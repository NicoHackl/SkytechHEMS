"""HEMS-interne Ersatzwerte für HA-Helfer (D-061).

Reihenfolge: gültiger HA-Helfer → HEMS-interner Wert → Add-on-Feld → Default.
Freigaben und Zwang gibt es ausschließlich als echten HA-Helfer.
"""

import json

import pytest

from ems.state import (
    SOURCE_ADDON,
    SOURCE_HA,
    SOURCE_HEMS,
    SOURCE_INTERNAL,
    STATE_INVALID,
    STATE_MISSING,
    STATE_UNAVAILABLE,
    STATE_VALID,
    StateProxy,
    is_gate_entity,
)
from internal_values import InternalValueError, InternalValueStore, validate_value

from test_configuration import binary
from test_emergency import FakeRequest, entry, make_app, run

POWER = "input_number.ems_luft_leistung_w"


def proxy(states=None, internal=None):
    return StateProxy({eid: entry(value) for eid, value in (states or {}).items()}, internal=internal)


# ---------------------------------------------------------------------------
# Resolve-Kette
# ---------------------------------------------------------------------------

def test_gueltiger_helfer_schlaegt_internen_wert():
    r = proxy({POWER: "1500"}, {POWER: 900.0}).resolve_number(POWER, addon=700.0)
    assert (r.value, r.state, r.source) == (1500.0, STATE_VALID, SOURCE_HA)


def test_gueltige_null_im_helfer_wird_nicht_ersetzt():
    r = proxy({POWER: "0"}, {POWER: 900.0}).resolve_number(POWER, addon=700.0)
    assert (r.value, r.source) == (0.0, SOURCE_HA)


@pytest.mark.parametrize("states, state", [
    ({}, STATE_MISSING),
    ({POWER: "unavailable"}, STATE_UNAVAILABLE),
    ({POWER: "kaputt"}, STATE_INVALID),
])
def test_interner_wert_vor_addon_feld_mit_urspruenglicher_ursache(states, state):
    r = proxy(states, {POWER: 900.0}).resolve_number(POWER, addon=700.0, internal=0.0)
    assert (r.value, r.state, r.source) == (900.0, state, SOURCE_HEMS)


def test_ohne_internen_wert_bleibt_die_bisherige_kette():
    assert proxy().resolve_number(POWER, addon=700.0).source == SOURCE_ADDON
    assert proxy().resolve_number(POWER, internal=5.0).source == SOURCE_INTERNAL


def test_interner_wert_ausserhalb_zwingender_grenzen_greift_trotzdem_nur_als_ersatz():
    soc = "input_number.ems_acspeicher1_soc_min_prozent"
    r = proxy({soc: "150"}, {soc: 20.0}).resolve_number(soc, minimum=0.0, maximum=100.0)
    assert (r.value, r.state, r.source) == (20.0, STATE_INVALID, SOURCE_HEMS)


def test_schalter_intern_schlaegt_missing_fallback():
    """Speicher: fehlendes laden_erlaubt heißt sonst „erlaubt“ – ein interner Wert gewinnt."""
    eid = "input_boolean.ems_acspeicher1_laden_erlaubt"
    r = proxy(internal={eid: False}).resolve_bool(eid, fallback=False, missing_fallback=True)
    assert (r.value, r.state, r.source) == (False, STATE_MISSING, SOURCE_HEMS)
    assert proxy({eid: "on"}, {eid: False}).resolve_bool(eid).value is True


def test_auswahl_intern_nur_mit_erlaubter_option():
    eid = "input_select.ems_luft_modus"
    options = ("auto", "manuell", "aus")
    assert proxy(internal={eid: "aus"}).resolve_select(eid, options, fallback="manuell").source == SOURCE_HEMS
    falsch = proxy(internal={eid: "quatsch"}).resolve_select(eid, options, fallback="manuell")
    assert (falsch.value, falsch.source) == ("manuell", SOURCE_INTERNAL)


@pytest.mark.parametrize("eid", [
    "input_boolean.ems_pv_regelung_aktiv",
    "input_boolean.ems_luft_freigabe",
    "input_boolean.ems_luft_technische_freigabe",
    "input_boolean.ems_luft_force",
    "input_number.ems_heizstab_force_leistung_w",
])
def test_freigaben_und_zwang_ignorieren_interne_werte(eid):
    assert is_gate_entity(eid)
    sp = proxy(internal={eid: True if eid.startswith("input_boolean") else 2000.0})
    if eid.startswith("input_boolean"):
        r = sp.resolve_bool(eid)
        assert (r.value, r.source) == (False, SOURCE_INTERNAL)
    else:
        assert sp.resolve_number(eid).source == SOURCE_INTERNAL


def test_resolve_raw_liefert_rohen_state_sonst_intern():
    eid = "input_select.ems_regelmodus"
    assert proxy({eid: "erfunden"}).resolve_raw(eid).value == "erfunden"
    r = proxy(internal={eid: "manuell"}).resolve_raw(eid)
    assert (r.value, r.state, r.source) == ("manuell", STATE_MISSING, SOURCE_HEMS)
    assert proxy().resolve_raw(eid).value is None


# ---------------------------------------------------------------------------
# Eingabeprüfung
# ---------------------------------------------------------------------------

NUMBER = {"entity": POWER, "label": "Leistung", "kind": "number", "internal_editable": True,
          "min": 0, "integer": False}


def test_validate_value_prueft_typ_und_grenzen():
    assert validate_value(NUMBER, "1500") == 1500.0
    with pytest.raises(InternalValueError):
        validate_value(NUMBER, -1)
    with pytest.raises(InternalValueError):
        validate_value(NUMBER, "abc")
    with pytest.raises(InternalValueError):
        validate_value({**NUMBER, "integer": True}, 1.5)
    with pytest.raises(InternalValueError):
        validate_value({**NUMBER, "max": 100}, 101)
    select = {"kind": "select", "internal_editable": True, "options": ["auto", "aus"]}
    assert validate_value(select, "aus") == "aus"
    with pytest.raises(InternalValueError):
        validate_value(select, "manuell")
    assert validate_value({"kind": "bool", "internal_editable": True}, "on") is True
    with pytest.raises(InternalValueError):
        validate_value({**NUMBER, "internal_editable": False}, 5)


# ---------------------------------------------------------------------------
# Datei
# ---------------------------------------------------------------------------

def test_datei_speichert_und_setzt_zurueck(tmp_path):
    store = InternalValueStore(tmp_path / "sub" / "interne_werte.json")
    store.load()
    assert store.snapshot() == {}
    store.set(POWER, 900.0)
    neu = InternalValueStore(store.path)
    neu.load()
    assert neu.snapshot() == {POWER: 900.0}
    neu.reset(POWER)
    assert json.loads(store.path.read_text(encoding="utf-8")) == {"values": {}}


def test_unlesbare_datei_wirkt_nicht_und_wird_nicht_ueberschrieben(tmp_path):
    path = tmp_path / "interne_werte.json"
    path.write_text("{kaputt", encoding="utf-8")
    store = InternalValueStore(path)
    store.load()
    assert store.snapshot() == {}
    assert "unlesbar" in store.file_error
    with pytest.raises(InternalValueError):
        store.set(POWER, 1.0)
    assert path.read_text(encoding="utf-8") == "{kaputt"


def test_datei_ignoriert_freigaben_von_hand(tmp_path):
    path = tmp_path / "interne_werte.json"
    path.write_text(json.dumps({"values": {"input_boolean.ems_luft_freigabe": True, POWER: 5}}),
                    encoding="utf-8")
    store = InternalValueStore(path)
    store.load()
    assert store.snapshot() == {POWER: 5}
    with pytest.raises(InternalValueError):
        store.set("input_boolean.ems_luft_technische_freigabe", True)


# ---------------------------------------------------------------------------
# Einbindung in main.py
# ---------------------------------------------------------------------------

OPTIONS = {"residual_power_entity": "sensor.ueberschuss", "devices": [binary()]}


def test_endpunkte_setzen_pruefen_und_loeschen(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch, OPTIONS)
    ok = run(app._handle_internal_value_set(FakeRequest({"entity_id": POWER, "value": 900})))
    assert ok.status == 200
    assert app.internal_values.get(POWER) == 900.0

    gate = run(app._handle_internal_value_set(FakeRequest(
        {"entity_id": "input_boolean.ems_luft_freigabe", "value": True})))
    assert gate.status == 400
    fremd = run(app._handle_internal_value_set(FakeRequest(
        {"entity_id": "input_number.ems_gibt_es_nicht_w", "value": 1})))
    assert fremd.status == 404
    negativ = run(app._handle_internal_value_set(FakeRequest({"entity_id": POWER, "value": -5})))
    assert negativ.status == 400

    body = json.loads(run(app._handle_internal_values(None)).body)
    assert body == {"values": {POWER: 900.0}, "file_error": ""}

    assert run(app._handle_internal_value_reset(FakeRequest({"entity_id": POWER}))).status == 200
    assert app.internal_values.snapshot() == {}


def test_interner_wert_wirkt_im_zyklus_nur_ohne_helfer(tmp_path, monkeypatch):
    app, ha = make_app(tmp_path, monkeypatch, OPTIONS, states={"sensor.ueberschuss": entry("0")})
    app.internal_values.set(POWER, 2222.0)
    app.internal_values.set("input_number.ems_globaler_puffer_w", 150.0)
    run(app._run_cycle())
    device = app._last_status["devices"][0]
    assert device["power_w"] == 2222.0
    assert device["entity_diagnostics"][POWER] == {
        "role": "power_w", "state": STATE_MISSING, "source": SOURCE_HEMS, "value": 2222.0,
    }
    puffer = app._last_status["global_entity_diagnostics"]["input_number.ems_globaler_puffer_w"]
    assert (puffer["source"], puffer["value"]) == (SOURCE_HEMS, 150.0)

    ha.states[POWER] = entry("1800")
    run(app._run_cycle())
    device = app._last_status["devices"][0]
    assert device["power_w"] == 1800.0
    assert device["entity_diagnostics"][POWER]["source"] == SOURCE_HA


def test_globale_diagnose_unbekannter_modus_bleibt_roh(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch, OPTIONS, states={
        "sensor.ueberschuss": entry("0"), "input_select.ems_regelmodus": entry("erfunden"),
    })
    run(app._run_cycle())
    assert app._last_status["global_mode"] == "erfunden"
    assert app._last_status["global_mode_configured"] is False
    diag = app._last_status["global_entity_diagnostics"]
    assert diag["input_boolean.ems_pv_regelung_aktiv"]["source"] == SOURCE_INTERNAL
