"""Tests für ControllableDevice: Zuteilung, Rampe, Phasenwahl, Schreiboperationen."""

import pytest

from ems.devices import ControllableDevice

from conftest import make_states


def make_watt(prio=1, min_w=0.0, max_w=3000.0, geschuetzt=0.0):
    d = ControllableDevice(
        id="heizstab",
        allowed_modes=["auto"],
        entity_actual_w="sensor.heizstab_ist",
        entity_anforderung_w="input_number.ems_heizstab_anforderung_leistung_w",
    )
    d.eligible = True
    d.priority = prio
    d.min_technisch_w = min_w
    d.max_technisch_w = max_w
    d.geschuetzte_mindestleistung_w = geschuetzt
    return d


def make_ampere(allowed_phases):
    d = ControllableDevice(
        id="wallbox",
        allowed_modes=["auto"],
        entity_actual_w="sensor.wb_ist",
        entity_anforderung_w="input_number.ems_wallbox_anforderung_leistung_a",
        output_unit="ampere",
        allowed_phases=allowed_phases,
    )
    d.eligible = True
    d._voltage_l1 = d._voltage_l2 = d._voltage_l3 = 230.0
    return d


# ---- Pool-Rückrechnung / Entlastung ----

def test_current_w_capped_at_anforderung():
    """Extern erzwungenes Laden über dem Sollwert zählt nicht in den Pool."""
    d = make_watt(min_w=1000.0, max_w=11000.0)
    d._actual_w = 11000.0
    d._anforderung_current_w = 0.0
    assert d.current_w == 0.0
    d._anforderung_current_w = 3000.0
    assert d.current_w == 3000.0
    # Gerät zieht weniger als angefordert -> Istwert zählt
    d._actual_w = 2000.0
    assert d.current_w == 2000.0


def test_current_w_zero_when_not_eligible():
    d = make_watt()
    d.eligible = False
    d._actual_w = 3000.0
    d._anforderung_current_w = 3000.0
    assert d.current_w == 0.0


def test_max_relief_capped_at_anforderung():
    d = make_watt(min_w=1000.0, max_w=11000.0)
    d._actual_w = 11000.0
    d._anforderung_current_w = 0.0
    assert d.max_relief_w == 0.0
    d._anforderung_current_w = 3000.0
    assert d.max_relief_w == 2000.0


# ---- Zuteilung (2-Pass) ----

def test_allocate_minimum_then_surplus():
    d = make_watt(min_w=1000.0, max_w=3000.0)
    remaining = d.allocate_minimum(5000.0)
    assert d.alloc_w == 1000.0
    assert remaining == 4000.0
    remaining = d.allocate_surplus(remaining)
    assert d.alloc_w == 3000.0          # bis max aufgefüllt
    assert remaining == 2000.0


def test_allocate_minimum_insufficient_pool_keeps_device_off():
    d = make_watt(min_w=2000.0, max_w=3000.0)
    remaining = d.allocate_minimum(1500.0)
    assert d.alloc_w == 0.0
    assert remaining == 1500.0          # Pool unangetastet
    # Ohne Minimum in Pass 1 bleibt das Gerät auch im Überschuss-Pass aus
    remaining = d.allocate_surplus(1500.0)
    assert d.alloc_w == 0.0


def test_allocate_priority_order_minimum_first():
    high = make_watt(prio=1, min_w=1000.0, max_w=5000.0)
    low  = make_watt(prio=2, min_w=1000.0, max_w=5000.0)
    pool = 2500.0
    # Pass 1: beide bekommen ihr Minimum
    pool = high.allocate_minimum(pool)
    pool = low.allocate_minimum(pool)
    assert high.alloc_w == 1000.0 and low.alloc_w == 1000.0 and pool == 500.0
    # Pass 2: Überschuss zuerst an höhere Priorität
    pool = high.allocate_surplus(pool)
    pool = low.allocate_surplus(pool)
    assert high.alloc_w == 1500.0
    assert low.alloc_w == 1000.0


def test_geschuetzte_mindestleistung_does_not_gate_startup():
    # geschuetzt (2000) > min_technisch (500): Pool (1500) trägt das technische
    # Minimum, aber nicht die volle geschützte Leistung. Das Gerät MUSS laufen
    # (ab min_technisch, dann den Überschuss bis zum Pool aufnehmen) – die
    # geschützte Mindestleistung darf NICHT als Startschwelle wirken.
    d = make_watt(min_w=500.0, max_w=3000.0, geschuetzt=2000.0)
    remaining = d.allocate_minimum(1500.0)
    assert d.alloc_w == 500.0           # technisches Minimum beansprucht, nicht 0
    assert remaining == 1000.0
    remaining = d.allocate_surplus(remaining)
    assert d.alloc_w == 1500.0          # Überschuss bis zum Pool ausgeschöpft
    assert remaining == 0.0


def test_geschuetzte_mindestleistung_no_priority_inversion():
    # Hoch-priores Gerät mit großer geschützter Mindestleistung darf nicht
    # ausgeschaltet werden, während ein nieder-priores Gerät läuft. Beide
    # erhalten ihr technisches Minimum; kein Gerät wird wegen geschuetzt > pool
    # zugunsten eines nieder-prioren Geräts abgeschaltet.
    high = make_watt(prio=1, min_w=500.0, max_w=3000.0, geschuetzt=2000.0)
    low  = make_watt(prio=2, min_w=500.0, max_w=3000.0, geschuetzt=0.0)
    pool = 1000.0
    pool = high.allocate_minimum(pool)
    pool = low.allocate_minimum(pool)
    assert high.alloc_w == 500.0        # hoch-prior läuft (nicht 0)
    assert low.alloc_w == 500.0
    assert pool == 0.0
    pool = high.allocate_surplus(pool)
    pool = low.allocate_surplus(pool)
    assert high.alloc_w == 500.0
    assert low.alloc_w == 500.0


# ---- Parameter-Distinktheit: min_technisch vs. geschuetzte_mindestleistung ----
# Beweist, dass min_technisch_w die Start-/Stopp-Schwelle ist und
# geschuetzte_mindestleistung_w die Zuteilung NICHT verändert. Hätte diese Matrix
# existiert, wäre der Bug (geschuetzt wirkte als Startschwelle) sofort aufgefallen.

@pytest.mark.parametrize("min_w,geschuetzt,pool,expected_alloc", [
    (500.0,    0.0, 1500.0, 1500.0),   # läuft, keine geschützte Leistung
    (500.0, 2000.0, 1500.0, 1500.0),   # geschuetzt > Pool darf NICHT ausschalten (Regression)
    (2000.0,   0.0, 1500.0,    0.0),   # echtes technisches Minimum nicht erreicht → aus
    (2000.0,2000.0, 1500.0,    0.0),   # identisch: geschuetzt ändert nichts
    (500.0, 9000.0, 5000.0, 3000.0),   # bei max_technisch_w gedeckelt, geschuetzt irrelevant
])
def test_allocation_uses_min_technisch_not_geschuetzte(min_w, geschuetzt, pool, expected_alloc):
    d = make_watt(min_w=min_w, max_w=3000.0, geschuetzt=geschuetzt)
    remaining = d.allocate_minimum(pool)
    d.allocate_surplus(remaining)
    assert d.alloc_w == expected_alloc


def test_status_dict_ampere_exposes_schutz_a():
    # Ampere-Geräte geben schutz_a (= schutz_w / (Phasen×Spannung)) im Status aus, damit
    # Ampere-Konsumenten (Energy Pilot) den Schutz einheitengleich vergleichen können.
    d = make_ampere(allowed_phases=[1])
    d._raw_geschuetzt = 6.0   # 6 A Mindestleistung (nativ)
    d._raw_max = 16.0         # 16 A -> max_technisch_w = 3680 W, damit die Deckelung nicht greift
    d._apply_raw_to_watt()    # eff = 230 V (1-phasig) -> geschuetzt_w = 1380 W, schutz_w = 1380 W
    status = d.to_status_dict()
    assert status["output_unit"] == "ampere"
    assert status["schutz_w"] == 1380.0
    assert status["schutz_a"] == 6.0   # 1380 / 230


def test_schutz_w_combines_geschuetzt_reserve_puffer_and_caps_at_max():
    # geschuetzte_mindestleistung wirkt ausschließlich über schutz_w (Schutz gegen
    # binäre Verbraucher) – schutz_w = geschuetzt + reserve + globaler Puffer,
    # gedeckelt auf max_technisch_w. Das ist die dokumentierte, eigentliche Rolle.
    d = make_watt()
    d._raw_max        = 2500.0
    d._raw_geschuetzt = 2000.0
    d.reserve_w        = 300.0
    d._global_puffer_w = 400.0
    d._apply_raw_to_watt()
    assert d.geschuetzte_mindestleistung_w == 2000.0
    assert d._schutz_w == 2500.0   # 2000 + 300 + 400 = 2700, gedeckelt auf max 2500


# ---- Rampenbegrenzung ----

def test_ramp_up_limited_by_step_when_aged():
    d = make_watt(min_w=500.0, max_w=3000.0)
    d._alloc_w = 2000.0
    d._anforderung_current_w = 0.0
    d._anforderung_age_s = 100.0
    d.hoch_regelzeit_s = 60.0
    d.max_anderung_pro_schritt_w = 1000.0
    d.calculate_ramp(0.0)
    assert d.new_w == 1000.0            # ein Schritt nach oben


def test_ramp_up_blocked_when_too_young():
    d = make_watt(min_w=500.0, max_w=3000.0)
    d._alloc_w = 2000.0
    d._anforderung_current_w = 500.0
    d._anforderung_age_s = 10.0
    d.hoch_regelzeit_s = 60.0
    d.calculate_ramp(0.0)
    assert d.new_w == 500.0             # noch nicht alt genug


def test_ramp_down_immediate_on_deficit():
    d = make_watt(min_w=500.0, max_w=3000.0)
    d._alloc_w = 500.0
    d._anforderung_current_w = 2500.0
    d._anforderung_age_s = 0.0
    d.runter_regelzeit_s = 60.0
    d.calculate_ramp(current_deficit_w=300.0)
    assert d.new_w == 500.0             # sofort herunter trotz junger Anforderung


def test_ramp_not_eligible_is_zero():
    d = make_watt()
    d.eligible = False
    d._alloc_w = 2000.0
    d.calculate_ramp(0.0)
    assert d.new_w == 0.0


# ---- Schreiboperationen / Deadband ----

def test_write_only_on_change_watt():
    d = make_watt(max_w=3000.0)
    d._anforderung_current_w = 1000.0
    d._new_w = 1000.0
    d.deadband_w = 0.0
    assert d.get_write_ops() == []      # keine Änderung → kein Schreibvorgang


def test_write_emitted_on_change_watt():
    d = make_watt(max_w=3000.0)
    d._anforderung_current_w = 1000.0
    d._new_w = 1500.0
    ops = d.get_write_ops()
    assert [(op.domain, op.service, op.data, op.owner) for op in ops] == [
        ("input_number", "set_value",
         {"entity_id": "input_number.ems_heizstab_anforderung_leistung_w", "value": 1500.0},
         "heizstab")
    ]


def test_deadband_suppresses_small_change():
    d = make_watt(max_w=3000.0)
    d._anforderung_current_w = 1000.0
    d._new_w = 1050.0
    d.deadband_w = 100.0                # Änderung < Deadband
    assert d.get_write_ops() == []
    assert d.new_w == 1000.0            # auf alten Wert zurückgesetzt


# ---- Phasenwahl (A3) ----

def test_phase_initial_start_picks_highest_that_fits():
    d = make_ampere(allowed_phases=[1, 3])
    d._raw_min = 6.0                    # 6 A Minimum
    d._anforderung_current_w = 0.0      # Ladestart
    d._current_phases = 1
    # Pool 5000 W: 3-phasig floor(5000/690)=7 >= 6 → 3 Phasen
    d.select_phases(5000.0, now_ts=1000.0)
    assert d._current_phases == 3


def test_phase_initial_start_falls_back_to_one_phase_on_low_surplus():
    d = make_ampere(allowed_phases=[1, 3])
    d._raw_min = 6.0
    d._anforderung_current_w = 0.0      # Ladestart
    d._current_phases = 1
    # Pool 2000 W: 3-phasig floor(2000/690)=2 < 6 → 1-phasig floor(2000/230)=8 >= 6
    d.select_phases(2000.0, now_ts=1000.0)
    assert d._current_phases == 1


def test_phase_single_phase_config_never_switches():
    d = make_ampere(allowed_phases=[1])
    d._raw_min = 6.0
    d._anforderung_current_w = 0.0
    d.select_phases(10000.0, now_ts=1000.0)
    assert d._current_phases == 1


# ---- Charakterisierung: Fallback-Verhalten vor dem Umbau ----

def ctrl_states(**overrides):
    """HA-Schnappschuss eines Watt-Geräts mit dem Präfix 'heizstab'."""
    states = {
        "sensor.heizstab_ist":                                     "0",
        "input_number.ems_heizstab_anforderung_leistung_w":        "0",
        "input_number.ems_heizstab_prioritat":                     "5",
        "input_number.ems_heizstab_reserve_w":                     "0",
        "input_number.ems_heizstab_hoch_regelzeit_s":              "0",
        "input_number.ems_heizstab_runter_regelzeit_s":            "0",
        "input_number.ems_heizstab_min_technisch_w":               "500",
        "input_number.ems_heizstab_max_technisch_w":               "3000",
        "input_number.ems_heizstab_geschutzte_mindestleistung_w":  "0",
        "input_number.ems_heizstab_max_anderung_pro_schritt_w":    "800",
        "input_number.ems_heizstab_min_anderung_pro_schritt_w":    "0",
    }
    states.update(overrides)
    return make_states(states)


def test_gueltige_null_aus_ha_wird_nicht_durch_default_ersetzt():
    """Eine ausdrückliche 0 ist ein Wert, kein Anlass für einen Ersatzwert."""
    d = make_watt()
    d.update_from_ha(ctrl_states(**{
        "input_number.ems_heizstab_max_anderung_pro_schritt_w": "0",
        "input_number.ems_heizstab_min_technisch_w":            "0",
    }), 10_000.0, 0.0)
    assert d.max_anderung_pro_schritt_w == 0.0
    assert d.min_technisch_w == 0.0


def test_fehlender_zahlenhelfer_verwendet_den_ersatzwert():
    d = make_watt()
    states = ctrl_states()
    del states._states["input_number.ems_heizstab_max_anderung_pro_schritt_w"]
    d.update_from_ha(states, 10_000.0, 0.0)
    assert d.max_anderung_pro_schritt_w == 1000.0


def test_unavailable_zahlenhelfer_verwendet_denselben_ersatzwert_wie_fehlend():
    """Der Wert ist gleich, die Ursache nicht – genau das trennt der Umbau."""
    d = make_watt()
    d.update_from_ha(ctrl_states(**{
        "input_number.ems_heizstab_max_anderung_pro_schritt_w": "unavailable",
    }), 10_000.0, 0.0)
    assert d.max_anderung_pro_schritt_w == 1000.0


def test_spannungssensor_ausserhalb_der_plausibilitaet_faellt_auf_230v():
    d = ControllableDevice(
        id="wallbox",
        allowed_modes=["manuell"],
        entity_actual_w="sensor.wb_ist",
        entity_anforderung_w="input_number.ems_wallbox_anforderung_leistung_a",
        output_unit="ampere",
        voltage_l1_entity="sensor.spannung_l1",
    )
    d.update_from_ha(make_states({"sensor.spannung_l1": "412"}), 10_000.0, 0.0)
    assert d._voltage_l1 == 230.0


# ---- Add-on-Fallbacks: HA gewinnt, sonst der konfigurierte Wert ----

def make_with_fallbacks(**overrides):
    """Watt-Gerät mit allen sechs verpflichtenden Add-on-Fallbacks."""
    params = {
        "technical_minimum": 100.0,
        "technical_maximum": 4000.0,
        "increase_delay_s": 60.0,
        "decrease_delay_s": 90.0,
        "maximum_step_change": 750.0,
        "minimum_step_change": 25.0,
    }
    params.update(overrides)
    return ControllableDevice(
        id="heizstab",
        allowed_modes=["manuell"],
        entity_actual_w="sensor.heizstab_ist",
        entity_anforderung_w="input_number.ems_heizstab_anforderung_leistung_w",
        **params,
    )


FALLBACK_HELFER = {
    "input_number.ems_heizstab_min_technisch_w":            "technical_minimum",
    "input_number.ems_heizstab_max_technisch_w":            "technical_maximum",
    "input_number.ems_heizstab_hoch_regelzeit_s":           "increase_delay_s",
    "input_number.ems_heizstab_runter_regelzeit_s":         "decrease_delay_s",
    "input_number.ems_heizstab_max_anderung_pro_schritt_w": "maximum_step_change",
    "input_number.ems_heizstab_min_anderung_pro_schritt_w": "minimum_step_change",
}


def read(device, states):
    device.begin_cycle(10_000.0)
    device.update_from_ha(states, 10_000.0, 0.0)
    return device


def wirksame_werte(device):
    return {
        "technical_minimum":   device.min_technisch_w,
        "technical_maximum":   device.max_technisch_w,
        "increase_delay_s":    device.hoch_regelzeit_s,
        "decrease_delay_s":    device.runter_regelzeit_s,
        "maximum_step_change": device.max_anderung_pro_schritt_w,
        "minimum_step_change": device.deadband_w,
    }


def test_gueltiger_ha_wert_schlaegt_den_addon_fallback():
    d = read(make_with_fallbacks(), ctrl_states(**{
        "input_number.ems_heizstab_min_technisch_w":            "500",
        "input_number.ems_heizstab_max_technisch_w":            "3000",
        "input_number.ems_heizstab_hoch_regelzeit_s":           "10",
        "input_number.ems_heizstab_runter_regelzeit_s":         "20",
        "input_number.ems_heizstab_max_anderung_pro_schritt_w": "800",
        "input_number.ems_heizstab_min_anderung_pro_schritt_w": "5",
    }))
    assert wirksame_werte(d) == {
        "technical_minimum": 500.0, "technical_maximum": 3000.0,
        "increase_delay_s": 10.0, "decrease_delay_s": 20.0,
        "maximum_step_change": 800.0, "minimum_step_change": 5.0,
    }
    for entity in FALLBACK_HELFER:
        assert d.entity_diagnostics[entity] == {
            "role": FALLBACK_HELFER[entity], "state": "valid", "source": "ha",
        }


@pytest.mark.parametrize("fehlerbild,erwarteter_zustand", [
    ("missing", "missing"),
    ("unavailable", "unavailable"),
    ("unknown", "unavailable"),
    ("kaputt", "invalid"),
])
def test_fehlend_unavailable_und_ungueltig_nutzen_denselben_addon_wert(
        fehlerbild, erwarteter_zustand):
    """Gleicher Wert, verschiedene Ursache – genau das ist die doppelte Auflösung."""
    states = ctrl_states()
    for entity in FALLBACK_HELFER:
        if fehlerbild == "missing":
            del states._states[entity]
        else:
            states._states[entity]["state"] = fehlerbild

    d = read(make_with_fallbacks(), states)
    assert wirksame_werte(d) == {
        "technical_minimum": 100.0, "technical_maximum": 4000.0,
        "increase_delay_s": 60.0, "decrease_delay_s": 90.0,
        "maximum_step_change": 750.0, "minimum_step_change": 25.0,
    }
    for entity in FALLBACK_HELFER:
        assert d.entity_diagnostics[entity]["state"] == erwarteter_zustand
        assert d.entity_diagnostics[entity]["source"] == "addon"


def test_gueltige_null_schlaegt_den_addon_fallback():
    d = read(make_with_fallbacks(), ctrl_states(**{
        "input_number.ems_heizstab_min_technisch_w":            "0",
        "input_number.ems_heizstab_hoch_regelzeit_s":           "0",
        "input_number.ems_heizstab_min_anderung_pro_schritt_w": "0",
    }))
    assert d.min_technisch_w == 0.0
    assert d.hoch_regelzeit_s == 0.0
    assert d.deadband_w == 0.0


def test_negativer_ha_wert_ist_ungueltig_und_faellt_zurueck():
    d = read(make_with_fallbacks(), ctrl_states(**{
        "input_number.ems_heizstab_min_technisch_w": "-100",
    }))
    assert d.min_technisch_w == 100.0
    assert d.entity_diagnostics[
        "input_number.ems_heizstab_min_technisch_w"]["state"] == "invalid"


def test_ampere_fallback_wird_nach_watt_umgerechnet():
    """Der Add-on-Wert liegt in der nativen Einheit – umgerechnet wird erst danach."""
    d = ControllableDevice(
        id="wallbox",
        allowed_modes=["manuell"],
        entity_actual_w="sensor.wb_ist",
        entity_anforderung_w="input_number.ems_wallbox_anforderung_leistung_a",
        output_unit="ampere",
        allowed_phases=[3],
        technical_minimum=6.0,
        technical_maximum=16.0,
        increase_delay_s=0.0,
        decrease_delay_s=0.0,
        maximum_step_change=2.0,
        minimum_step_change=1.0,
    )
    read(d, make_states({"sensor.wb_ist": "0"}))
    assert d.min_technisch_w == pytest.approx(6 * 3 * 230)
    assert d.max_technisch_w == pytest.approx(16 * 3 * 230)
    assert d.max_anderung_pro_schritt_w == pytest.approx(2 * 3 * 230)
    assert d.deadband_w == pytest.approx(1 * 3 * 230)


def test_phasenwechselsperre_gueltige_null_gewinnt_gegen_den_addon_wert():
    """Vorher verwarf `ha_delay if ha_delay > 0` eine ausdrückliche 0."""
    d = ControllableDevice(
        id="wallbox",
        allowed_modes=["manuell"],
        entity_actual_w="sensor.wb_ist",
        entity_anforderung_w="input_number.ems_wallbox_anforderung_leistung_a",
        entity_prefix="wallbox",
        output_unit="ampere",
        allowed_phases=[1, 3],
        phase_switch_delay_s=300.0,
    )
    read(d, make_states({"input_number.ems_wallbox_min_umschaltzeit_s": "0"}))
    assert d.phase_switch_delay_s == 0.0

    read(d, make_states({}))
    assert d.phase_switch_delay_s == 300.0
