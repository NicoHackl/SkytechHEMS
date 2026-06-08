"""Tests für EMSController: Pool, Lockout, konfigurierbarer Sensor, Kaskade, One-Change."""

from ems.controller import EMSController, DEFAULT_RESIDUAL_ENTITY
from ems.devices import BinaryDevice

from conftest import make_states


def make_binary(prio, actual_on, final_on):
    b = BinaryDevice("d%d" % prio, ["auto"], "switch.x", "input_boolean.x")
    b.priority = prio
    b._actual_on = actual_on
    b._final_on = final_on
    return b


# ---- Konfiguration des Überschuss-Sensors ----

def test_default_residual_entity():
    ctrl = EMSController([])
    assert ctrl._residual_entity == DEFAULT_RESIDUAL_ENTITY


def test_custom_residual_entity_used():
    ctrl = EMSController([], residual_power_entity="sensor.mein_ueberschuss")
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.mein_ueberschuss": "3000",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["residual_w"] == 3000.0
    assert res["status"]["pool_w"] == 3000.0


def test_empty_residual_entity_falls_back_to_default():
    ctrl = EMSController([], residual_power_entity="   ")
    assert ctrl._residual_entity == DEFAULT_RESIDUAL_ENTITY


# ---- Globalzustände ----

def test_ems_disabled_yields_empty_pool():
    ctrl = EMSController([], residual_power_entity="sensor.s")
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "off",
        "sensor.s": "5000",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["ems_enabled"] is False
    assert res["status"]["pool_w"] == 0.0


def test_hard_lockout_on_invalid_sensor():
    ctrl = EMSController([], residual_power_entity="sensor.s")
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.s": "unavailable",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["residual_sensor_valid"] is False
    assert res["status"]["hard_lockout"] is True
    assert res["status"]["pool_w"] == 0.0


def test_hard_lockout_on_extreme_negative():
    ctrl = EMSController([], residual_power_entity="sensor.s")
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.s": "-60000",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["hard_lockout"] is True


# ---- One-Change-Limit ----

def test_limit_one_change_only_one_turn_on():
    ctrl = EMSController([])
    a = make_binary(1, actual_on=False, final_on=True)
    b = make_binary(2, actual_on=False, final_on=True)
    ctrl._limit_one_change([a, b], binary_immediate_off=False)
    # Höchste Priorität (kleinste Zahl) gewinnt
    assert a.final_on is True
    assert b.final_on is False


def test_limit_one_change_skipped_on_emergency():
    ctrl = EMSController([])
    a = make_binary(1, actual_on=True, final_on=False)
    b = make_binary(2, actual_on=True, final_on=False)
    ctrl._limit_one_change([a, b], binary_immediate_off=True)
    # Notabschaltung: beide dürfen gleichzeitig abschalten
    assert a.final_on is False
    assert b.final_on is False


def test_limit_one_change_turn_off_keeps_higher_on():
    ctrl = EMSController([])
    a = make_binary(1, actual_on=True, final_on=False)   # wichtig
    b = make_binary(2, actual_on=True, final_on=False)   # unwichtig
    ctrl._limit_one_change([a, b], binary_immediate_off=False)
    # Nur das unwichtigste (höchste Prio-Zahl) schaltet ab
    assert b.final_on is False
    assert a.final_on is True


# ---- Prioritätskaskade (Promotion) ----

def test_cascade_promotes_higher_priority_on():
    ctrl = EMSController([])
    high = make_binary(1, actual_on=False, final_on=False)
    high.eligible = True
    high._candidate_on = True
    low = make_binary(2, actual_on=False, final_on=True)
    ctrl._apply_priority_cascade([high, low])
    # Höher-priores Gerät darf nicht aus sein, während niedriger-priores an ist
    assert high.final_on is True
