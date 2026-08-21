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
ANF_ENTITY     = f"input_number.ems_{PREFIX}_anforderung_leistung_w"
ANF_MODE       = f"input_select.ems_{PREFIX}_anforderung_betriebsart"


def make_battery(**kw):
    """Speicher mit getrennten Ist-Sensoren (Variante A aus D-B12)."""
    kw.setdefault("soc_entity", SOC_ENTITY)
    kw.setdefault("charge_power_entity", LADE_ENTITY)
    kw.setdefault("discharge_power_entity", ENTLADE_ENTITY)
    d = BatteryDevice(id=PREFIX, allowed_modes=["auto", "manuell"],
                      entity_prefix=PREFIX, **kw)
    d.eligible = True
    d.source = "user"
    return d


def battery_states(*, soc=50, lade_ist=0, entlade_ist=0, sollwert=0,
                   betriebsart="auto", anforderung_betriebsart="standby",
                   max_lade=5000, min_lade=0, max_entlade=5000, min_entlade=0,
                   soc_min=10, soc_max=100, soc_reserve=0, taper=0, hysterese=2,
                   prio=1, entlade_prio=50, sofort=300, totzone=0, umschaltzeit=0,
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
        ANF_ENTITY:     sollwert,
        ANF_MODE:       anforderung_betriebsart,
        f"input_select.ems_{PREFIX}_betriebsart":              betriebsart,
        f"input_boolean.ems_{PREFIX}_laden_erlaubt":           laden,
        f"input_boolean.ems_{PREFIX}_entladen_erlaubt":        entladen,
        f"input_boolean.ems_{PREFIX}_netzladen_aktiv":         netzladen,
        f"input_number.ems_{PREFIX}_prioritat":                prio,
        f"input_number.ems_{PREFIX}_entlade_prioritat":        entlade_prio,
        f"input_number.ems_{PREFIX}_max_ladeleistung_w":       max_lade,
        f"input_number.ems_{PREFIX}_min_ladeleistung_w":       min_lade,
        f"input_number.ems_{PREFIX}_max_entladeleistung_w":    max_entlade,
        f"input_number.ems_{PREFIX}_min_entladeleistung_w":    min_entlade,
        f"input_number.ems_{PREFIX}_soc_min_prozent":          soc_min,
        f"input_number.ems_{PREFIX}_soc_max_prozent":          soc_max,
        f"input_number.ems_{PREFIX}_soc_reserve_prozent":      soc_reserve,
        f"input_number.ems_{PREFIX}_soc_taper_band_prozent":   taper,
        f"input_number.ems_{PREFIX}_soc_max_hysterese_prozent": hysterese,
        f"input_number.ems_{PREFIX}_entlade_sofort_schwelle_w": sofort,
        f"input_number.ems_{PREFIX}_umschalt_totzone_w":       totzone,
        f"input_number.ems_{PREFIX}_min_umschaltzeit_s":       umschaltzeit,
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
        b = BatteryDevice(id=PREFIX, allowed_modes=["auto"], entity_prefix=PREFIX,
                          soc_entity=SOC_ENTITY,
                          power_entity=f"sensor.{PREFIX}_leistung",
                          power_sign=sign)
        b.eligible, b.source = True, "user"
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


def test_soc_taper_linear():
    """Halbes Drosselband übrig -> halbe Leistung."""
    b = prepare(make_battery(), soc=97.5, soc_max=100, taper=5, max_lade=4000)
    assert b._lade_limit_w() == pytest.approx(2000.0)
    b = prepare(make_battery(), soc=12.5, soc_min=10, taper=5, max_entlade=4000)
    assert b._entlade_limit_w() == pytest.approx(2000.0)


def test_soc_max_hysterese_haelt_gesperrt():
    """Nach Erreichen von soc_max bleibt der Ladepfad zu, bis der SoC unter die
    Wiedereinstiegsschwelle fällt – sonst flippt der Speicher bei 100 % im Takt."""
    b = make_battery()
    prepare(b, soc=100, soc_max=100, hysterese=2)
    assert b._lade_limit_w() == 0.0
    prepare(b, soc=99, soc_max=100, hysterese=2)      # noch im Hysterese-Band
    assert b._lade_limit_w() == 0.0
    prepare(b, soc=97, soc_max=100, hysterese=2)      # unter der Schwelle
    assert b._lade_limit_w() > 0.0


def test_soc_reserve_blockiert_entladung():
    b = prepare(make_battery(), soc=25, soc_min=10, soc_reserve=30)
    assert b.entlade_kapazitaet_w() == 0.0
    assert b._entlade_block == "soc_reserve"


def test_wr_derating_hat_vorrang():
    entity = f"sensor.{PREFIX}_lade_limit"
    b = make_battery(available_charge_power_entity=entity)
    prepare(b, max_lade=5000, **{entity: 1200})
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
    b = prepare(make_battery(), sollwert=2000, umschaltzeit=300)
    b._last_direction_change_ts = 10_000.0 - 60.0     # vor 60 s gewechselt
    b.set_discharge_target(1500.0)
    b.calculate_ramp(0.0)
    assert (b.new_lade_w, b.new_entlade_w) == (0.0, 0.0)
    assert b.to_status_dict()["blockiert_grund"] == "umschaltsperre"


def test_umschaltsperre_faehrt_standby_nicht_alte_richtung():
    """In der Sperrzeit wird STANDBY gefahren – sonst entlädt der Speicher in den
    PV-Überschuss hinein."""
    b = prepare(make_battery(), sollwert=-1800, umschaltzeit=300)
    b._last_direction_change_ts = 10_000.0 - 10.0
    b._alloc_w = 2500.0
    b.calculate_ramp(0.0)
    assert b.new_betriebsart == "standby"
    assert b.new_entlade_w == 0.0


def test_umschaltsperre_laeuft_ab():
    b = prepare(make_battery(), sollwert=2000, umschaltzeit=300)
    b._last_direction_change_ts = 10_000.0 - 400.0    # Sperre abgelaufen
    b.set_discharge_target(1500.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w == 1500.0


# ---------------------------------------------------------------------------
# Rampen
# ---------------------------------------------------------------------------

def test_entladung_runter_sofort_ungerampt():
    """H-5: grosse Absenkung ist ein echter Lastabwurf -> sofort, sonst
    exportieren wir Batteriestrom."""
    b = prepare(make_battery(), sollwert=-3000, sofort=300, schritt=100)
    b.set_discharge_target(500.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w == 500.0


def test_kleine_absenkung_wird_gedaempft():
    """H-7: kleine Absenkungen sind meist Sensor-Versatz -> dämpfen, sonst
    entsteht daraus ein Grenzzyklus."""
    b = prepare(make_battery(), sollwert=-2000, sofort=300, schritt=50)
    b.set_discharge_target(1900.0)
    b.calculate_ramp(0.0)
    assert b.new_entlade_w == 1950.0


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
    b = prepare(make_battery(), sollwert=-50, anforderung_betriebsart="entladen",
                deadband=500, umschaltzeit=0, min_entlade=0)
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
    ({"soc": 20, "soc_reserve": 40},       "_entlade_block", "soc_reserve"),
    ({"netzladen": "on"},                  "_entlade_block", "netzladen"),
    ({"soc": "unavailable"},               "_lade_block",    "sensor_ungueltig"),
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
