"""Tests für den Ladelimit-Sensor je AC-Speicher (D-057).

Der Sensor muss genau das Limit zeigen, mit dem die Regelung im selben Zyklus
rechnet. Geprüft wird deshalb gegen den echten Status eines BatteryDevice, nicht
gegen handgebaute Zahlen.
"""

import asyncio

import battery_publisher as bp

from test_battery_device import PREFIX, make_battery, prepare, stufe

ENTITY = f"sensor.ems_{PREFIX}_lade_limit_w"


class FakeHA:
    """Merkt sich, was geschrieben wurde. `fail` erzwingt einen Schreibfehler."""

    def __init__(self, fail=False, raise_exc=False):
        self.writes = []
        self.fail = fail
        self.raise_exc = raise_exc

    async def set_state(self, entity_id, state, attributes=None):
        if self.raise_exc:
            raise RuntimeError("HA nicht erreichbar")
        if self.fail:
            return False
        self.writes.append((entity_id, state, attributes or {}))
        return True


def _status(*devices):
    return {"devices": [d.to_status_dict() if hasattr(d, "to_status_dict") else d
                        for d in devices]}


def _states(status):
    return {eid: (state, attrs) for eid, state, attrs in bp.build_battery_limit_states(status)}


def test_entity_id_folgt_dem_praefix():
    assert bp.battery_limit_entity_id("e3dc_speicher") == "sensor.ems_e3dc_speicher_lade_limit_w"


def test_status_enthaelt_entity_prefix():
    b = prepare(make_battery(), soc=50)
    assert b.to_status_dict()["entity_prefix"] == PREFIX


def test_je_speicher_ein_sensor_andere_geraete_keiner():
    b = prepare(make_battery(), soc=50)
    states = _states(_status(b, {"type": "binary", "id": "heizluefter"},
                             {"type": "controllable", "id": "heizstab"}))
    assert list(states) == [ENTITY]


def test_state_ist_das_interne_ladelimit():
    b = prepare(make_battery(available_charge_power_w=5000), soc=50)
    state, attrs = _states(_status(b))[ENTITY]
    assert state == "5000"
    assert float(state) == b._lade_limit_w()
    assert attrs["unit_of_measurement"] == "W"
    assert attrs["device_class"] == "power"
    assert attrs["state_class"] == "measurement"
    assert attrs["wr_max_ladeleistung_w"] == 5000.0
    assert attrs["ladestufe_aktiv"] is None


def test_greifende_ladestufe_senkt_den_sensor():
    b = prepare(make_battery(available_charge_power_w=6000), soc=80,
                **stufe(1, soc=50, max_w=4500), **stufe(2, soc=65, max_w=1500))
    state, attrs = _states(_status(b))[ENTITY]
    assert state == "1500"
    assert float(state) == b._lade_limit_w()
    assert attrs["ladestufe_aktiv"] == 2
    assert attrs["ladestufe_max_w"] == 1500.0


def test_gesperrtes_laden_zeigt_null_und_grund():
    b = prepare(make_battery(), soc=50, laden="off")
    b._darf_laden()
    state, attrs = _states(_status(b))[ENTITY]
    assert state == "0"
    assert attrs["blockiert_grund"] == "laden_gesperrt"


def test_soc_max_zeigt_null():
    b = prepare(make_battery(), soc=100, soc_max=100)
    state, _ = _states(_status(b))[ENTITY]
    assert state == "0"


def test_praefix_abweichend_von_id():
    b = make_battery()
    b.id = "speicher_keller"
    prepare(b, soc=50)
    assert list(_states(_status(b))) == [ENTITY]


def test_attribute_ohne_zeitstempel_stabil():
    b = prepare(make_battery(), soc=50)
    first = _states(_status(b))
    prepare(b, now_ts=10_030.0, soc=50)
    assert _states(_status(b)) == first


def test_publish_schreibt_alle_speicher():
    b = prepare(make_battery(), soc=50)
    ha = FakeHA()
    asyncio.run(bp.publish_battery_limits(ha, _status(b)))
    assert [(eid, state) for eid, state, _ in ha.writes] == [(ENTITY, "5000")]


def test_publish_wirft_nie():
    b = prepare(make_battery(), soc=50)
    asyncio.run(bp.publish_battery_limits(FakeHA(fail=True), _status(b)))
    asyncio.run(bp.publish_battery_limits(FakeHA(raise_exc=True), _status(b)))
    asyncio.run(bp.publish_battery_limits(FakeHA(), None))
