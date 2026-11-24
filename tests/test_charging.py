"""Ladeziele im vollständigen Regelzyklus: Budget, Zuordnung und Ausfälle."""

import pytest

from configuration import validate_options
from ems.charging import CHARGING_INTERFACES
from ems.controller import EMSController
from ems.ops import WriteResult
from status_publisher import build_status_state
from conftest import make_states
from test_run_cycle import CTRL_FALLBACKS, _controllable_w, _global

TARGET = 'input_number.ems_auto_anforderung_leistung_w'


def config(backend='evms', **overrides):
    return {'name': 'auto', 'class': 'controllable', 'allowed_modes': 'auto',
            'charging_backend': backend, 'output_unit': 'watt',
            **CTRL_FALLBACKS, **overrides}


def snapshot(backend='evms', counter=1, assignment='sitzung-a', attrs=None, states=None):
    interface = CHARGING_INTERFACES[backend]
    feedback = {
        'ladevertrag_version': 1, 'instanz_id': 'prozess-a',
        'auto_zuordnung_id': assignment, 'auto_rueckmeldung_zaehler': counter,
        'auto_freigabe': True, 'auto_istleistung_w': 0,
        'auto_minimum_w': 1380, 'auto_maximum_w': 11000,
        **(attrs or {}),
    }
    return make_states({**_global(), **_controllable_w('auto', min_w=0, max_w=11000),
                        'sensor.s': 5000, interface: 'auto', **(states or {})},
                       attributes={interface: feedback})


def request(result):
    return next(op.data['value'] for op in result['write_ops']
                if op.data.get('entity_id') == TARGET)


@pytest.mark.parametrize('backend', CHARGING_INTERFACES)
def test_all_routes_write_only_watts_after_live_feedback(backend):
    ctrl = EMSController([config(backend)], residual_power_entity='sensor.s')
    assert request(ctrl.run_cycle(snapshot(backend))) == 0
    result = ctrl.run_cycle(snapshot(backend, counter=2))
    assert request(result) == 5000
    assert len(result['write_ops']) == 1
    assert ctrl.charging_interface_values()['auto'] == {
        'anbindung': backend, 'zuordnung_id': 'sitzung-a', 'leistung_w': 5000}


@pytest.mark.parametrize('attrs', [
    {'auto_freigabe': False}, {'auto_freigabe': 'true'},
    {'auto_istleistung_w': None}, {'auto_istleistung_w': float('nan')},
    {'auto_istleistung_w': -1}, {'auto_istleistung_w': True},
    {'auto_maximum_w': None}, {'auto_minimum_w': 12000},
    {'auto_maximum_w': 0}, {'ladevertrag_version': 2},
    {'ladevertrag_version': True}, {'instanz_id': ''},
    {'auto_rueckmeldung_zaehler': True}, {'auto_zuordnung_id': ''},
])
def test_invalid_feedback_stops_even_force(attrs):
    ctrl = EMSController([config()], residual_power_entity='sensor.s')
    ctrl.run_cycle(snapshot())
    result = ctrl.run_cycle(snapshot(counter=2, attrs=attrs, states={
        TARGET: 5000, 'input_boolean.ems_auto_force': 'on',
        'input_number.ems_auto_force_leistung_w': 7000}))
    assert request(result) == 0
    assert not result['status']['devices'][0]['runtime_active']


def test_timeout_and_recovery(monkeypatch):
    now = [0.0]
    monkeypatch.setattr('ems.charging.time.monotonic', lambda: now[0])
    ctrl = EMSController([config(charging_feedback_timeout_s=20)], residual_power_entity='sensor.s')
    ctrl.run_cycle(snapshot())
    assert request(ctrl.run_cycle(snapshot(counter=2))) == 5000
    now[0] = 20
    assert request(ctrl.run_cycle(snapshot(counter=2))) == 0
    assert request(ctrl.run_cycle(snapshot(counter=3))) == 5000


def test_assignment_switch_requires_new_sample_and_clears_old_commit():
    ctrl = EMSController([config()], residual_power_entity='sensor.s')
    ctrl.run_cycle(snapshot())
    ctrl.run_cycle(snapshot(counter=2))
    assert request(ctrl.run_cycle(snapshot(counter=3, assignment='sitzung-b'))) == 0
    assert ctrl.charging_interface_values()['auto']['leistung_w'] == 0
    assert ctrl.charging_interface_values()['auto']['zuordnung_id'] == 'sitzung-b'
    assert request(ctrl.run_cycle(snapshot(counter=4, assignment='sitzung-b'))) == 5000


def test_other_backend_does_not_release_target():
    ctrl = EMSController([config('evms')], residual_power_entity='sensor.s')
    assert request(ctrl.run_cycle(snapshot('wallbox_provider'))) == 0
    assert request(ctrl.run_cycle(snapshot('wallbox_provider', counter=2))) == 0


def test_minimum_and_maximum_respected_despite_deadband():
    ctrl = EMSController([config()], residual_power_entity='sensor.s')
    ctrl.run_cycle(snapshot())
    result = ctrl.run_cycle(snapshot(counter=2, states={'sensor.s': 1000}))
    assert result['write_ops'] == []
    assert ctrl.charging_interface_values()['auto']['leistung_w'] == 0
    result = ctrl.run_cycle(snapshot(counter=3, attrs={'auto_maximum_w': 4999.5},
                                    states={TARGET: 5000,
                                            'input_number.ems_auto_min_anderung_pro_schritt_w': 500}))
    assert request(result) == 4999


def test_invalid_state_cannot_reuse_old_attributes():
    ctrl = EMSController([config()], residual_power_entity='sensor.s')
    ctrl.run_cycle(snapshot())
    result = ctrl.run_cycle(snapshot(counter=2, states={'sensor.evms_schnittstelle': 'unavailable'}))
    assert request(result) == 0


def test_failed_write_and_emergency_publish_zero_budget():
    ctrl = EMSController([config()], residual_power_entity='sensor.s')
    ctrl.run_cycle(snapshot())
    result = ctrl.run_cycle(snapshot(counter=2))
    assert ctrl.charging_interface_values(active=False)['auto']['leistung_w'] == 0
    ctrl.report_write_results([WriteResult(result['write_ops'][0], False, 'Testfehler')])
    targets = ctrl.charging_interface_values()
    assert targets['auto']['leistung_w'] == 0
    state, attrs = build_status_state(2, 30, '21.10.2026 12:00:00', charging_targets=targets)
    assert state == ''  # Speichervertrag bleibt kompatibel.
    assert attrs['ladevertrag_version'] == 1
    assert attrs['ladeziele'] == targets


@pytest.mark.parametrize('overrides,field', [
    ({'output_unit': 'ampere'}, 'output_unit'),
    ({'charging_backend': 'falsch'}, 'charging_backend'),
    ({'charging_feedback_timeout_s': 0}, 'charging_feedback_timeout_s'),
    ({'charging_feedback_timeout_s': None}, 'charging_feedback_timeout_s'),
    ({'charging_feedback_timeout_s': 'ungueltig'}, 'charging_feedback_timeout_s'),
    ({'charging_feedback_timeout_s': float('nan')}, 'charging_feedback_timeout_s'),
    ({'actual_power_entity': 'sensor.alt'}, 'actual_power_entity'),
])
def test_configuration_rejects_ambiguous_or_unsafe_setup(overrides, field):
    result = validate_options({'devices': [config(**overrides)]})
    assert f'devices[0].{field}' in result.field_errors


def test_process_restart_requires_new_sample():
    ctrl = EMSController([config()], residual_power_entity='sensor.s')
    ctrl.run_cycle(snapshot())
    ctrl.run_cycle(snapshot(counter=2))
    assert request(ctrl.run_cycle(snapshot(counter=3, attrs={'instanz_id': 'prozess-b'}))) == 0
    assert request(ctrl.run_cycle(snapshot(counter=4, attrs={'instanz_id': 'prozess-b'}))) == 5000


def test_charging_schema_keeps_ep_device_class_and_watt_helpers():
    from main import _build_device_controls_schema
    from config_service import ConfigService
    validated = validate_options({'devices': [config()]})
    schema = _build_device_controls_schema(validated.devices,
                                           residual_power_entity='sensor.s', interval_s=30)
    target = schema[1]
    assert target['class'] == 'controllable'
    assert target['output_unit'] == 'watt'
    assert target['charging_backend'] == 'evms'
    assert target['actual_power_entity'] == ''
    assert target['phase_entity'] == ''
    assert target['request_entity'] == TARGET
    assert ConfigService.supported()['charging_backends'] == ['', 'evms', 'wallbox_provider', 'automation']


def test_flow_card_distinguishes_missing_measurement_from_zero():
    from flow_publisher import build_status_payload
    ctrl = EMSController([config()], residual_power_entity='sensor.s')
    ctrl.run_cycle(snapshot())
    valid = ctrl.run_cycle(snapshot(counter=2))
    missing = ctrl.run_cycle(snapshot(counter=3, attrs={'auto_istleistung_w': None}))
    assert valid['status']['devices'][0]['charging_measurement_valid'] is True
    assert missing['status']['devices'][0]['charging_measurement_valid'] is False
    assert build_status_payload(valid['status'], 2, '21.10.2026 12:00:00')['devices']['auto']['leistung_w'] == 0
    assert build_status_payload(missing['status'], 3, '21.10.2026 12:00:01')['devices']['auto']['leistung_w'] is None
