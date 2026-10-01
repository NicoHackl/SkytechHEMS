"""Tests der Notabschaltung (D-059): Bedingung, Zielzeilen, Merker, Ablauf,
Quittieren, Konfiguration und die Einbindung in den Zyklus von main.py.

Gefahren wird gegen ein gefälschtes Home Assistant ohne Netzwerk.
"""

import asyncio
import datetime
import json

import pytest

import configuration as cfg
import main
from config_service import ConfigService
from emergency import (
    CONDITION_INVALID,
    CONDITION_MET,
    CONDITION_NOT_MET,
    SENSOR_ENTITY_ID,
    EmergencyConfig,
    EmergencyStop,
    Latch,
    LatchStore,
    describe_op,
    evaluate,
    shutdown_ops,
    target_ops,
)
from emergency_rules import condition_error, target_error
from ems.ops import WriteOp, WriteResult

from test_configuration import battery, binary, controllable


def run(coro):
    return asyncio.run(coro)


def entry(state):
    return {"state": state, "attributes": {}, "last_changed": None}


class FakeHA:
    """Protokolliert jeden Schreibbefehl als „domain.service entity_id“."""

    def __init__(self, states=None, fail=()):
        self.states = dict(states or {})
        self.fail = set(fail)
        self.calls = []
        self.sensors = {}
        self.unreachable = False

    async def execute_write_ops(self, ops, abort=None):
        results = []
        for op in ops:
            if abort is not None and abort():
                break
            self.calls.append(describe_op(op))
            ok = op.data.get("entity_id") not in self.fail
            results.append(WriteResult(op, ok, "" if ok else "HTTP 500"))
        return results

    async def call_service(self, domain, service, data=None):
        self.calls.append(f"{domain}.{service} {(data or {}).get('entity_id', '')}")

    async def set_state(self, entity_id, state, attributes=None):
        self.sensors[entity_id] = (state, attributes or {})
        return True

    async def fetch_state(self, entity_id):
        if self.unreachable:
            raise RuntimeError("Verbindung abgelehnt")
        return self.states.get(entity_id)

    async def fetch_all_states(self):
        return dict(self.states)


FIXED_NOW = datetime.datetime(2026, 10, 1, 14, 30, 5, tzinfo=main.BERLIN)


def make_stop(tmp_path, ha, *, targets=None, devices=None, script="", entity="binary_sensor.netz",
              operator="==", value="off"):
    return EmergencyStop(
        ha=ha,
        store=LatchStore(tmp_path / "notabschaltung.json"),
        config=EmergencyConfig(entity, operator, value, targets or []),
        device_configs=devices or [],
        post_cycle_script=script,
        now=lambda: FIXED_NOW,
    )


# ---------------------------------------------------------------------------
# Bedingung
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("operator,value,state,expected", [
    ("==", "off", "off", CONDITION_MET),
    ("==", "OFF", "off", CONDITION_MET),          # Text ohne Groß-/Kleinschreibung
    ("==", "on", "off", CONDITION_NOT_MET),
    ("!=", "on", "off", CONDITION_MET),
    ("!=", "off", "off", CONDITION_NOT_MET),
    ("==", "1", "1.0", CONDITION_MET),            # Zahlen numerisch
    ("!=", "1", "1.0", CONDITION_NOT_MET),
    (">", "100", "150", CONDITION_MET),
    (">", "100", "100", CONDITION_NOT_MET),
    (">=", "100", "100", CONDITION_MET),
    ("<", "0,5", "0.4", CONDITION_MET),           # Dezimalkomma im Sollwert
    ("<", "0.5", "0.5", CONDITION_NOT_MET),
    ("<=", "0.5", "0.5", CONDITION_MET),
])
def test_bedingung_operatoren(operator, value, state, expected):
    assert evaluate("sensor.x", operator, value, entry(state)).state == expected


@pytest.mark.parametrize("state", ["unavailable", "unknown", "", None])
def test_nicht_auswertbarer_zustand_loest_nicht_aus(state):
    result = evaluate("sensor.x", "==", "off", entry(state))
    assert result.state == CONDITION_INVALID


def test_fehlende_entitaet_loest_nicht_aus():
    result = evaluate("sensor.x", "==", "off", None)
    assert result.state == CONDITION_INVALID
    assert "existiert" in result.reason


def test_groessenvergleich_mit_text_ist_nicht_auswertbar():
    assert evaluate("sensor.x", ">", "100", entry("hoch")).state == CONDITION_INVALID
    assert evaluate("sensor.x", ">", "viel", entry("150")).state == CONDITION_INVALID


def test_bedingung_feldfehler():
    assert condition_error("", "", "") == {}            # leer = aus, kein Fehler
    assert set(condition_error("sensor.x", "~", "")) == {"operator", "value"}
    assert set(condition_error("sensor.x", ">", "abc")) == {"value"}
    assert condition_error("sensor.x", "==", "abc") == {}


# ---------------------------------------------------------------------------
# Zielzeilen und Geräte
# ---------------------------------------------------------------------------

def test_zielzeilen_je_domain():
    ops = target_ops([
        {"entity": "switch.wallbox", "value": "off"},
        {"entity": "input_boolean.x", "value": "on"},
        {"entity": "select.e3dc_modus", "value": "Automatik"},
        {"entity": "input_number.y", "value": "12,5"},
        {"entity": "button.reset", "value": ""},
        {"entity": "script.notfall", "value": ""},
    ])
    assert [(op.domain, op.service) for op in ops] == [
        ("switch", "turn_off"), ("input_boolean", "turn_on"), ("select", "select_option"),
        ("input_number", "set_value"), ("button", "press"), ("script", "turn_on"),
    ]
    assert ops[2].data == {"entity_id": "select.e3dc_modus", "option": "Automatik"}
    assert ops[3].data["value"] == 12.5
    assert all(op.owner == "notabschaltung" for op in ops)


def test_ungueltige_zielzeile_wird_uebersprungen():
    ops = target_ops([
        {"entity": "sensor.nur_lesbar", "value": "1"},
        {"entity": "switch.a", "value": "vielleicht"},
        {"entity": "switch.b", "value": "off"},
    ])
    assert [op.data["entity_id"] for op in ops] == ["switch.b"]


def test_zielzeile_feldfehler():
    assert "entity" in target_error("sensor.x", "1")
    assert "value" in target_error("switch.x", "")
    assert "value" in target_error("select.x", " ")
    assert "value" in target_error("number.x", "abc")
    assert target_error("button.x", "") == {}


def test_abschalt_ops_fuer_jede_geraeteklasse():
    ops = shutdown_ops([
        {"name": "heizstab", "class": "controllable", "entity_prefix": "heizstab"},
        {"name": "luft", "class": "binary", "entity_prefix": "luft"},
        {"name": "akku", "class": "battery", "entity_prefix": "akku"},
    ])
    assert [describe_op(op) for op in ops] == [
        "input_number.set_value input_number.ems_heizstab_anforderung_leistung_w",
        "input_boolean.turn_off input_boolean.ems_luft_anforderung_an",
        # Speicher: erst 0 W, dann standby
        "input_number.set_value input_number.ems_akku_anforderung_leistung_w",
        "input_select.select_option input_select.ems_akku_anforderung_betriebsart",
    ]


# ---------------------------------------------------------------------------
# Merker
# ---------------------------------------------------------------------------

def test_merker_roundtrip(tmp_path):
    store = LatchStore(tmp_path / "sub" / "notabschaltung.json")
    store.save(Latch(True, "2026-10-01T14:30:05+02:00", {"entity": "sensor.x"}))
    latch, error = store.load()
    assert error == ""
    assert latch.active is True
    assert latch.trigger == {"entity": "sensor.x"}
    assert not (tmp_path / "sub" / "notabschaltung.tmp").exists()


def test_fehlender_merker_ist_nicht_aktiv(tmp_path):
    latch, error = LatchStore(tmp_path / "fehlt.json").load()
    assert latch.active is False and error == ""


@pytest.mark.parametrize("inhalt", ["{kaputt", "[]", '{"active": "ja"}'])
def test_kaputter_merker_gilt_als_aktiv(tmp_path, inhalt):
    path = tmp_path / "notabschaltung.json"
    path.write_text(inhalt, encoding="utf-8")
    latch, error = LatchStore(path).load()
    assert latch.active is True
    assert "gilt als aktiv" in error


# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------

DEVICES = [
    {"name": "luft", "class": "binary", "entity_prefix": "luft"},
    {"name": "akku", "class": "battery", "entity_prefix": "akku"},
]
TARGETS = [{"entity": "select.akku_modus", "value": "auto"}]


def test_ausloesen_reihenfolge_geraete_skript_ziele(tmp_path):
    ha = FakeHA()
    stop = make_stop(tmp_path, ha, devices=DEVICES, targets=TARGETS, script="script.weiterreichen")
    run(stop.trigger_now(evaluate("binary_sensor.netz", "==", "off", entry("off"))))
    assert ha.calls == [
        "input_boolean.turn_off input_boolean.ems_luft_anforderung_an",
        "input_number.set_value input_number.ems_akku_anforderung_leistung_w",
        "input_select.select_option input_select.ems_akku_anforderung_betriebsart",
        "script.turn_on script.weiterreichen",
        "select.select_option select.akku_modus",
    ]
    assert stop.active is True
    assert ha.sensors[SENSOR_ENTITY_ID][0] == "on"
    assert ha.sensors[SENSOR_ENTITY_ID][1]["seit"] == "01.10.2026 14:30:05"
    saved = json.loads((tmp_path / "notabschaltung.json").read_text(encoding="utf-8"))
    assert saved["active"] is True
    assert saved["trigger"]["measured"] == "off"


def test_zweites_ausloesen_schaltet_nicht_erneut(tmp_path):
    ha = FakeHA()
    stop = make_stop(tmp_path, ha, devices=DEVICES)
    result = evaluate("binary_sensor.netz", "==", "off", entry("off"))
    run(stop.trigger_now(result))
    anzahl = len(ha.calls)
    run(stop.trigger_now(result))
    assert len(ha.calls) == anzahl


def test_nur_fehlgeschlagene_befehle_werden_wiederholt(tmp_path):
    ha = FakeHA(fail={"select.akku_modus"})
    stop = make_stop(tmp_path, ha, devices=DEVICES, targets=TARGETS)
    run(stop.trigger_now(evaluate("binary_sensor.netz", "==", "off", entry("off"))))
    assert [describe_op(op) for op in stop.pending_ops] == ["select.select_option select.akku_modus"]

    ha.calls.clear()
    run(stop.retry_pending())
    assert ha.calls == ["select.select_option select.akku_modus"]
    assert stop.pending_ops                     # schlägt weiter fehl

    ha.fail.clear()
    ha.calls.clear()
    run(stop.retry_pending())
    assert ha.calls == ["select.select_option select.akku_modus"]
    assert stop.pending_ops == []

    ha.calls.clear()
    run(stop.retry_pending())
    assert ha.calls == []                       # danach still


def test_neustart_mit_gesetztem_merker_fuehrt_folge_erneut_aus(tmp_path):
    LatchStore(tmp_path / "notabschaltung.json").save(
        Latch(True, "2026-10-01T14:30:05+02:00", {"entity": "binary_sensor.netz"}))
    ha = FakeHA()
    stop = make_stop(tmp_path, ha, devices=DEVICES, targets=TARGETS)
    stop.load()
    assert stop.active is True
    run(stop.run_due_sequence())
    assert "select.select_option select.akku_modus" in ha.calls
    ha.calls.clear()
    run(stop.run_due_sequence())                # nur einmal je Start
    assert ha.calls == []


def test_merker_nicht_schreibbar_wirft_trotzdem_ab(tmp_path):
    (tmp_path / "blockiert").write_text("", encoding="utf-8")   # Datei statt Ordner
    ha = FakeHA()
    stop = EmergencyStop(ha=ha, store=LatchStore(tmp_path / "blockiert" / "n.json"),
                         config=EmergencyConfig("binary_sensor.netz", "==", "off"),
                         device_configs=DEVICES)
    run(stop.trigger_now(evaluate("binary_sensor.netz", "==", "off", entry("off"))))
    assert stop.active is True
    assert ha.calls                              # abgeworfen wurde trotzdem
    assert "nicht beschreibbar" in stop.file_error


# ---------------------------------------------------------------------------
# Quittieren
# ---------------------------------------------------------------------------

def _aktiv(tmp_path, ha, **kwargs):
    stop = make_stop(tmp_path, ha, **kwargs)
    run(stop.trigger_now(evaluate("binary_sensor.netz", "==", "off", entry("off"))))
    return stop


def test_quittieren_gesperrt_solange_bedingung_zutrifft(tmp_path):
    stop = _aktiv(tmp_path, FakeHA())
    reason = run(stop.acknowledge(entry("off")))
    assert "trifft noch zu" in reason
    assert stop.active is True


def test_quittieren_gesperrt_wenn_bedingung_nicht_pruefbar(tmp_path):
    stop = _aktiv(tmp_path, FakeHA())
    reason = run(stop.acknowledge(entry("unavailable")))
    assert "nicht prüfbar" in reason
    assert stop.active is True


def test_quittieren_loescht_merker(tmp_path):
    stop = _aktiv(tmp_path, FakeHA(fail={"select.akku_modus"}), targets=TARGETS)
    assert run(stop.acknowledge(entry("on"))) == ""
    assert stop.active is False
    assert stop.pending_ops == []
    latch, _ = LatchStore(tmp_path / "notabschaltung.json").load()
    assert latch.active is False


def test_quittieren_ohne_konfigurierte_bedingung_erlaubt(tmp_path):
    LatchStore(tmp_path / "notabschaltung.json").save(Latch(True))
    stop = make_stop(tmp_path, FakeHA(), entity="")
    stop.load()
    assert run(stop.acknowledge(None)) == ""
    assert stop.active is False


def test_status_dict(tmp_path):
    stop = _aktiv(tmp_path, FakeHA())
    stop.check(entry("off"))
    status = stop.to_status_dict()
    assert status["active"] is True
    assert status["since"] == "01.10.2026 14:30:05"
    assert status["can_acknowledge"] is False
    assert "trifft noch zu" in status["ack_block_reason"]
    assert status["trigger"]["operator_label"] == "="


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

def test_konfiguration_defaults():
    options = cfg.validate_options({}).options
    assert options["emergency_condition_entity"] == ""
    assert options["emergency_condition_operator"] == "=="
    assert options["emergency_targets"] == []


def test_konfiguration_feldfehler_mit_pfaden():
    result = cfg.validate_options({
        "emergency_condition_entity": "kein entity",
        "emergency_condition_operator": ">",
        "emergency_condition_value": "aus",
        "emergency_targets": [
            {"entity": "switch.ok", "value": "off"},
            {"entity": "sensor.x", "value": "1"},
            {"entity": "select.y", "value": ""},
        ],
    })
    errors = result.field_errors
    assert "emergency_condition_entity" in errors
    assert "emergency_condition_value" in errors
    assert "emergency_targets[0].entity" not in errors
    assert "emergency_targets[1].entity" in errors
    assert "emergency_targets[2].value" in errors


def test_konfiguration_gueltig():
    result = cfg.validate_options({
        "emergency_condition_entity": "binary_sensor.netz",
        "emergency_condition_operator": "==",
        "emergency_condition_value": "off",
        "emergency_targets": [{"entity": "select.akku_modus", "value": "auto"}],
    })
    assert not [key for key in result.field_errors if key.startswith("emergency")]


def test_merge_uebernimmt_notabschaltung():
    merged = cfg.merge_known_fields({}, {"emergency_targets": [{"entity": "switch.a", "value": "off"}]})
    assert merged["emergency_targets"] == [{"entity": "switch.a", "value": "off"}]


def test_entitaeten_tragen_eingabe_attribute():
    snapshot = {
        "select.modus": {"state": "auto", "attributes": {"options": ["auto", "manuell"]}},
        "number.grenze": {"state": "5", "attributes": {"min": 0, "max": 10, "step": 0.5,
                                                        "unit_of_measurement": "kW"}},
    }
    svc = ConfigService(supervisor=None, write_ops=None, local_options={}, loaded_options={},
                        instance_id="x", entity_snapshot=lambda: snapshot)
    eintraege = {e["entity_id"]: e for e in svc.entities(["select", "number"])}
    assert eintraege["select.modus"]["options"] == ["auto", "manuell"]
    assert eintraege["number.grenze"]["max"] == 10
    assert eintraege["number.grenze"]["unit"] == "kW"


# ---------------------------------------------------------------------------
# Einbindung in main.py
# ---------------------------------------------------------------------------

def make_app(tmp_path, monkeypatch, options, states=None, fail=()):
    options_path = tmp_path / "options.json"
    options_path.write_text(json.dumps(options), encoding="utf-8")
    monkeypatch.setattr(main, "OPTIONS_PATH", options_path)
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    app = main.HEMSApp()
    ha = FakeHA(states, fail)
    app.ha = ha
    app.emergency._ha = ha
    return app, ha


EMERGENCY_OPTIONS = {
    "residual_power_entity": "sensor.ueberschuss",
    "emergency_condition_entity": "binary_sensor.netz",
    "emergency_condition_operator": "==",
    "emergency_condition_value": "off",
    "emergency_targets": [{"entity": "select.akku_modus", "value": "auto"}],
    "devices": [binary(), controllable(), battery()],
}


def test_zyklus_loest_aus_und_regelt_nicht(tmp_path, monkeypatch):
    app, ha = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "battery_residual_power_entity": "sensor.bilanz"},
                       states={"binary_sensor.netz": entry("off")})
    monkeypatch.setattr(app.ems, "run_cycle", lambda st: pytest.fail("Regelzyklus darf nicht laufen"))
    run(app._run_cycle())
    assert app.emergency.active is True
    assert ha.calls[0] == "input_boolean.turn_off input_boolean.ems_luft_anforderung_an"
    assert ha.calls[-1] == "select.select_option select.akku_modus"
    assert app._last_error == ""


def test_zyklus_mit_gesetztem_merker_nach_neustart(tmp_path, monkeypatch):
    LatchStore(tmp_path / "notabschaltung.json").save(Latch(True, "2026-10-01T14:30:05+02:00"))
    app, ha = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "battery_residual_power_entity": "sensor.bilanz"},
                       states={"binary_sensor.netz": entry("on")})
    monkeypatch.setattr(app.ems, "run_cycle", lambda st: pytest.fail("Regelzyklus darf nicht laufen"))
    run(app._run_cycle())
    assert "select.select_option select.akku_modus" in ha.calls
    ha.calls.clear()
    run(app._run_cycle())
    assert ha.calls == []                        # still bis zur Quittierung


def test_zyklus_ohne_notabschaltung_regelt_normal(tmp_path, monkeypatch):
    app, ha = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "devices": []},
                       states={"binary_sensor.netz": entry("on"), "sensor.ueberschuss": entry("0")})
    run(app._run_cycle())
    assert app.emergency.active is False
    assert app._cycle_count == 1
    assert ha.sensors[SENSOR_ENTITY_ID][0] == "off"


def test_abort_verwirft_restliche_regelbefehle(tmp_path, monkeypatch):
    app, ha = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "devices": []},
                       states={"binary_sensor.netz": entry("on"), "sensor.ueberschuss": entry("0")})
    ops = [WriteOp("input_boolean", "turn_on", {"entity_id": f"input_boolean.x{i}"}) for i in range(3)]

    async def ausloesen_waehrend_charge(write_ops, abort=None):
        app.emergency.active = True          # löst aus, während die Charge startet
        return await FakeHA.execute_write_ops(ha, write_ops, abort)

    monkeypatch.setattr(app.ems, "run_cycle", lambda st: {"status": {}, "write_ops": ops})
    monkeypatch.setattr(ha, "execute_write_ops", ausloesen_waehrend_charge)
    run(app._run_cycle())
    assert ha.calls == []
    assert app._cycle_count == 0


def test_quittieren_endpunkt_baut_controller_neu(tmp_path, monkeypatch):
    app, ha = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "devices": []},
                       states={"binary_sensor.netz": entry("off")})
    run(app._run_cycle())
    assert app.emergency.active is True

    response = run(app._handle_emergency_acknowledge(None))
    assert response.status == 409

    ha.states["binary_sensor.netz"] = entry("on")
    alter_controller = app.ems
    response = run(app._handle_emergency_acknowledge(None))
    assert response.status == 200
    assert app.emergency.active is False
    assert app.ems is not alter_controller
    assert ha.sensors[SENSOR_ENTITY_ID][0] == "off"


def test_quittieren_bei_unerreichbarem_ha_gesperrt(tmp_path, monkeypatch):
    app, ha = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "devices": []},
                       states={"binary_sensor.netz": entry("off")})
    run(app._run_cycle())
    ha.unreachable = True
    response = run(app._handle_emergency_acknowledge(None))
    assert response.status == 409
    assert app.emergency.active is True


class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def test_live_pruefung_endpunkt(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "devices": []},
                      states={"sensor.netz_spannung": entry("12")})
    response = run(app._handle_emergency_test(FakeRequest(
        {"entity": "sensor.netz_spannung", "operator": "<", "value": "100"})))
    body = json.loads(response.body)
    assert body["state"] == CONDITION_MET
    assert body["current"] == "12"

    response = run(app._handle_emergency_test(FakeRequest({"entity": "", "operator": "==", "value": ""})))
    assert json.loads(response.body)["state"] == CONDITION_INVALID


def test_ungueltige_bedingung_schaltet_ueberwachung_ab_und_meldet_es(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch, {**EMERGENCY_OPTIONS, "devices": [],
                                               "emergency_condition_operator": ">"},
                      states={"binary_sensor.netz": entry("off")})
    assert app.emergency.config.configured is False
    assert "ungültig" in app.emergency.to_status_dict()["config_error"]
