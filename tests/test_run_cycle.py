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
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto"}],
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
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto"}],
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
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto"}],
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
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto"}],
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
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto"}],
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
         "actual_power_entity": "sensor.hs", "allowed_modes": "auto"},
        {"name": "luft", "class": "binary",
         "switch_entity": "switch.luft", "allowed_modes": "auto"},
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
         "switch_entity": "switch.boiler", "allowed_modes": "auto"},
        {"name": "luft", "class": "binary",
         "switch_entity": "switch.luft", "allowed_modes": "auto"},
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
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto"}],
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
          "allowed_modes": "auto", "output_unit": "ampere", "phases": "1,3"}],
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
        "sensor.wb": 0,
        "sensor.s": 5000,
    }
    res = ctrl.run_cycle(make_states(states))
    amp   = _op_for(res["write_ops"], "input_number.ems_wallbox_anforderung_leistung_a")
    phase = _op_for(res["write_ops"], "input_number.ems_wallbox_anzahl_phase")
    assert amp is not None and amp[2]["value"] == 7        # floor(5000/690) = 7 A
    assert phase is not None and phase[2]["value"] == 3.0  # 3-phasig gewählt
