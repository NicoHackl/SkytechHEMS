"""Tests für BatteryDevice: Pool-Semantik, SoC-Grenzen, Rampen, Schreibvertrag.

Der Speicher ist die erste Klasse, die den Messwert, auf dem das gesamte HEMS
aufbaut, selbst verfälscht. Die Tests hier sichern beide Seiten ab: was der
Speicher in den Pool zurückmeldet (current_w, gemessene_last_w, netz_support_w)
und was er nach HA schreibt (ein signierter Sollwert plus Betriebsart).
"""

import pytest

from ems.devices import BatteryDevice

from conftest import make_states


PREFIX = "acspeicher1"
SOC_ENTITY     = f"sensor.{PREFIX}_soc"
LADE_ENTITY    = f"sensor.{PREFIX}_ladeleistung"
ENTLADE_ENTITY = f"sensor.{PREFIX}_entladeleistung"
LADE_LIMIT     = f"sensor.{PREFIX}_lade_limit"
ENTLADE_LIMIT  = f"sensor.{PREFIX}_entlade_limit"
ANF_ENTITY     = f"input_number.ems_{PREFIX}_anforderung_leistung_w"
ANF_MODE       = f"input_select.ems_{PREFIX}_anforderung_betriebsart"


def make_battery(**kw):
    """Speicher mit getrennten Ist-Sensoren (Variante A aus D-B12).

    Die beiden available_*-Sensoren sind Pflicht: sie sind die alleinigen
    physischen Maximalgrenzen.
    """
    kw.setdefault("soc_entity", SOC_ENTITY)
    kw.setdefault("available_charge_power_entity", LADE_LIMIT)
    kw.setdefault("available_discharge_power_entity", ENTLADE_LIMIT)
    if not kw.get("power_entity"):
        kw.setdefault("charge_power_entity", LADE_ENTITY)
        kw.setdefault("discharge_power_entity", ENTLADE_ENTITY)
    d = BatteryDevice(id=PREFIX, allowed_modes=["auto", "manuell"],
                      entity_prefix=PREFIX, **kw)
    d.eligible = True
    d.source = "user"
    return d


def battery_states(*, soc=50, lade_ist=0, entlade_ist=0, sollwert=0,
                   betriebsart="auto", anforderung_betriebsart="standby",
                   lade_limit=5000, entlade_limit=5000,
                   min_lade=0, min_entlade=0, soc_min=10, soc_max=100,
                   prio=1, entlade_prio=50, totzone=0,
                   hoch=0, runter=0, schritt=100000, deadband=0,
                   laden="on", entladen="on", netzladen="off",
                   geschuetzt=0, reserve=0, **extra):
    """Vollständiger HA-Schnappschuss eines Speichers.

    Die Voreinstellungen schalten alle Zeit- und Totband-Bremsen aus, damit ein
    Test genau die Bremse einschaltet, die er prüft.
    """
    states = {
        SOC_ENTITY:     soc,
        LADE_ENTITY:    lade_ist,
        ENTLADE_ENTITY: entlade_ist,
        LADE_LIMIT:     lade_limit,
        ENTLADE_LIMIT:  entlade_limit,
        ANF_ENTITY:     sollwert,
        ANF_MODE:       anforderung_betriebsart,
        f"input_select.ems_{PREFIX}_betriebsart":              betriebsart,
        f"input_boolean.ems_{PREFIX}_laden_erlaubt":           laden,
        f"input_boolean.ems_{PREFIX}_entladen_erlaubt":        entladen,
        f"input_boolean.ems_{PREFIX}_netzladen_aktiv":         netzladen,
        f"input_number.ems_{PREFIX}_prioritat":                prio,
        f"input_number.ems_{PREFIX}_entlade_prioritat":        entlade_prio,
        f"input_number.ems_{PREFIX}_min_ladeleistung_w":       min_lade,
        f"input_number.ems_{PREFIX}_min_entladeleistung_w":    min_entlade,
        f"input_number.ems_{PREFIX}_soc_min_prozent":          soc_min,
        f"input_number.ems_{PREFIX}_soc_max_prozent":          soc_max,
        f"input_number.ems_{PREFIX}_umschalt_totzone_w":       totzone,
        f"input_number.ems_{PREFIX}_hoch_regelzeit_s":         hoch,
        f"input_number.ems_{PREFIX}_runter_regelzeit_s":       runter,
        f"input_number.ems_{PREFIX}_max_anderung_pro_schritt_w": schritt,
        f"input_number.ems_{PREFIX}_min_anderung_pro_schritt_w": deadband,
        f"input_number.ems_{PREFIX}_geschutzte_mindestleistung_w": geschuetzt,
        f"input_number.ems_{PREFIX}_reserve_w":                reserve,
        f"input_number.ems_{PREFIX}_netzlade_leistung_w":      0,
    }
    states.update(extra)
    return make_states(states)


def prepare(device, now_ts=10_000.0, **kw):
    """begin_cycle + update_from_ha in einem Schritt."""
    device.begin_cycle(now_ts)
    device.update_from_ha(battery_states(**kw), now_ts, 0.0)
    return device


def op_for(write_ops, entity_id):
    return next((op for op in write_ops if op[2].get("entity_id") == entity_id), None)


# ---------------------------------------------------------------------------
# Pool-Semantik
# ---------------------------------------------------------------------------

def test_current_w_nur_hems_ladeleistung():
    """Extern erzwungenes Laden über dem Sollwert zählt nicht in den Pool."""
    b = prepare(make_battery(), lade_ist=3000, sollwert=1000)
    assert b.current_w == 1000.0
    b = prepare(make_battery(), lade_ist=800, sollwert=1000)
    assert b.current_w == 800.0


def test_current_w_null_bei_netzladen():
    """Netzgeladene Leistung ist kein PV-Überschuss und darf nicht in den Pool."""
    b = prepare(make_battery(), lade_ist=3000, sollwert=3000, netzladen="on")
    assert b.current_w == 0.0


def test_gemessene_last_w_auch_bei_netzladen():
    """Gegenstück zum Test darüber: sonst sieht Speicher B das Netzladen von A
    als Hauslast und deckt es (Kreisstrom über zwei Geräte)."""
    b = prepare(make_battery(), lade_ist=3000, sollwert=3000, netzladen="on")
    assert b.gemessene_last_w == 3000.0


def test_gemessene_last_w_ignoriert_eligible():
    b = prepare(make_battery(), lade_ist=2500, sollwert=0)
    b.eligible = False
    assert b.current_w == 0.0
    assert b.gemessene_last_w == 2500.0


def test_netz_support_immer_messwert():
    """Entladung zählt auch ohne HEMS-Anforderung – sie verfälscht den Netzpunkt."""
    b = prepare(make_battery(), entlade_ist=1840, sollwert=0)
    assert b.netz_support_w == 1840.0
    b.eligible = False
    assert b.netz_support_w == 1840.0


def test_max_relief_ohne_min_technisch_abzug():
    """Anders als ein Heizstab kann der Speicher von jedem Ladewert sofort auf 0."""
    b = prepare(make_battery(), lade_ist=2000, sollwert=2000, min_lade=1000)
    assert b.max_relief_w == 2000.0


def test_signierter_sollwert_wird_korrekt_aufgeteilt():
    """D-B20: eine Entität, + laden / - entladen."""
    b = prepare(make_battery(), sollwert=2000)
    assert (b.lade_anforderung_w, b.entlade_anforderung_w) == (2000.0, 0.0)
    b = prepare(make_battery(), sollwert=-1800)
    assert (b.lade_anforderung_w, b.entlade_anforderung_w) == (0.0, 1800.0)


def test_signierter_ist_sensor_beide_vorzeichen():
    """D-B12 Variante B: ein Sensor für beide Richtungen."""
    for sign, wert, erwartet_lade, erwartet_entlade in [
        ("positiv_laden",    2000, 2000.0, 0.0),
        ("positiv_laden",   -1500, 0.0, 1500.0),
        ("positiv_entladen", 2000, 0.0, 2000.0),
        ("positiv_entladen", -900, 900.0, 0.0),
    ]:
        b = make_battery(power_entity=f"sensor.{PREFIX}_leistung", power_sign=sign)
        prepare(b, **{f"sensor.{PREFIX}_leistung": wert})
        assert b.gemessene_last_w == erwartet_lade
        assert b.netz_support_w == erwartet_entlade


# ---------------------------------------------------------------------------
# SoC-Grenzen und Derating
# ---------------------------------------------------------------------------

def test_soc_max_stoppt_laden():
    b = prepare(make_battery(), soc=100, soc_max=100)
    assert b._lade_limit_w() == 0.0
    assert b._darf_laden() is False


def test_soc_min_stoppt_entladen():
    b = prepare(make_battery(), soc=10, soc_min=10)
    assert b.entlade_kapazitaet_w() == 0.0


def test_kein_soc_taper_mehr():
    """Innerhalb der SoC-Grenzen gilt allein das momentane WR-Limit.

    Die CV-Phase regelt der Wechselrichter selbst – und genau das meldet er
    über die available_*-Sensoren. Ein zweites, lineares Drosselband im HEMS
    hätte dagegengeregelt."""
    b = prepare(make_battery(), soc=97.5, soc_max=100, lade_limit=4000)
    assert b._lade_limit_w() == pytest.approx(4000.0)
    b = prepare(make_battery(), soc=12.5, soc_min=10, entlade_limit=4000)
    assert b._entlade_limit_w() == pytest.approx(4000.0)


def test_soc_max_hysterese_haelt_gesperrt():
    """Nach Erreichen von soc_max bleibt der Ladepfad zu, bis der SoC unter die
    Wiedereinstiegsschwelle fällt – sonst flippt der Speicher bei 100 % im Takt."""
    b = make_battery(soc_max_hysteresis_percent=2.0)
    prepare(b, soc=100, soc_max=100)
    assert b._lade_limit_w() == 0.0
    prepare(b, soc=99, soc_max=100)      # noch im Hysterese-Band
    assert b._lade_limit_w() == 0.0
    prepare(b, soc=97, soc_max=100)      # unter der Schwelle
    assert b._lade_limit_w() > 0.0


def test_entladeboden_ist_allein_soc_min():
    """Die Notstromreserve entfällt ersatzlos – der Boden ist soc_min_prozent."""
    b = prepare(make_battery(), soc=25, soc_min=10)
    assert b.entlade_kapazitaet_w() > 0.0
    b = prepare(make_battery(), soc=9, soc_min=10)
    assert b.entlade_kapazitaet_w() == 0.0
    assert b._entlade_block == "soc_min"


def test_available_sensor_ist_die_ladegrenze():
    b = prepare(make_battery(), lade_limit=1200)
    assert b._lade_limit_w() == 1200.0


def test_leistungssensor_unavailable_faellt_aus_regelung():
    """Ohne Messwert ist netz_support_w unbekannt und die Pool-Bereinigung blind."""
    b = prepare(make_battery(), entlade_ist="unavailable")
    assert b.sensoren_gueltig is False
    b.calculate_ramp(0.0)
    assert (b.new_lade_w, b.new_entlade_w) == (0.0, 0.0)
    assert b.new_betriebsart == "standby"


def test_soc_unavailable_faellt_aus_regelung():
    b = prepare(make_battery(), soc="unavailable")
    assert b.sensoren_gueltig is False
    assert b._darf_laden() is False
    assert b.entlade_kapazitaet_w() == 0.0


# ---------------------------------------------------------------------------
# Richtungsauflösung
# ---------------------------------------------------------------------------

def test_niemals_laden_bei_hausdefizit():
    """D-B10: liegt ein Entladeziel an, wird der Ladewunsch verworfen."""
    b = prepare(make_battery())
    b._alloc_w = 2000.0
    b.set_discharge_target(1500.0)
    b.calculate_ramp(0.0)
    assert b.new_lade_w == 0.0
    assert b.new_entlade_w == 1500.0
    assert b._lade_block == "hausdefizit"


def test_niemals_gleichzeitig_laden_und_entladen():
    b = prepare(make_battery())
    b._alloc_w = 2000.0
    b.set_discharge_target(0.0)
    b.calculate_ramp(0.0)
    assert b.new_lade_w == 0.0 or b.new_entlade_w == 0.0


def test_totzone_fuehrt_zu_standby():
    b = prepare(make_battery(), totzone=100)
    b.set_discharge_target(60.0)
    b.calculate_ramp(0.0)
    assert (b.new_lade_w, b.new_entlade_w) == (0.0, 0.0)
    assert b.new_betriebsart == "standby"
    assert b.to_status_dict()["blockiert_grund"] == "totzone"


def test_umschaltsperre_blockiert_richtungswechsel():
    """Läuft der Speicher auf Laden, darf er nicht sofort auf Entladen springen."""
    b = prepare(make_battery(direction_switch_delay_s=300), sollwert=2000)
    b._last_direction_change_ts = 10_000.0 - 60.0     # vor 60 s gewechselt
    b.set_discharge_target(1500.0)
    b.calculate_ramp(0.0)
    assert (b.new_lade_w, b.new_entlade_w) == (0.0, 0.0)
    assert b.to_status_dict()["blockiert_grund"] == "umschaltsperre"


def test_umschaltsperre_faehrt_standby_nicht_alte_richtung():
    """In der Sperrzeit wird STANDBY gefahren – sonst entlädt der Speicher in den
    PV-Überschuss hinein."""
    b = prepare(make_battery(direction_switch_delay_s=300), sollwert=-1800)
    b._last_direction_change_ts = 10_000.0 - 10.0
    b._alloc_w = 2500.0
    b.calculate_ramp(0.0)
    assert b.new_betriebsart == "standby"
    assert b.new_entlade_w == 0.0


def test_umschaltsperre_laeuft_ab():
    b = prepare(make_battery(direction_switch_delay_s=300), sollwert=2000)
    b._last_direction_change_ts = 10_000.0 - 400.0    # Sperre abgelaufen
    b.set_discharge_target(1500.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w == 1500.0


# ---------------------------------------------------------------------------
# Rampen
# ---------------------------------------------------------------------------

def test_entladung_runter_folgt_der_schrittbegrenzung():
    """Die Entlade-Sofort-Schwelle entfällt: Absenkungen laufen ausschließlich
    über max_anderung_pro_schritt_w."""
    b = prepare(make_battery(), sollwert=-3000, schritt=100)
    b.set_discharge_target(500.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w == 2900.0


def test_entladung_runter_ohne_schrittbegrenzung_sofort():
    """Fehlt die Maximaländerung, wird das Ziel unmittelbar erreicht."""
    states = battery_states(sollwert=-3000)
    del states._states[f"input_number.ems_{PREFIX}_max_anderung_pro_schritt_w"]
    b = make_battery()
    b.begin_cycle(10_000.0)
    b.update_from_ha(states, 10_000.0, 0.0)
    b.set_discharge_target(500.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w == 500.0


def test_entladung_hoch_gerampt():
    b = prepare(make_battery(), sollwert=-1000, schritt=200)
    b.set_discharge_target(3000.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w == 1200.0


def test_entladung_hoch_wartet_auf_hoch_regelzeit():
    """hoch_regelzeit_s ist der Stabilitätsparameter gegen H-7, nicht Komfort."""
    now = 10_000.0
    b = make_battery()
    b.begin_cycle(now)
    b.update_from_ha(
        battery_states(sollwert=-1000, hoch=60, schritt=100000),
        now, 0.0,
    )
    b._anforderung_age_s = 10.0                       # jünger als hoch_regelzeit_s
    b.set_discharge_target(3000.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w == 1000.0


def test_laden_bei_defizit_sofort_zurueck():
    b = prepare(make_battery(), sollwert=3000, runter=600, schritt=100)
    b._alloc_w = 0.0
    b.calculate_ramp(current_deficit_w=500.0)
    assert b.new_lade_w == 0.0


def test_zu_kleine_zuteilung_rastet_auf_null():
    """Unterhalb der technischen Untergrenze gibt es nur 0 – nie überschießen."""
    b = prepare(make_battery(), min_entlade=800)
    b.set_discharge_target(300.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w == 0.0


# ---------------------------------------------------------------------------
# Schreibvertrag
# ---------------------------------------------------------------------------

def test_write_reihenfolge_beim_einschalten():
    """Erst Betriebsart, dann Leistung."""
    b = prepare(make_battery(), sollwert=0, anforderung_betriebsart="standby")
    b.set_discharge_target(1500.0)
    b.calculate_ramp(0.0)
    ops = b.get_write_ops()
    assert [op[2]["entity_id"] for op in ops] == [ANF_MODE, ANF_ENTITY]
    assert ops[0][2]["option"] == "entladen"
    assert ops[1][2]["value"] == -1500.0


def test_write_reihenfolge_beim_abschalten():
    """Erst Leistung auf 0, dann Modus – ein Modussprung bei stehender Leistung
    kann am Gerät einen Stromstoss erzeugen."""
    b = prepare(make_battery(), sollwert=-1500, anforderung_betriebsart="entladen",
                betriebsart="standby")
    b.calculate_ramp(0.0)
    ops = b.get_write_ops()
    assert [op[2]["entity_id"] for op in ops] == [ANF_ENTITY, ANF_MODE]
    assert ops[0][2]["value"] == 0.0
    assert ops[1][2]["option"] == "standby"


def test_deadband_unterdrueckt_kleine_aenderung():
    b = prepare(make_battery(), sollwert=-1500, anforderung_betriebsart="entladen",
                deadband=100)
    b.set_discharge_target(1540.0)
    b.calculate_ramp(0.0)
    assert b.get_write_ops() == []
    # Anzeige muss zeigen, was wirklich in HA steht
    assert b.new_entlade_w == 1500.0


def test_deadband_beim_senken_der_entladung_aus():
    """Beim Zurücknehmen einer Entladung zählt Geschwindigkeit mehr als
    Schreibsparsamkeit."""
    b = prepare(make_battery(), sollwert=-1500, anforderung_betriebsart="entladen",
                deadband=500)
    b.set_discharge_target(1400.0)
    b.calculate_ramp(0.0)
    assert op_for(b.get_write_ops(), ANF_ENTITY)[2]["value"] == -1400.0


def test_deadband_beim_vorzeichenwechsel_aus():
    b = prepare(make_battery(direction_switch_delay_s=0), sollwert=-50,
                anforderung_betriebsart="entladen", deadband=500, min_entlade=0)
    b._alloc_w = 60.0
    b.calculate_ramp(0.0)
    assert op_for(b.get_write_ops(), ANF_ENTITY)[2]["value"] == 60.0


def test_schreibt_sicheren_zustand_aktiv_bei_lockout():
    """Nicht 'nichts tun' – der letzte Sollwert bliebe sonst stehen und der
    Speicher entlädt bis leer weiter."""
    b = prepare(make_battery(), sollwert=-4000, anforderung_betriebsart="entladen")
    b.eligible = False
    b.calculate_ramp(0.0)
    ops = b.get_write_ops()
    assert op_for(ops, ANF_ENTITY)[2]["value"] == 0.0
    assert op_for(ops, ANF_MODE)[2]["option"] == "standby"


def test_sicherer_zustand_ist_immer_standby():
    """Ohne autonome Rückfallregelung gibt es keinen anderen sicheren Zustand."""
    b = make_battery()
    assert b._sicherer_zustand() == "standby"
    assert "inverter" not in BatteryDevice.BETRIEBSARTEN


def test_kein_schreiben_im_eingeschwungenen_zustand():
    """Bei 3 s Takt und n Speichern ist Schreibsparsamkeit auch HA-Last."""
    b = prepare(make_battery(), sollwert=-1500, anforderung_betriebsart="entladen")
    b.set_discharge_target(1500.0)
    b.calculate_ramp(0.0)
    assert b.get_write_ops() == []


# ---------------------------------------------------------------------------
# Betriebsarten, Sperrgründe, Statusanzeige
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("betriebsart,laedt,entlaedt", [
    ("auto",          True,  True),
    ("nur_laden",     True,  False),
    ("nur_entladen",  False, True),
    ("standby",       False, False),
])
def test_betriebsarten_gaten_beide_pfade(betriebsart, laedt, entlaedt):
    b = prepare(make_battery(), betriebsart=betriebsart)
    assert b._darf_laden() is laedt
    assert (b.entlade_kapazitaet_w() > 0) is entlaedt


def test_unbekannte_betriebsart_faellt_auf_standby():
    b = prepare(make_battery(), betriebsart="quatsch")
    assert b.betriebsart == "standby"


@pytest.mark.parametrize("kwargs,feld,grund", [
    ({"betriebsart": "nur_entladen"},      "_lade_block",    "betriebsart"),
    ({"laden": "off"},                     "_lade_block",    "laden_gesperrt"),
    ({"soc": 100, "soc_max": 100},         "_lade_block",    "soc_max"),
    ({"betriebsart": "nur_laden"},         "_entlade_block", "betriebsart"),
    ({"entladen": "off"},                  "_entlade_block", "entladen_gesperrt"),
    ({"soc": 5, "soc_min": 10},            "_entlade_block", "soc_min"),
    ({"netzladen": "on"},                  "_entlade_block", "netzladen"),
    ({"soc": "unavailable"},               "_lade_block",    "sensor_ungueltig"),
    ({"lade_limit": "unavailable"},        "_lade_block",    "limit_sensor"),
    ({"entlade_limit": "unavailable"},     "_entlade_block", "limit_sensor"),
    ({"lade_limit": 0},                    "_lade_block",    "wr_derating"),
    ({"entlade_limit": 0},                 "_entlade_block", "wr_derating"),
])
def test_blockiert_grund_je_sperrfall(kwargs, feld, grund):
    b = prepare(make_battery(), **kwargs)
    b._darf_laden()
    b.entlade_kapazitaet_w()
    assert getattr(b, feld) == grund


def test_status_dict_grundform():
    b = prepare(make_battery(capacity_kwh=10.0), soc=72.5, entlade_ist=1840,
                sollwert=-1800, entlade_prio=30)
    b.set_discharge_target(1900.0)
    b.calculate_ramp(0.0)
    d = b.to_status_dict()
    assert d["type"] == "battery"
    assert d["entlade_prioritat"] == 30
    assert d["soc_prozent"] == 72.5
    assert d["energie_kwh"] == pytest.approx(7.25)
    assert d["betriebsart_effektiv"] == "entladen"
    assert d["netto_w"] == -1900.0
    assert d["hausdefizit_anteil_w"] == 1900.0
    assert "shelly_fallback" not in d


def test_status_dict_ohne_kapazitaet_hat_keine_energie():
    b = prepare(make_battery(), soc=50)
    assert "energie_kwh" not in b.to_status_dict()


def test_gesperrter_speicher_reserviert_keinen_pool():
    """Ein Speicher, der gerade nicht laden darf, nimmt binären Geräten keine
    Leistung weg, die er selbst nicht abrufen kann."""
    b = prepare(make_battery(), betriebsart="nur_entladen", geschuetzt=1500)
    assert b.consume_from_pool(4000.0, 0.0) == 4000.0

    b = prepare(make_battery(), betriebsart="auto", geschuetzt=1500)
    assert b.consume_from_pool(4000.0, 0.0) == 2500.0


# ---------------------------------------------------------------------------
# Vereinfachter Speichervertrag: available_*-Sensoren, entfallene Helfer
# ---------------------------------------------------------------------------

ENTFALLENE_HELFER = (
    f"input_number.ems_{PREFIX}_max_ladeleistung_w",
    f"input_number.ems_{PREFIX}_max_entladeleistung_w",
    f"input_number.ems_{PREFIX}_soc_reserve_prozent",
    f"input_number.ems_{PREFIX}_soc_taper_band_prozent",
    f"input_number.ems_{PREFIX}_soc_max_hysterese_prozent",
    f"input_number.ems_{PREFIX}_entlade_sofort_schwelle_w",
    f"input_number.ems_{PREFIX}_min_umschaltzeit_s",
)


def test_entfallene_helfer_werden_nicht_mehr_gelesen():
    """Sie dürfen weder die Regelung beeinflussen noch in der Diagnose auftauchen."""
    b = prepare(make_battery(), **{entity: 4242 for entity in ENTFALLENE_HELFER})
    assert not set(ENTFALLENE_HELFER) & set(b.entity_diagnostics)
    assert b._lade_limit_w() == 5000.0          # aus dem available_*-Sensor, nicht 4242
    assert b.soc_max_hysteresis_percent == 2.0
    assert b.direction_switch_delay_s == 5.0


def test_beide_limits_begrenzen_unabhaengig():
    b = prepare(make_battery(), lade_limit=1500, entlade_limit=4200)
    assert b._lade_limit_w() == 1500.0
    assert b._entlade_limit_w() == 4200.0


@pytest.mark.parametrize("fehlerbild", ["unavailable", "unknown", "kaputt"])
def test_defekter_ladelimit_sensor_sperrt_nur_den_ladepfad(fehlerbild):
    b = prepare(make_battery(), lade_limit=fehlerbild, entlade_limit=4000)
    assert b._lade_limit_w() == 0.0
    assert b._darf_laden() is False
    assert b._lade_block == "limit_sensor"
    assert b.entlade_kapazitaet_w() == 4000.0


@pytest.mark.parametrize("fehlerbild", ["unavailable", "unknown", "kaputt"])
def test_defekter_entladelimit_sensor_sperrt_nur_den_entladepfad(fehlerbild):
    b = prepare(make_battery(), lade_limit=4000, entlade_limit=fehlerbild)
    assert b.entlade_kapazitaet_w() == 0.0
    assert b._entlade_block == "limit_sensor"
    assert b._darf_laden() is True


def test_fehlender_limit_sensor_sperrt_nur_seine_richtung():
    states = battery_states()
    del states._states[LADE_LIMIT]
    b = make_battery()
    b.begin_cycle(10_000.0)
    b.update_from_ha(states, 10_000.0, 0.0)
    assert b._darf_laden() is False
    assert b.entlade_kapazitaet_w() == 5000.0
    assert b.entity_diagnostics[LADE_LIMIT]["state"] == "missing"


def test_gueltige_null_sperrt_die_richtung_bewusst():
    b = prepare(make_battery(), lade_limit=0, entlade_limit=0)
    assert b._darf_laden() is False
    assert b._lade_block == "wr_derating"
    assert b.entlade_kapazitaet_w() == 0.0
    assert b._entlade_block == "wr_derating"
    assert b.entity_diagnostics[LADE_LIMIT]["state"] == "valid"


def test_defaults_der_statischen_speicherfelder():
    b = make_battery()
    assert b.soc_max_hysteresis_percent == 2.0
    assert b.direction_switch_delay_s == 5.0


# ---- Freigaben: fehlend heißt erlaubt, ausgefallen heißt gesperrt ----

def test_fehlende_freigabe_entitaet_gilt_als_erlaubt():
    states = battery_states()
    del states._states[f"input_boolean.ems_{PREFIX}_laden_erlaubt"]
    del states._states[f"input_boolean.ems_{PREFIX}_entladen_erlaubt"]
    b = make_battery()
    b.begin_cycle(10_000.0)
    b.update_from_ha(states, 10_000.0, 0.0)
    assert b.laden_erlaubt is True
    assert b.entladen_erlaubt is True


@pytest.mark.parametrize("fehlerbild", ["unavailable", "unknown", "vielleicht"])
def test_ausgefallene_freigabe_entitaet_gilt_als_gesperrt(fehlerbild):
    """Ein ausgefallener Schalter ist kein Grund, weiterzuregeln."""
    b = prepare(make_battery(), laden=fehlerbild, entladen=fehlerbild)
    assert b.laden_erlaubt is False
    assert b.entladen_erlaubt is False
    assert b._darf_laden() is False
    assert b.entlade_kapazitaet_w() == 0.0


# ---- Reserve ----

def test_fehlende_reserve_entitaet_faellt_auf_50_watt():
    states = battery_states()
    del states._states[f"input_number.ems_{PREFIX}_reserve_w"]
    b = make_battery()
    b.begin_cycle(10_000.0)
    b.update_from_ha(states, 10_000.0, 0.0)
    assert b.reserve_w == 50.0


def test_vorhandene_reserve_null_ueberschreibt_den_default():
    b = prepare(make_battery(), reserve=0)
    assert b.reserve_w == 0.0


# ---- Schrittbegrenzung ----

def test_schrittbegrenzung_gilt_in_beiden_richtungen():
    b = prepare(make_battery(), sollwert=1000, schritt=200)
    b._alloc_w = 5000.0
    b.calculate_ramp(0.0)
    assert b.new_lade_w == 1200.0

    b = prepare(make_battery(), sollwert=-1000, schritt=200)
    b.set_discharge_target(4000.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w == 1200.0


def test_ohne_schrittbegrenzung_wird_das_ziel_direkt_erreicht():
    states = battery_states(sollwert=0)
    del states._states[f"input_number.ems_{PREFIX}_max_anderung_pro_schritt_w"]
    b = make_battery()
    b.begin_cycle(10_000.0)
    b.update_from_ha(states, 10_000.0, 0.0)
    assert b._step_limit_w is None
    b._alloc_w = 4000.0
    b.calculate_ramp(0.0)
    assert b.new_lade_w == 4000.0


# ---- Sofort-Stopp und gesunkenes Limit ----

@pytest.mark.parametrize("kwargs", [
    {"betriebsart": "standby"},
    {"soc": "unavailable"},
    {"entlade_ist": "unavailable"},
])
def test_sicherheitsgruende_stoppen_sofort_ohne_rampe(kwargs):
    b = prepare(make_battery(), sollwert=-4000, schritt=50, **kwargs)
    b.calculate_ramp(0.0)
    assert (b.new_lade_w, b.new_entlade_w) == (0.0, 0.0)
    assert b.new_betriebsart == "standby"


def test_gesunkenes_wr_limit_wird_nach_der_rampe_nie_ueberschritten():
    """Die Rampe darf bremsen, aber nie über die momentane physische Grenze."""
    b = prepare(make_battery(), sollwert=-4000, entlade_limit=800, schritt=100)
    b.set_discharge_target(4000.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w <= 800.0

    b = prepare(make_battery(), sollwert=4000, lade_limit=600, schritt=100)
    b._alloc_w = 4000.0
    b.calculate_ramp(0.0)
    assert b.new_lade_w <= 600.0


# ---- Energy Pilot ----

def test_ep_maximalvorschlaege_werden_ignoriert():
    """Der Energy Pilot darf physische WR-Limits nicht überschreiben."""
    b = make_battery()
    b.source = "ep"
    prepare(b, lade_limit=1500, entlade_limit=1500, **{
        f"sensor.ep_{PREFIX}_lade_max_w_vorschlag": 9000,
        f"sensor.ep_{PREFIX}_entlade_max_w_vorschlag": 9000,
    })
    assert b._lade_limit_w() == 1500.0
    assert b._entlade_limit_w() == 1500.0
