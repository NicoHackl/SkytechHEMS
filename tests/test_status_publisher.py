"""Tests für das HEMS-Lebenszeichen sensor.skytech_hems_status (D-062).

Vertrag: contract/contract_hems_wallbox_provider/ und contract/contract_hems_battery_provider/.
Die Provider werten ausschließlich die Änderung von zyklus_zaehler aus.
"""

import status_publisher as sp

from test_emergency import EMERGENCY_OPTIONS, entry, make_app, run


class FakeHA:
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


def test_state_und_attribute_gemaess_vertrag():
    state, attrs = sp.build_status_state(7, 30, "07.10.2026 12:00:00")
    assert state == "7"
    assert attrs["zyklus_zaehler"] == 7
    assert attrs["zyklus_intervall_s"] == 30
    assert attrs["erzeugt_am"] == "07.10.2026 12:00:00"
    assert attrs["vertrag_version"] == 1


def test_zaehler_aendert_sich_je_veroeffentlichung():
    ha = FakeHA()
    pub = sp.StatusPublisher()
    run(pub.publish(ha, 30, "a"))
    run(pub.publish(ha, 30, "b"))
    assert [w[0] for w in ha.writes] == [sp.STATUS_ENTITY_ID] * 2
    assert [w[1] for w in ha.writes] == ["1", "2"]


def test_schreibfehler_wirft_nicht():
    assert run(sp.StatusPublisher().publish(FakeHA(fail=True), 30, "x")) is False
    assert run(sp.StatusPublisher().publish(FakeHA(raise_exc=True), 30, "x")) is False


def test_zaehler_laeuft_auch_nach_fehler_weiter():
    # Der Provider erkennt das Leben an einer Änderung – ein fehlgeschlagener
    # Schreibvorgang darf beim nächsten Mal nicht denselben Wert erneut liefern.
    ha = FakeHA(fail=True)
    pub = sp.StatusPublisher()
    run(pub.publish(ha, 30, "x"))
    ha.fail = False
    run(pub.publish(ha, 30, "y"))
    assert ha.writes[-1][1] == "2"


def test_normaler_zyklus_veroeffentlicht_lebenszeichen(tmp_path, monkeypatch):
    app, ha = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "devices": []},
                       states={"binary_sensor.netz": entry("on"), "sensor.ueberschuss": entry("0")})
    run(app._run_cycle())
    run(app._run_cycle())
    state, attrs = ha.sensors[sp.STATUS_ENTITY_ID]
    assert state == "2"
    assert attrs["zyklus_intervall_s"] == app.interval_s


def test_notabschaltung_veroeffentlicht_lebenszeichen(tmp_path, monkeypatch):
    app, ha = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "devices": []},
                       states={"binary_sensor.netz": entry("off")})
    run(app._run_cycle())
    assert app.emergency.active is True
    assert ha.sensors[sp.STATUS_ENTITY_ID][0] == "1"


def test_zyklus_mit_ausnahme_veroeffentlicht_kein_lebenszeichen(tmp_path, monkeypatch):
    app, ha = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "devices": []},
                       states={"binary_sensor.netz": entry("on"), "sensor.ueberschuss": entry("0")})

    def kaputt(st):
        raise RuntimeError("Regelfehler")

    monkeypatch.setattr(app.ems, "run_cycle", kaputt)
    run(app._run_cycle())
    assert sp.STATUS_ENTITY_ID not in ha.sensors
