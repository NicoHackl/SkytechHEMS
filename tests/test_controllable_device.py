"""Tests für ControllableDevice: Zuteilung, Rampe, Phasenwahl, Schreiboperationen."""

from ems.devices import ControllableDevice


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
    assert ops == [
        ("input_number", "set_value",
         {"entity_id": "input_number.ems_heizstab_anforderung_leistung_w", "value": 1500.0})
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
