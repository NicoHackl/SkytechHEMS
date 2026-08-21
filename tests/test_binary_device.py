"""Tests für BinaryDevice: Hysterese, Zeit-Guards, Pool-Verbrauch."""

from ems.devices import BinaryDevice

from conftest import make_states


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
    b._anforderung_an = True
    b._actual_on = False
    assert b.current_w == 0.0
    b._actual_on = True
    assert b.current_w == 1500.0


def test_current_w_ignoriert_extern_erzwungenen_schalter():
    """Force-Modus: Schalter an, aber HEMS hat nicht angefordert -> nicht in den Pool."""
    b = make_binary(power=1500.0)
    b._actual_on = True
    b._anforderung_an = False
    assert b.current_w == 0.0


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
    ops = b.get_write_ops()
    assert [(op.domain, op.service, op.data, op.owner) for op in ops] == [
        ("input_boolean", "turn_on",
         {"entity_id": "input_boolean.ems_luft_anforderung_an"}, "luft")
    ]
    b._final_on = False
    assert b.get_write_ops()[0][1] == "turn_off"


# ---- Charakterisierung: Fallback-Verhalten vor dem Umbau ----

def binary_states(**overrides):
    """HA-Schnappschuss eines binären Geräts mit dem Präfix 'luft'."""
    states = {
        "switch.luft":                                 "off",
        "input_boolean.ems_luft_anforderung_an":       "off",
        "input_number.ems_luft_prioritat":             "5",
        "input_number.ems_luft_leistung_w":            "1500",
        "input_number.ems_luft_einschaltreserve_w":    "200",
        "input_number.ems_luft_mindestlaufzeit_s":     "600",
        "input_number.ems_luft_mindestauszeit_s":      "300",
        "input_number.ems_luft_abschaltverzogerung_s": "120",
    }
    states.update(overrides)
    return make_states(states)


def test_gueltige_null_bleibt_null():
    b = make_binary()
    b.update_from_ha(binary_states(**{
        "input_number.ems_luft_leistung_w":        "0",
        "input_number.ems_luft_mindestlaufzeit_s": "0",
    }), 10_000.0, 0.0)
    assert b.power_w == 0.0
    assert b.min_runtime_s == 0.0


def test_fehlender_zahlenhelfer_wird_als_null_gelesen():
    """Heute unauffällig – nach dem Umbau greift stattdessen der Add-on-Fallback."""
    b = make_binary()
    states = binary_states()
    del states._states["input_number.ems_luft_leistung_w"]
    b.update_from_ha(states, 10_000.0, 0.0)
    assert b.power_w == 0.0


def test_unavailable_zahlenhelfer_wird_wie_fehlend_behandelt():
    b = make_binary()
    b.update_from_ha(binary_states(**{
        "input_number.ems_luft_leistung_w": "unavailable",
    }), 10_000.0, 0.0)
    assert b.power_w == 0.0


def test_unbekannter_schalterzustand_gilt_als_aus():
    b = make_binary()
    b.update_from_ha(binary_states(**{"switch.luft": "unavailable"}), 10_000.0, 0.0)
    assert b.actual_on is False


# ---- Add-on-Fallbacks: HA gewinnt, sonst der konfigurierte Wert ----

BIN_HELFER = {
    "input_number.ems_luft_leistung_w":            "power_w",
    "input_number.ems_luft_einschaltreserve_w":    "on_reserve_w",
    "input_number.ems_luft_mindestlaufzeit_s":     "min_runtime_s",
    "input_number.ems_luft_mindestauszeit_s":      "min_offtime_s",
    "input_number.ems_luft_abschaltverzogerung_s": "off_delay_s",
}


def make_with_fallbacks():
    return BinaryDevice(
        id="luft",
        allowed_modes=["manuell"],
        entity_switch="switch.luft",
        entity_anforderung_an="input_boolean.ems_luft_anforderung_an",
        power_w=900.0,
        on_reserve_w=150.0,
        min_runtime_s=480.0,
        min_offtime_s=240.0,
        off_delay_s=90.0,
    )


def read(device, states):
    device.begin_cycle(10_000.0)
    device.update_from_ha(states, 10_000.0, 0.0)
    return device


def wirksame_werte(device):
    return {
        "power_w":       device.power_w,
        "on_reserve_w":  device.on_reserve_w,
        "min_runtime_s": device.min_runtime_s,
        "min_offtime_s": device.min_offtime_s,
        "off_delay_s":   device.off_delay_s,
    }


def test_gueltige_ha_werte_schlagen_die_addon_fallbacks():
    d = read(make_with_fallbacks(), binary_states())
    assert wirksame_werte(d) == {
        "power_w": 1500.0, "on_reserve_w": 200.0,
        "min_runtime_s": 600.0, "min_offtime_s": 300.0, "off_delay_s": 120.0,
    }
    for entity, role in BIN_HELFER.items():
        assert d.entity_diagnostics[entity] == {
            "role": role, "state": "valid", "source": "ha",
        }


def test_fehlende_helfer_verwenden_die_addon_fallbacks():
    states = binary_states()
    for entity in BIN_HELFER:
        del states._states[entity]
    d = read(make_with_fallbacks(), states)
    assert wirksame_werte(d) == {
        "power_w": 900.0, "on_reserve_w": 150.0,
        "min_runtime_s": 480.0, "min_offtime_s": 240.0, "off_delay_s": 90.0,
    }
    for entity in BIN_HELFER:
        assert d.entity_diagnostics[entity]["state"] == "missing"
        assert d.entity_diagnostics[entity]["source"] == "addon"


def test_unavailable_helfer_liefert_denselben_wert_mit_anderer_ursache():
    states = binary_states()
    for entity in BIN_HELFER:
        states._states[entity]["state"] = "unavailable"
    d = read(make_with_fallbacks(), states)
    assert d.power_w == 900.0
    assert d.entity_diagnostics["input_number.ems_luft_leistung_w"]["state"] == "unavailable"


def test_gueltige_null_schlaegt_den_addon_fallback_auch_binaer():
    d = read(make_with_fallbacks(), binary_states(**{
        "input_number.ems_luft_leistung_w":        "0",
        "input_number.ems_luft_mindestlaufzeit_s": "0",
    }))
    assert d.power_w == 0.0
    assert d.min_runtime_s == 0.0


def test_zeitschutz_bleibt_unveraendert_mit_addon_werten():
    """Die Guards rechnen mit dem wirksamen Wert – egal woher er kommt."""
    states = binary_states(**{"switch.luft": "on"})
    del states._states["input_number.ems_luft_mindestlaufzeit_s"]
    d = read(make_with_fallbacks(), states)
    d.eligible = True
    d._switch_age_s = 100.0          # unter der Mindestlaufzeit von 480 s
    d._desired_on = False
    d.calculate_candidate(10_000.0)
    assert d.candidate_on is True
    assert d.in_min_runtime is True
