"""End-to-End-Tests für EMSController.run_cycle MIT konfigurierten Geräten.

Diese Tests fahren die vollständige Pipeline
    HA-State → update_from_ha → consume_from_pool → allocate → ramp → get_write_ops
und prüfen die tatsächlich an HA geschriebenen Sollwerte (write_ops). Genau diese
Integrationsebene fehlte – die übrigen run_cycle-Tests laufen mit null Geräten.
Sie zementieren außerdem die Entitätsnamen-Konvention (Präfix, _w/_a-Suffix,
anzahl_phase) sowie die Watt↔Ampere-Umrechnung.
"""

import pytest

from ems.controller import EMSController
from ems.ops import WriteOp, WriteResult

from conftest import make_states


# ---------------------------------------------------------------------------
# State-Builder
# ---------------------------------------------------------------------------

def _global(**over):
    base = {
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "input_number.ems_globaler_puffer_w": 0,
        "input_number.ems_einschaltreserve_global_w": 0,
    }
    base.update(over)
    return base


def _controllable_w(prefix, *, prio=1, min_w=500, max_w=3000, geschuetzt=0,
                    reserve=0, actual=0, setpoint=0):
    """Watt-Modus: alle Grenzwert-Helfer eines regelbaren Geräts."""
    return {
        f"input_boolean.ems_{prefix}_freigabe": "on",
        f"input_boolean.ems_{prefix}_technische_freigabe": "on",
        f"input_select.ems_{prefix}_modus": "auto",
        f"input_number.ems_{prefix}_prioritat": prio,
        f"input_number.ems_{prefix}_min_technisch_w": min_w,
        f"input_number.ems_{prefix}_max_technisch_w": max_w,
        f"input_number.ems_{prefix}_geschutzte_mindestleistung_w": geschuetzt,
        f"input_number.ems_{prefix}_reserve_w": reserve,
        f"input_number.ems_{prefix}_hoch_regelzeit_s": 0,
        f"input_number.ems_{prefix}_runter_regelzeit_s": 0,
        f"input_number.ems_{prefix}_max_anderung_pro_schritt_w": 100000,
        f"input_number.ems_{prefix}_min_anderung_pro_schritt_w": 0,
        f"input_number.ems_{prefix}_anforderung_leistung_w": setpoint,
    }


def _binary(prefix, *, prio=2, power=1000, switch="off", anforderung=None):
    return {
        f"input_boolean.ems_{prefix}_anforderung_an": anforderung if anforderung else switch,
        f"input_boolean.ems_{prefix}_freigabe": "on",
        f"input_boolean.ems_{prefix}_technische_freigabe": "on",
        f"input_select.ems_{prefix}_modus": "auto",
        f"input_number.ems_{prefix}_prioritat": prio,
        f"input_number.ems_{prefix}_leistung_w": power,
        f"input_number.ems_{prefix}_einschaltreserve_w": 0,
        f"input_number.ems_{prefix}_mindestlaufzeit_s": 0,
        f"input_number.ems_{prefix}_mindestauszeit_s": 0,
        f"input_number.ems_{prefix}_abschaltverzogerung_s": 0,
    }


# Verpflichtende Add-on-Fallbacks. In diesen Tests liefern die HA-Helfer gültige
# Werte, der Add-on-Wert greift also nie – ohne ihn wäre der Eintrag aber
# ungültig und das Gerät würde gar nicht erst registriert.
CTRL_FALLBACKS = {
    "technical_minimum": 0, "technical_maximum": 100000,
    "increase_delay_s": 0, "decrease_delay_s": 0,
    "maximum_step_change": 100000, "minimum_step_change": 0,
}
BIN_FALLBACKS = {
    "power_w": 1000, "on_reserve_w": 0,
    "min_runtime_s": 0, "min_offtime_s": 0, "off_delay_s": 0,
}


def _op_for(write_ops, entity_id):
    """Findet die Schreiboperation für eine Entität: (domain, service, data) oder None."""
    return next((op for op in write_ops if op[2].get("entity_id") == entity_id), None)


# ---------------------------------------------------------------------------
# Regelbares Gerät (Watt) – Kern-Regression des geschuetzte_mindestleistung-Bugs
# ---------------------------------------------------------------------------

def test_controllable_runs_at_min_technisch_when_geschuetzt_exceeds_pool():
    # Heizstab: min_technisch=500, geschuetzt=2000; Pool=1500 trägt das technische
    # Minimum, aber nicht die volle geschützte Leistung. Erwartung: Gerät läuft und
    # nimmt den Überschuss bis zum Pool auf (1500 W) – der Bug schrieb 0 W.
    ctrl = EMSController(
        [{"name": "heizstab", "class": "controllable",
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}],
        residual_power_entity="sensor.s",
    )
    states = {
        **_global(),
        **_controllable_w("heizstab", min_w=500, max_w=3000, geschuetzt=2000),
        "sensor.s": 1500,
        "sensor.heizstab_ist": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    op = _op_for(res["write_ops"], "input_number.ems_heizstab_anforderung_leistung_w")
    assert op is not None, "Sollwert muss geschrieben werden (Gerät darf nicht aus bleiben)"
    assert op[2]["value"] == pytest.approx(1500)


# ---------------------------------------------------------------------------
# Doppelte Freigabe: _freigabe UND _technische_freigabe müssen aktiv sein
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("freigabe,technische_freigabe", [
    ("off", "on"),   # nur technische Freigabe → nicht eligible
    ("on",  "off"),  # nur Bedien-Freigabe     → nicht eligible
    ("off", "off"),  # keine Freigabe          → nicht eligible
])
def test_device_not_eligible_without_both_freigaben(freigabe, technische_freigabe):
    ctrl = EMSController(
        [{"name": "heizstab", "class": "controllable",
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}],
        residual_power_entity="sensor.s",
    )
    states = {
        **_global(),
        **_controllable_w("heizstab", min_w=500, max_w=3000),
        "input_boolean.ems_heizstab_freigabe": freigabe,
        "input_boolean.ems_heizstab_technische_freigabe": technische_freigabe,
        "sensor.s": 5000,
        "sensor.heizstab_ist": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    assert res["status"]["devices"][0]["eligible"] is False


def test_device_eligible_only_when_both_freigaben_on():
    ctrl = EMSController(
        [{"name": "heizstab", "class": "controllable",
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}],
        residual_power_entity="sensor.s",
    )
    states = {
        **_global(),
        # _controllable_w setzt beide Freigaben bereits auf "on"
        **_controllable_w("heizstab", min_w=500, max_w=3000),
        "sensor.s": 5000,
        "sensor.heizstab_ist": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    assert res["status"]["devices"][0]["eligible"] is True


def test_controllable_surplus_capped_at_max():
    ctrl = EMSController(
        [{"name": "heizstab", "class": "controllable",
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}],
        residual_power_entity="sensor.s",
    )
    states = {
        **_global(),
        **_controllable_w("heizstab", min_w=500, max_w=3000, geschuetzt=0),
        "sensor.s": 5000,
        "sensor.heizstab_ist": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    op = _op_for(res["write_ops"], "input_number.ems_heizstab_anforderung_leistung_w")
    assert op[2]["value"] == pytest.approx(3000)   # bei max_technisch_w gedeckelt


def test_controllable_below_min_technisch_stays_off():
    # Pool unter dem technischen Minimum → Gerät bleibt aus (kein Schreibvorgang,
    # da Sollwert bereits 0 ist).
    ctrl = EMSController(
        [{"name": "heizstab", "class": "controllable",
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}],
        residual_power_entity="sensor.s",
    )
    states = {
        **_global(),
        **_controllable_w("heizstab", min_w=2000, max_w=3000, setpoint=0),
        "sensor.s": 1500,
        "sensor.heizstab_ist": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    op = _op_for(res["write_ops"], "input_number.ems_heizstab_anforderung_leistung_w")
    assert op is None   # bleibt bei 0 → kein Schreibvorgang


# ---------------------------------------------------------------------------
# Echte Rolle von geschuetzte_mindestleistung: Schutz gegen binäre Verbraucher
# ---------------------------------------------------------------------------

def test_geschuetzt_protects_power_from_lower_priority_binary():
    # Heizstab (Prio 1, min=0) + Heizlüfter (Prio 2, 1000 W). Pool = 2500 W.
    # Ohne geschützte Mindestleistung reicht der Pool → Binär schaltet AN.
    # Mit geschuetzt=2000 reserviert der Heizstab die Leistung (schutz_w) → der
    # Binärverbraucher sieht zu wenig Pool und bleibt AUS. Genau das ist die in
    # der README dokumentierte Funktion von geschuetzte_mindestleistung.
    cfg = [
        {"name": "heizstab", "class": "controllable",
         "actual_power_entity": "sensor.hs", "allowed_modes": "auto", **CTRL_FALLBACKS},
        {"name": "luft", "class": "binary",
         "switch_entity": "switch.luft", "allowed_modes": "auto", **BIN_FALLBACKS},
    ]

    def run(geschuetzt):
        ctrl = EMSController(cfg, residual_power_entity="sensor.s")
        states = {
            **_global(),
            **_controllable_w("heizstab", prio=1, min_w=0, max_w=5000, geschuetzt=geschuetzt),
            **_binary("luft", prio=2, power=1000, switch="off"),
            "sensor.hs": 0,
            "switch.luft": "off",
            "sensor.s": 2500,
        }
        res = ctrl.run_cycle(make_states(states))
        return _op_for(res["write_ops"], "input_boolean.ems_luft_anforderung_an")

    assert run(0)[1] == "turn_on"       # ohne Schutz: Binär bekommt den Pool
    assert run(2000)[1] == "turn_off"   # mit Schutz: Leistung reserviert → Binär aus


# ---------------------------------------------------------------------------
# Fremdsteuerung ("Force-Modus"): Leistung darf nicht in den Pool zurückfließen
# ---------------------------------------------------------------------------

def test_extern_erzwungener_binaerverbraucher_blaeht_pool_nicht_auf():
    # luft (Prio 9, 2000 W) ist extern eingeschaltet: switch.luft = on, aber die
    # HEMS-Anforderung ist aus. Deren Last steckt bereits in residual (= 0) und darf
    # nicht als eigener Überschuss gutgeschrieben werden – sonst startet boiler.
    cfg = [
        {"name": "boiler", "class": "binary",
         "switch_entity": "switch.boiler", "allowed_modes": "auto", **BIN_FALLBACKS},
        {"name": "luft", "class": "binary",
         "switch_entity": "switch.luft", "allowed_modes": "auto", **BIN_FALLBACKS},
    ]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_binary("boiler", prio=1, power=1000, switch="off"),
        **_binary("luft", prio=9, power=2000, switch="on", anforderung="off"),
        "switch.boiler": "off",
        "switch.luft": "on",
        "sensor.s": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    assert res["status"]["pool_w"] == pytest.approx(0.0)
    assert _op_for(res["write_ops"], "input_boolean.ems_boiler_anforderung_an")[1] == "turn_off"


def test_extern_erzwungenes_regelbares_geraet_blaeht_pool_nicht_auf():
    # Wallbox/Heizstab lädt extern mit 3000 W, HEMS-Anforderung = 0. Der Istwert
    # darf nicht in den Pool zurückgerechnet werden.
    ctrl = EMSController(
        [{"name": "heizstab", "class": "controllable",
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}],
        residual_power_entity="sensor.s",
    )
    states = {
        **_global(),
        **_controllable_w("heizstab", min_w=500, max_w=3000, setpoint=0),
        "sensor.s": 0,
        "sensor.heizstab_ist": 3000,
    }
    res = ctrl.run_cycle(make_states(states))
    assert res["status"]["pool_w"] == pytest.approx(0.0)
    op = _op_for(res["write_ops"], "input_number.ems_heizstab_anforderung_leistung_w")
    assert op is None   # Sollwert bleibt 0 – keine Anforderung wegen Fremdlast


# ---------------------------------------------------------------------------
# Ampere-Modus: Umrechnung, Floor-Rounding, Phasenwahl, Entitätsnamen
# ---------------------------------------------------------------------------

def test_ampere_device_writes_floored_ampere_and_phase():
    # Wallbox (entity_prefix=wallbox, ampere, phases="1,3"). Pool = 5000 W bei
    # 230 V Fallback. 3-phasig: floor(5000 / 690) = 7 A; Phasenwahl = 3.
    ctrl = EMSController(
        [{"name": "wallbox_1", "class": "controllable",
          "actual_power_entity": "sensor.wb", "entity_prefix": "wallbox",
          "allowed_modes": "auto", "output_unit": "ampere", "phases": "1,3", **CTRL_FALLBACKS}],
        residual_power_entity="sensor.s",
    )
    states = {
        **_global(),
        "input_boolean.ems_wallbox_freigabe": "on",
        "input_boolean.ems_wallbox_technische_freigabe": "on",
        "input_select.ems_wallbox_modus": "auto",
        "input_number.ems_wallbox_prioritat": 1,
        "input_number.ems_wallbox_min_technisch_a": 6,
        "input_number.ems_wallbox_max_technisch_a": 16,
        "input_number.ems_wallbox_geschutzte_mindestleistung_a": 0,
        "input_number.ems_wallbox_reserve_w": 0,
        "input_number.ems_wallbox_hoch_regelzeit_s": 0,
        "input_number.ems_wallbox_runter_regelzeit_s": 0,
        "input_number.ems_wallbox_max_anderung_pro_schritt_a": 16,
        "input_number.ems_wallbox_min_anderung_pro_schritt_a": 0,
        "input_number.ems_wallbox_anforderung_leistung_a": 0,
        # Bei phases "1,3" ist der Phasenhelfer ein Schreibziel und damit Pflicht.
        "input_number.ems_wallbox_anzahl_phase": 1,
        "sensor.wb": 0,
        "sensor.s": 5000,
    }
    res = ctrl.run_cycle(make_states(states))
    amp   = _op_for(res["write_ops"], "input_number.ems_wallbox_anforderung_leistung_a")
    phase = _op_for(res["write_ops"], "input_number.ems_wallbox_anzahl_phase")
    assert amp is not None and amp[2]["value"] == 7        # floor(5000/690) = 7 A
    assert phase is not None and phase[2]["value"] == 3.0  # 3-phasig gewählt


# ---------------------------------------------------------------------------
# AC-Speicher: Pool-Bereinigung, Hausdefizit, Mehrspeicher-Aufteilung
# ---------------------------------------------------------------------------
#
# Die vier Formeln residual_bereinigt_w, pool_roh_w, entlade_basis_w und
# hausdefizit_w tragen das gesamte Risiko der Speicher-Erweiterung. Die Tests
# hier fahren sie über den vollständigen Zyklus.

def _battery_cfg(name, *, prefix=None, capacity=10.0):
    return {
        "name": name,
        "class": "battery",
        "entity_prefix": prefix or name,
        "allowed_modes": "auto",
        "soc_entity": f"sensor.{name}_soc",
        "charge_power_entity": f"sensor.{name}_lade_w",
        "discharge_power_entity": f"sensor.{name}_entlade_w",
        "available_charge_power_entity": f"sensor.{name}_lade_limit",
        "available_discharge_power_entity": f"sensor.{name}_entlade_limit",
        "capacity_kwh": capacity,
    }


def _battery(name, *, prefix=None, soc=50, lade_ist=0, entlade_ist=0, sollwert=0,
             betriebsart="auto", anforderung_betriebsart="standby",
             prio=1, entlade_prio=50, lade_limit=5000, entlade_limit=5000,
             min_lade=0, min_entlade=0, soc_min=10, soc_max=100):
    p = prefix or name
    return {
        f"sensor.{name}_soc":       soc,
        f"sensor.{name}_lade_w":    lade_ist,
        f"sensor.{name}_entlade_w": entlade_ist,
        f"sensor.{name}_lade_limit":    lade_limit,
        f"sensor.{name}_entlade_limit": entlade_limit,
        f"input_number.ems_{p}_anforderung_leistung_w":       sollwert,
        f"input_select.ems_{p}_anforderung_betriebsart":      anforderung_betriebsart,
        f"input_boolean.ems_{p}_freigabe":                    "on",
        f"input_boolean.ems_{p}_technische_freigabe":         "on",
        f"input_select.ems_{p}_modus":                        "auto",
        f"input_select.ems_{p}_betriebsart":                  betriebsart,
        f"input_boolean.ems_{p}_laden_erlaubt":               "on",
        f"input_boolean.ems_{p}_entladen_erlaubt":            "on",
        f"input_boolean.ems_{p}_netzladen_aktiv":             "off",
        f"input_number.ems_{p}_prioritat":                    prio,
        f"input_number.ems_{p}_entlade_prioritat":            entlade_prio,
        f"input_number.ems_{p}_min_ladeleistung_w":           min_lade,
        f"input_number.ems_{p}_min_entladeleistung_w":        min_entlade,
        f"input_number.ems_{p}_soc_min_prozent":              soc_min,
        f"input_number.ems_{p}_soc_max_prozent":              soc_max,
        f"input_number.ems_{p}_umschalt_totzone_w":           0,
        f"input_number.ems_{p}_hoch_regelzeit_s":             0,
        f"input_number.ems_{p}_runter_regelzeit_s":           0,
        f"input_number.ems_{p}_max_anderung_pro_schritt_w":   100000,
        f"input_number.ems_{p}_min_anderung_pro_schritt_w":   0,
        f"input_number.ems_{p}_geschutzte_mindestleistung_w": 0,
        f"input_number.ems_{p}_reserve_w":                    0,
        f"input_number.ems_{p}_netzlade_leistung_w":          0,
    }


def test_pool_ohne_speicher_unveraendert():
    """Regression: ohne konfigurierten Speicher ist die Erweiterung eine
    Identitätsoperation."""
    cfg = [{"name": "heizstab", "class": "controllable",
            "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_controllable_w("heizstab", min_w=500, max_w=3000, setpoint=1000),
        "sensor.s": 1500,
        "sensor.heizstab_ist": 1000,
    }
    status = ctrl.run_cycle(make_states(states))["status"]
    assert status["netz_support_w"] == 0
    assert status["residual_bereinigt_w"] == status["residual_w"]
    assert status["pool_w"] == pytest.approx(2500)     # 1500 + 1000 zurückaddiert
    assert status["hausdefizit_w"] == 0


def test_entladung_erhoeht_pool_nicht():
    """H-1 – der wichtigste Test des Features. Ohne Bereinigung läse das HEMS
    die eigene Entladung als PV-Überschuss und schaukelte sich auf."""
    ctrl = EMSController([_battery_cfg("speicher")], residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("speicher", entlade_ist=3000),
        "sensor.s": 0,          # Zähler sieht durch die Entladung ausgeglichen aus
    }
    status = ctrl.run_cycle(make_states(states))["status"]
    assert status["netz_support_w"] == 3000
    assert status["residual_bereinigt_w"] == pytest.approx(-3000)
    assert status["pool_w"] == 0


def test_defizit_sichtbar_trotz_entladung():
    """H-2 – deckt der Speicher die Hauslast, darf das Defizit nicht verschwinden."""
    cfg = [_battery_cfg("speicher"),
           {"name": "heizstab", "class": "controllable",
            "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("speicher", entlade_ist=2000),
        **_controllable_w("heizstab", min_w=500, max_w=3000, actual=0, setpoint=0),
        "sensor.s": 0,
        "sensor.heizstab_ist": 0,
    }
    status = ctrl.run_cycle(make_states(states))["status"]
    assert status["current_deficit_w"] == pytest.approx(2000)


def test_hausdefizit_schliesst_hems_lasten_aus():
    """Kernanforderung: der Speicher deckt den Hausverbrauch, nicht den Heizstab."""
    cfg = [_battery_cfg("speicher"),
           {"name": "heizstab", "class": "controllable",
            "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("speicher"),
        **_controllable_w("heizstab", min_w=500, max_w=3000, setpoint=2000),
        "sensor.s": -2500,           # 500 W Hausgrundlast + 2000 W Heizstab
        "sensor.heizstab_ist": 2000,
    }
    status = ctrl.run_cycle(make_states(states))["status"]
    assert status["hausdefizit_w"] == pytest.approx(500)
    assert status["current_deficit_w"] == pytest.approx(2500)


def test_heizstab_laeuft_nicht_aus_speicher():
    """Ende-zu-Ende: die Entladeanforderung deckt nur die Hausgrundlast."""
    cfg = [_battery_cfg("speicher"),
           {"name": "heizstab", "class": "controllable",
            "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("speicher"),
        **_controllable_w("heizstab", min_w=500, max_w=3000, setpoint=2000),
        "sensor.s": -2500,
        "sensor.heizstab_ist": 2000,
        "input_number.ems_ac_speicher_entlade_abschlag_w": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    op = _op_for(res["write_ops"], "input_number.ems_speicher_anforderung_leistung_w")
    assert op[2]["value"] == pytest.approx(-500)


def test_fremdgesteuerter_heizstab_wird_nicht_gedeckt():
    """D-B14/F-5: der von Hand eingeschaltete Heizstab senkt hausdefizit_w um
    seine volle Istleistung – er bleibt Überschussverbraucher."""
    cfg = [_battery_cfg("speicher"),
           {"name": "heizstab", "class": "controllable",
            "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("speicher"),
        **_controllable_w("heizstab", min_w=500, max_w=3000, setpoint=0),
        "sensor.s": -2500,
        "sensor.heizstab_ist": 2000,      # läuft, obwohl das HEMS 0 anfordert
        "input_number.ems_ac_speicher_entlade_abschlag_w": 0,
    }
    status = ctrl.run_cycle(make_states(states))["status"]
    assert status["hems_last_w"] == 0                 # Force-Anteil zählt nicht
    assert status["hems_last_gemessen_w"] == 2000     # gemessen zählt er sehr wohl
    assert status["hausdefizit_w"] == pytest.approx(500)


def test_pool_ignoriert_fremdlast_weiterhin():
    """Gegenprobe: die zwei Summen driften nur auf der Entladeseite."""
    cfg = [_battery_cfg("speicher"),
           {"name": "heizstab", "class": "controllable",
            "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("speicher"),
        **_controllable_w("heizstab", min_w=500, max_w=3000, setpoint=0),
        "sensor.s": 1000,
        "sensor.heizstab_ist": 2000,
    }
    status = ctrl.run_cycle(make_states(states))["status"]
    assert status["pool_roh_w"] == pytest.approx(1000)          # ohne Fremdlast
    assert status["entlade_basis_w"] == pytest.approx(3000)     # mit Fremdlast


def test_pool_und_hausdefizit_schliessen_sich_aus():
    """4.4 – die beiden Grössen sind komplementär, auch mit Fremdlast."""
    cfg = [_battery_cfg("speicher"),
           {"name": "heizstab", "class": "controllable",
            "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    for residual, ist in [(-4000, 0), (-4000, 2000), (0, 0), (3000, 1000), (5000, 0)]:
        states = {
            **_global(),
            **_battery("speicher"),
            **_controllable_w("heizstab", min_w=500, max_w=3000, setpoint=0),
            "sensor.s": residual,
            "sensor.heizstab_ist": ist,
        }
        status = ctrl.run_cycle(make_states(states))["status"]
        assert status["pool_w"] == 0 or status["hausdefizit_w"] == 0
        assert status["entlade_basis_w"] >= status["pool_roh_w"] - 1e-6


def test_speicher_in_residual_false():
    """D-B03: sitzt der Sensor nicht an der Netzübergabe, wird nicht bereinigt."""
    ctrl = EMSController([_battery_cfg("speicher")], residual_power_entity="sensor.s",
                         speicher_in_residual_enthalten=False)
    states = {**_global(), **_battery("speicher", entlade_ist=3000), "sensor.s": 0}
    status = ctrl.run_cycle(make_states(states))["status"]
    assert status["residual_bereinigt_w"] == 0
    assert status["netz_support_w"] == 3000        # gemessen, aber nicht abgezogen


def test_zwei_speicher_teilen_hausdefizit():
    """H-3: die Summe deckt das Defizit einmal, nicht je Speicher einmal."""
    cfg = [_battery_cfg("sp1"), _battery_cfg("sp2")]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("sp1", entlade_prio=10, entlade_limit=2000),
        **_battery("sp2", entlade_prio=20, entlade_limit=5000),
        "sensor.s": -2500,
        "input_number.ems_ac_speicher_entlade_abschlag_w": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    v1 = _op_for(res["write_ops"], "input_number.ems_sp1_anforderung_leistung_w")[2]["value"]
    v2 = _op_for(res["write_ops"], "input_number.ems_sp2_anforderung_leistung_w")[2]["value"]
    assert v1 == pytest.approx(-2000)
    assert v2 == pytest.approx(-500)
    assert v1 + v2 == pytest.approx(-2500)


def test_drei_speicher_entlade_prioritaetsreihenfolge():
    cfg = [_battery_cfg("sp1"), _battery_cfg("sp2"), _battery_cfg("sp3")]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("sp1", entlade_prio=20, entlade_limit=5000),
        **_battery("sp2", entlade_prio=10, entlade_limit=2000),
        **_battery("sp3", entlade_prio=30, entlade_limit=5000),
        "sensor.s": -2480,
        "input_number.ems_ac_speicher_entlade_abschlag_w": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    werte = {
        n: _op_for(res["write_ops"], f"input_number.ems_{n}_anforderung_leistung_w")
        for n in ("sp1", "sp2", "sp3")
    }
    assert werte["sp2"][2]["value"] == pytest.approx(-2000)   # niedrigste Prio-Zahl zuerst
    assert werte["sp1"][2]["value"] == pytest.approx(-480)
    assert werte["sp3"] is None                                # bleibt bei 0, kein Schreibvorgang


def test_entlade_prio_unabhaengig_von_lade_prio():
    """D-B17: 'lade mich zuletzt, entlade mich zuerst' ist eine gültige Konfiguration."""
    cfg = [_battery_cfg("sp1"), _battery_cfg("sp2")]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("sp1", prio=1, entlade_prio=90, entlade_limit=5000),
        **_battery("sp2", prio=90, entlade_prio=1, entlade_limit=5000),
        "sensor.s": -1000,
        "input_number.ems_ac_speicher_entlade_abschlag_w": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    assert _op_for(res["write_ops"],
                   "input_number.ems_sp2_anforderung_leistung_w")[2]["value"] == pytest.approx(-1000)
    assert _op_for(res["write_ops"], "input_number.ems_sp1_anforderung_leistung_w") is None


def test_entlade_prio_gleichstand_config_reihenfolge():
    """Stabile Sortierung: bei Gleichstand entscheidet die Konfiguration."""
    cfg = [_battery_cfg("sp1"), _battery_cfg("sp2")]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("sp1", entlade_prio=50, entlade_limit=1000),
        **_battery("sp2", entlade_prio=50, entlade_limit=5000),
        "sensor.s": -1500,
        "input_number.ems_ac_speicher_entlade_abschlag_w": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    assert _op_for(res["write_ops"],
                   "input_number.ems_sp1_anforderung_leistung_w")[2]["value"] == pytest.approx(-1000)
    assert _op_for(res["write_ops"],
                   "input_number.ems_sp2_anforderung_leistung_w")[2]["value"] == pytest.approx(-500)


def test_entlade_abschlag_wirkt_einmal_systemweit():
    """10.3: bei n Speichern wäre ein Abschlag je Gerät n-fach wirksam."""
    cfg = [_battery_cfg("sp1"), _battery_cfg("sp2")]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("sp1", entlade_prio=10, entlade_limit=1000),
        **_battery("sp2", entlade_prio=20, entlade_limit=5000),
        "sensor.s": -2000,
        "input_number.ems_ac_speicher_entlade_abschlag_w": 20,
    }
    res = ctrl.run_cycle(make_states(states))
    v1 = _op_for(res["write_ops"], "input_number.ems_sp1_anforderung_leistung_w")[2]["value"]
    v2 = _op_for(res["write_ops"], "input_number.ems_sp2_anforderung_leistung_w")[2]["value"]
    assert v1 + v2 == pytest.approx(-1980)      # genau ein Abschlag von 20 W


def test_zu_kleine_zuteilung_rastet_auf_null_im_zyklus():
    cfg = [_battery_cfg("sp1"), _battery_cfg("sp2")]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("sp1", entlade_prio=10, entlade_limit=1000),
        **_battery("sp2", entlade_prio=20, entlade_limit=5000, min_entlade=800),
        "sensor.s": -1200,
        "input_number.ems_ac_speicher_entlade_abschlag_w": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    assert _op_for(res["write_ops"],
                   "input_number.ems_sp1_anforderung_leistung_w")[2]["value"] == pytest.approx(-1000)
    # sp2 bekäme 200 W, unterschreitet damit seine Mindestleistung -> bleibt aus
    assert _op_for(res["write_ops"], "input_number.ems_sp2_anforderung_leistung_w") is None


def test_netzladender_speicher_ist_keine_hauslast():
    """11.3 Regel 1: sonst deckt Speicher B das Netzladen von Speicher A."""
    cfg = [_battery_cfg("sp1"), _battery_cfg("sp2")]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("sp1", lade_ist=3000, sollwert=3000),
        **_battery("sp2"),
        "input_boolean.ems_sp1_netzladen_aktiv": "on",
        "sensor.s": -3000,
    }
    status = ctrl.run_cycle(make_states(states))["status"]
    assert status["hems_last_w"] == 0             # nicht in den Pool zurückrechnen
    assert status["hems_last_gemessen_w"] == 3000  # aber als Last sichtbar
    assert status["hausdefizit_w"] == 0            # sp2 deckt es nicht


def test_speicher_prio_1_verdraengt_heizstab():
    """D-B02: der Speicher konkurriert beim Laden in derselben Sortierung."""
    cfg = [_battery_cfg("speicher"),
           {"name": "heizstab", "class": "controllable",
            "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("speicher", prio=1, lade_limit=5000),
        **_controllable_w("heizstab", prio=50, min_w=500, max_w=3000),
        "sensor.s": 4000,
        "sensor.heizstab_ist": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    assert _op_for(res["write_ops"],
                   "input_number.ems_speicher_anforderung_leistung_w")[2]["value"] == pytest.approx(3500)


def test_speicher_prio_50_bekommt_rest():
    cfg = [_battery_cfg("speicher"),
           {"name": "heizstab", "class": "controllable",
            "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("speicher", prio=50, lade_limit=5000),
        **_controllable_w("heizstab", prio=1, min_w=500, max_w=3000),
        "sensor.s": 4000,
        "sensor.heizstab_ist": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    assert _op_for(res["write_ops"],
                   "input_number.ems_speicher_anforderung_leistung_w")[2]["value"] == pytest.approx(1000)


def test_defekter_speicher_blockiert_flotte_nicht():
    """10.3: ein Speicher ohne gültige Messwerte fällt heraus, der andere läuft."""
    cfg = [_battery_cfg("sp1"), _battery_cfg("sp2")]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("sp1", entlade_prio=10, entlade_limit=5000),
        **_battery("sp2", entlade_prio=20, entlade_limit=5000),
        "sensor.sp1_soc": "unavailable",
        "sensor.s": -1000,
        "input_number.ems_ac_speicher_entlade_abschlag_w": 0,
    }
    res = ctrl.run_cycle(make_states(states))
    assert _op_for(res["write_ops"], "input_number.ems_sp1_anforderung_leistung_w") is None
    assert _op_for(res["write_ops"],
                   "input_number.ems_sp2_anforderung_leistung_w")[2]["value"] == pytest.approx(-1000)


def test_plausibilitaetswarnung_geloggt(caplog):
    """12.4: Entladung bei gleichzeitigem Überschuss ist fast immer ein
    Konfigurationsfehler – die Warnung ist bewusst nicht an debug_output gekoppelt."""
    ctrl = EMSController([_battery_cfg("speicher")], residual_power_entity="sensor.s",
                         speicher_in_residual_enthalten=False)
    states = {**_global(), **_battery("speicher", entlade_ist=3000), "sensor.s": 4000}
    with caplog.at_level("WARNING"):
        ctrl.run_cycle(make_states(states))
    assert any("entlädt in den PV-Überschuss" in r.message for r in caplog.records)


def test_lockout_schreibt_sicheren_zustand():
    """12.1: bei Lockout wird der sichere Zustand AKTIV geschrieben."""
    ctrl = EMSController([_battery_cfg("speicher")], residual_power_entity="sensor.s")
    states = {
        **_global(),
        **_battery("speicher", entlade_ist=4000, sollwert=-4000,
                   anforderung_betriebsart="entladen"),
        "sensor.s": "unavailable",
    }
    res = ctrl.run_cycle(make_states(states))
    assert _op_for(res["write_ops"],
                   "input_number.ems_speicher_anforderung_leistung_w")[2]["value"] == 0.0
    assert _op_for(res["write_ops"],
                   "input_select.ems_speicher_anforderung_betriebsart")[2]["option"] == "standby"


def test_unvollstaendige_speicherkonfig_wird_uebersprungen():
    """Fehlerhafte Einträge werden einzeln übersprungen, die übrigen bleiben aktiv."""
    cfg = [
        {"name": "kaputt", "class": "battery"},                     # ohne soc_entity
        {"name": "ohne_sensor", "class": "battery", "soc_entity": "sensor.x"},
        _battery_cfg("sp1"),
    ]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {**_global(), **_battery("sp1"), "sensor.s": 0}
    status = ctrl.run_cycle(make_states(states))["status"]
    assert [d["id"] for d in status["devices"]] == ["sp1"]


# ---------------------------------------------------------------------------
# Schreibziel-Gesundheit und Write-Fehler (B-2)
# ---------------------------------------------------------------------------

def _heizstab_cfg():
    return {"name": "heizstab", "class": "controllable",
            "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto",
            **CTRL_FALLBACKS}


def _heizstab_states(**over):
    states = {
        **_global(),
        **_controllable_w("heizstab", min_w=500, max_w=3000),
        "sensor.s": 3000,
        "sensor.heizstab_ist": 0,
    }
    states.update(over)
    return states


def _dev(res, device_id="heizstab"):
    return next(d for d in res["status"]["devices"] if d["id"] == device_id)


def test_fehlendes_schreibziel_verhindert_zuteilung():
    ctrl = EMSController([_heizstab_cfg()], residual_power_entity="sensor.s")
    states = _heizstab_states()
    del states["input_number.ems_heizstab_anforderung_leistung_w"]
    res = ctrl.run_cycle(make_states(states))
    device = _dev(res)
    assert device["runtime_active"] is False
    assert device["inactive_reasons"] == ["schreibziel_fehlt"]
    assert device["alloc_w"] == 0.0
    assert res["status"]["pool_w"] == 3000.0     # Pool bleibt unangetastet


def test_nicht_verfuegbares_schreibziel_verhindert_zuteilung():
    ctrl = EMSController([_heizstab_cfg()], residual_power_entity="sensor.s")
    res = ctrl.run_cycle(make_states(_heizstab_states(**{
        "input_number.ems_heizstab_anforderung_leistung_w": "unavailable",
    })))
    assert _dev(res)["inactive_reasons"] == ["schreibziel_nicht_verfuegbar"]


def test_speicher_ohne_negatives_minimum_ist_nicht_regelbar():
    """Mit min: 0 klemmt HA jede Entladeanforderung – der Speicher entlädt nie."""
    ctrl = EMSController([_battery_cfg("speicher")], residual_power_entity="sensor.s")
    states = {**_global(), **_battery("speicher"), "sensor.s": 0}
    st = make_states(states, attributes={
        "input_number.ems_speicher_anforderung_leistung_w": {"min": 0.0, "max": 5000.0},
    })
    device = _dev(ctrl.run_cycle(st), "speicher")
    assert device["runtime_active"] is False
    assert device["inactive_reasons"] == ["schreibziel_ungueltig"]


def test_speicher_ohne_betriebsart_optionen_ist_nicht_regelbar():
    ctrl = EMSController([_battery_cfg("speicher")], residual_power_entity="sensor.s")
    states = {**_global(), **_battery("speicher"), "sensor.s": 0}
    st = make_states(states, attributes={
        "input_number.ems_speicher_anforderung_leistung_w": {"min": -5000.0},
        "input_select.ems_speicher_anforderung_betriebsart": {"options": ["an", "aus"]},
    })
    assert _dev(ctrl.run_cycle(st), "speicher")["runtime_active"] is False


def test_inaktives_geraet_schreibt_weiter_den_sicheren_zustand():
    """Sonst bliebe der letzte Sollwert stehen, bis jemand das Add-on neu startet."""
    ctrl = EMSController([_heizstab_cfg()], residual_power_entity="sensor.s")
    res = ctrl.run_cycle(make_states(_heizstab_states(**{
        "input_number.ems_heizstab_anforderung_leistung_w": "unavailable",
    })))
    op = _op_for(res["write_ops"], "input_number.ems_heizstab_anforderung_leistung_w")
    assert op is not None and op[2]["value"] == 0.0


def test_inaktiver_speicher_schreibt_weiter_standby():
    ctrl = EMSController([_battery_cfg("speicher")], residual_power_entity="sensor.s")
    states = {**_global(), **_battery("speicher", sollwert=-2000,
                                      anforderung_betriebsart="entladen"),
              "sensor.s": 0}
    st = make_states(states, attributes={
        "input_number.ems_speicher_anforderung_leistung_w": {"min": 0.0},
    })
    res = ctrl.run_cycle(st)
    assert _op_for(res["write_ops"],
                   "input_number.ems_speicher_anforderung_leistung_w")[2]["value"] == 0.0
    assert _op_for(res["write_ops"],
                   "input_select.ems_speicher_anforderung_betriebsart")[2]["option"] == "standby"


def test_write_fehler_markiert_nur_das_betroffene_geraet():
    cfg = [_heizstab_cfg(),
           {"name": "luft", "class": "binary", "switch_entity": "switch.luft",
            "allowed_modes": "auto", **BIN_FALLBACKS}]
    ctrl = EMSController(cfg, residual_power_entity="sensor.s")
    states = {**_heizstab_states(), **_binary("luft", prio=2, power=1000)}

    res = ctrl.run_cycle(make_states(states))
    assert _dev(res)["runtime_active"] is True

    kaputt = _op_for(res["write_ops"], "input_number.ems_heizstab_anforderung_leistung_w")
    ctrl.report_write_results([
        WriteResult(op, ok=(op is not kaputt), error="" if op is not kaputt else "HTTP 400")
        for op in res["write_ops"]
    ])

    res = ctrl.run_cycle(make_states(states))
    assert _dev(res)["runtime_active"] is False
    assert _dev(res)["inactive_reasons"] == ["schreiben_fehlgeschlagen"]
    assert _dev(res)["write_error"] == "HTTP 400"
    # Das andere Gerät regelt unbeeindruckt weiter.
    assert _dev(res, "luft")["runtime_active"] is True
    assert res["status"]["devices_inactive_runtime"] == ["heizstab"]


def test_repariertes_ziel_wird_ueber_sicheren_retry_wieder_aktiv():
    ctrl = EMSController([_heizstab_cfg()], residual_power_entity="sensor.s")
    states = _heizstab_states()

    ctrl.run_cycle(make_states(states))
    ctrl.report_write_results([WriteResult(
        WriteOp("input_number", "set_value", {}, "heizstab"), False, "HTTP 500")])

    res = ctrl.run_cycle(make_states(states))
    assert _dev(res)["runtime_active"] is False

    # Der sichere Schreibvorgang geht durch -> nächster Zyklus wieder aktiv.
    ctrl.report_write_results([WriteResult(op, True) for op in res["write_ops"]])
    res = ctrl.run_cycle(make_states(states))
    assert _dev(res)["runtime_active"] is True
    assert _dev(res)["alloc_w"] > 0.0


def test_schreibziel_erscheint_in_der_entitaetsdiagnose():
    ctrl = EMSController([_heizstab_cfg()], residual_power_entity="sensor.s")
    states = _heizstab_states()
    del states["input_number.ems_heizstab_anforderung_leistung_w"]
    diagnose = _dev(ctrl.run_cycle(make_states(states)))["entity_diagnostics"]
    assert diagnose["input_number.ems_heizstab_anforderung_leistung_w"] == {
        "role": "request", "state": "missing", "source": "ha",
    }
