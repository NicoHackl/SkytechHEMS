"""Tests für BinaryDevice: Hysterese, Zeit-Guards, Pool-Verbrauch."""

from ems.devices import BinaryDevice


def make_binary(prio=1, power=1000.0, on_reserve=0.0):
    b = BinaryDevice(
        id="luft",
        allowed_modes=["auto"],
        entity_switch="switch.luft",
        entity_anforderung_an="input_boolean.ems_luft_anforderung_an",
    )
    b.eligible = True
    b.priority = prio
    b.power_w = power
    b.on_reserve_w = on_reserve
    return b


def test_max_relief_is_zero():
    b = make_binary()
    assert b.max_relief_w == 0.0


def test_current_w_depends_on_actual_state():
    b = make_binary(power=1500.0)
    b._actual_on = False
    assert b.current_w == 0.0
    b._actual_on = True
    assert b.current_w == 1500.0


def test_consume_off_requires_power_plus_reserves():
    b = make_binary(power=1000.0, on_reserve=200.0)
    b._actual_on = False
    # Einschaltschwelle = 1000 + 200 + 300(global) = 1500
    remaining = b.consume_from_pool(1499.0, 300.0)
    assert b.desired_on is False
    assert remaining == 1499.0  # nichts verbraucht
    remaining = b.consume_from_pool(1500.0, 300.0)
    assert b.desired_on is True
    assert remaining == 500.0  # power_w abgezogen


def test_consume_on_only_requires_power():
    b = make_binary(power=1000.0, on_reserve=500.0)
    b._actual_on = True
    # Bereits an: Hysterese-Reserve entfällt, nur power_w nötig
    b.consume_from_pool(1000.0, 0.0)
    assert b.desired_on is True


def test_consume_not_eligible_is_noop():
    b = make_binary()
    b.eligible = False
    assert b.consume_from_pool(9999.0, 0.0) == 9999.0


def test_candidate_min_runtime_keeps_on():
    b = make_binary()
    b._actual_on = True
    b._desired_on = False
    b._switch_age_s = 10.0
    b.min_runtime_s = 60.0
    b.calculate_candidate(now_ts=1000.0)
    assert b.candidate_on is True  # Mindestlaufzeit schützt


def test_candidate_off_delay_blocks_then_releases():
    b = make_binary()
    b._actual_on = True
    b._desired_on = False
    b._switch_age_s = 100.0
    b.min_runtime_s = 60.0
    b.off_delay_s = 30.0
    b._off_since_ts = 0.0

    b.calculate_candidate(now_ts=1000.0)
    assert b.candidate_on is True            # Verzögerung läuft gerade an
    assert b._off_since_ts == 1000.0

    b.calculate_candidate(now_ts=1040.0)     # 40s > 30s Verzögerung
    assert b.candidate_on is False


def test_candidate_min_offtime_blocks_restart():
    b = make_binary()
    b._actual_on = False
    b._desired_on = True
    b._switch_age_s = 10.0
    b.min_offtime_s = 60.0
    b.calculate_candidate(now_ts=1000.0)
    assert b.candidate_on is False           # Mindestauszeit noch nicht erfüllt

    b._switch_age_s = 70.0
    b.calculate_candidate(now_ts=1000.0)
    assert b.candidate_on is True


def test_candidate_not_eligible_is_off():
    b = make_binary()
    b.eligible = False
    b._off_since_ts = 123.0
    b.calculate_candidate(now_ts=1000.0)
    assert b.candidate_on is False
    assert b._off_since_ts == 0.0


def test_write_ops_reflect_final_state():
    b = make_binary()
    b._final_on = True
    assert b.get_write_ops() == [
        ("input_boolean", "turn_on", {"entity_id": "input_boolean.ems_luft_anforderung_an"})
    ]
    b._final_on = False
    assert b.get_write_ops()[0][1] == "turn_off"
