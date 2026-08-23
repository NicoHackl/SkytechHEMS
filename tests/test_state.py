"""Tests für StateProxy und die Hilfsfunktionen (safe_float, parse_ts)."""

import datetime

from ems.state import (
    StateProxy, safe_float, parse_ts,
    STATE_VALID, STATE_MISSING, STATE_UNAVAILABLE, STATE_INVALID,
    SOURCE_HA, SOURCE_ADDON, SOURCE_INTERNAL,
)


def test_safe_float_valid():
    assert safe_float("12.5") == 12.5
    assert safe_float(3) == 3.0


def test_safe_float_invalid_uses_default():
    assert safe_float("abc") == 0.0
    assert safe_float(None) == 0.0
    assert safe_float("unavailable", default=-1.0) == -1.0


def test_parse_ts_none_is_zero():
    assert parse_ts(None) == 0.0


def test_parse_ts_numeric_passthrough():
    assert parse_ts(1700000000) == 1700000000.0


def test_parse_ts_iso_with_z():
    # 2023-11-14T22:13:20Z entspricht einem festen Epoch-Wert
    ts = parse_ts("2023-11-14T22:13:20Z")
    expected = datetime.datetime(2023, 11, 14, 22, 13, 20,
                                 tzinfo=datetime.timezone.utc).timestamp()
    assert ts == expected


def test_parse_ts_garbage_is_zero():
    assert parse_ts("nicht-ein-datum") == 0.0


def test_stateproxy_get_state_and_default():
    sp = StateProxy({"sensor.x": {"state": "42", "attributes": {}, "last_changed": None}})
    assert sp.get("sensor.x") == "42"
    assert sp.get("sensor.missing") is None
    assert sp.get("sensor.missing", "fallback") == "fallback"


def test_stateproxy_last_changed_accessor():
    sp = StateProxy({"sensor.x": {"state": "1", "attributes": {}, "last_changed": "2023-01-01T00:00:00Z"}})
    assert sp.get("sensor.x.last_changed") == "2023-01-01T00:00:00Z"
    assert sp.get("sensor.missing.last_changed") is None


def test_stateproxy_getattr():
    sp = StateProxy({"sensor.x": {"state": "1", "attributes": {"unit": "W"}, "last_changed": None}})
    assert sp.getattr("sensor.x") == {"unit": "W"}
    assert sp.getattr("sensor.missing") is None


# ---- Charakterisierung: Lücken, die der Resolve-Vertrag schließt ----

def test_stateproxy_get_trennt_fehlend_und_null_nicht():
    """`get()` liefert für beide Fälle None – deshalb braucht es eine eigene Präsenzprüfung."""
    sp = StateProxy({"sensor.null": {"state": None, "attributes": {}, "last_changed": None}})
    assert sp.get("sensor.null") is None
    assert sp.get("sensor.gibt_es_nicht") is None


def test_safe_float_laesst_nan_und_unendlich_durch():
    """`safe_float` prüft nur die Umwandlung, nicht die Endlichkeit."""
    assert safe_float("inf") == float("inf")
    assert safe_float("nan") != safe_float("nan")   # NaN ist zu sich selbst ungleich


# ---- Resolve-Vertrag: Wert, Ursache und Quelle ----

def proxy(**states):
    return StateProxy({
        eid: {"state": value, "attributes": {}, "last_changed": None}
        for eid, value in states.items()
    })


def test_has_trennt_fehlend_von_vorhandenem_null():
    sp = proxy(**{"sensor.null": None})
    assert sp.has("sensor.null") is True
    assert sp.has("sensor.weg") is False


def test_availability_kennt_drei_faelle():
    sp = proxy(**{"sensor.ok": "5", "sensor.aus": "unavailable", "sensor.unbekannt": "unknown"})
    assert sp.availability("sensor.ok") == STATE_VALID
    assert sp.availability("sensor.aus") == STATE_UNAVAILABLE
    assert sp.availability("sensor.unbekannt") == STATE_UNAVAILABLE
    assert sp.availability("sensor.weg") == STATE_MISSING


def test_resolve_number_gueltiger_wert_kommt_aus_ha():
    r = proxy(**{"sensor.x": "1500"}).resolve_number("sensor.x", addon=99.0)
    assert (r.value, r.state, r.source) == (1500.0, STATE_VALID, SOURCE_HA)


def test_resolve_number_gueltige_null_wird_nicht_ersetzt():
    """Der wichtigste Fall: 0 ist ein Wert, kein Anlass für einen Fallback."""
    r = proxy(**{"sensor.x": "0"}).resolve_number("sensor.x", addon=99.0)
    assert (r.value, r.source) == (0.0, SOURCE_HA)


def test_resolve_number_fehlend_und_unavailable_teilen_den_wert_nicht_die_ursache():
    fehlend = proxy().resolve_number("sensor.x", addon=99.0)
    aus = proxy(**{"sensor.x": "unavailable"}).resolve_number("sensor.x", addon=99.0)
    assert fehlend.value == aus.value == 99.0
    assert fehlend.state == STATE_MISSING
    assert aus.state == STATE_UNAVAILABLE
    assert fehlend.source == aus.source == SOURCE_ADDON


def test_resolve_number_nicht_numerisch_ist_ungueltig():
    r = proxy(**{"sensor.x": "kaputt"}).resolve_number("sensor.x", addon=7.0)
    assert (r.value, r.state, r.source) == (7.0, STATE_INVALID, SOURCE_ADDON)


def test_resolve_number_nan_und_unendlich_sind_ungueltig():
    for raw in ("nan", "inf", "-inf"):
        r = proxy(**{"sensor.x": raw}).resolve_number("sensor.x", internal=3.0)
        assert (r.value, r.state) == (3.0, STATE_INVALID), raw


def test_resolve_number_bereichsverletzung_ist_ungueltig():
    r = proxy(**{"sensor.x": "-5"}).resolve_number("sensor.x", internal=0.0, minimum=0.0)
    assert (r.value, r.state) == (0.0, STATE_INVALID)
    r = proxy(**{"sensor.x": "150"}).resolve_number("sensor.x", internal=0.0, maximum=100.0)
    assert r.state == STATE_INVALID


def test_resolve_number_addon_schlaegt_internen_default():
    r = proxy().resolve_number("sensor.x", addon=5.0, internal=9.0)
    assert (r.value, r.source) == (5.0, SOURCE_ADDON)


def test_resolve_number_ohne_ersatzwert_liefert_none():
    r = proxy().resolve_number("sensor.x")
    assert (r.value, r.state, r.source) == (None, STATE_MISSING, SOURCE_INTERNAL)


def test_resolve_bool_liest_on_und_off():
    sp = proxy(**{"input_boolean.a": "on", "input_boolean.b": "off"})
    assert sp.resolve_bool("input_boolean.a").value is True
    assert sp.resolve_bool("input_boolean.b").value is False


def test_resolve_bool_trennt_fehlend_von_ausgefallen():
    """Der Speicher braucht genau das: fehlt die Freigabe, gilt sie als erteilt."""
    fehlend = proxy().resolve_bool("input_boolean.laden_erlaubt",
                                   fallback=False, missing_fallback=True)
    aus = proxy(**{"input_boolean.laden_erlaubt": "unavailable"}).resolve_bool(
        "input_boolean.laden_erlaubt", fallback=False, missing_fallback=True)
    assert (fehlend.value, fehlend.state) == (True, STATE_MISSING)
    assert (aus.value, aus.state) == (False, STATE_UNAVAILABLE)


def test_resolve_bool_unbrauchbarer_state_ist_ungueltig():
    r = proxy(**{"input_boolean.a": "vielleicht"}).resolve_bool(
        "input_boolean.a", fallback=False, missing_fallback=True)
    assert (r.value, r.state) == (False, STATE_INVALID)


def test_resolve_select_akzeptiert_nur_bekannte_optionen():
    sp = proxy(**{"input_select.m": "nur_laden"})
    ok = sp.resolve_select("input_select.m", ("auto", "nur_laden"), fallback="standby")
    assert (ok.value, ok.state, ok.source) == ("nur_laden", STATE_VALID, SOURCE_HA)
    schlecht = sp.resolve_select("input_select.m", ("auto",), fallback="standby")
    assert (schlecht.value, schlecht.state) == ("standby", STATE_INVALID)


def test_resolve_select_fehlend_nutzt_den_ersatzwert():
    r = proxy().resolve_select("input_select.m", ("auto",), fallback="standby")
    assert (r.value, r.state, r.source) == ("standby", STATE_MISSING, SOURCE_INTERNAL)


# ---- resolve_formula_namespace (D-045): volle Matrix je Zeile ----

def test_resolve_formula_namespace_volle_matrix_je_zeile():
    """Pflicht-Testfall 13 (test-strategie.md): gültiger Wert, gültiger
    Nullwert, fehlende Entität, unavailable, unknown, nicht-numerisch – Wert
    und Diagnose getrennt geprüft."""
    sp = proxy(**{
        "sensor.a": "700",
        "sensor.b": "0",
        "sensor.d": "unavailable",
        "sensor.e": "unknown",
        "sensor.f": "kaputt",
    })
    variables = [
        {"name": "a", "entity": "sensor.a"},   # gültiger Wert
        {"name": "b", "entity": "sensor.b"},   # gültiger Nullwert – kein Fallback!
        {"name": "c", "entity": "sensor.c"},   # fehlende Entität
        {"name": "d", "entity": "sensor.d"},   # unavailable
        {"name": "e", "entity": "sensor.e"},   # unknown
        {"name": "f", "entity": "sensor.f"},   # nicht-numerisch
    ]
    namespace, diagnostics = sp.resolve_formula_namespace(variables)

    assert namespace["a"] == 700.0 and namespace["a_valid"] is True
    assert namespace["b"] == 0.0 and namespace["b_valid"] is True
    assert namespace["c"] is None and namespace["c_valid"] is False
    assert namespace["d"] is None and namespace["d_valid"] is False
    assert namespace["e"] is None and namespace["e_valid"] is False
    assert namespace["f"] is None and namespace["f_valid"] is False

    by_name = {d["name"]: d for d in diagnostics}
    assert by_name["a"]["state"] == STATE_VALID and by_name["a"]["source"] == SOURCE_HA
    assert by_name["c"]["state"] == STATE_MISSING
    assert by_name["d"]["state"] == STATE_UNAVAILABLE
    assert by_name["e"]["state"] == STATE_UNAVAILABLE  # "unknown" fällt unter denselben Zustand
    assert by_name["f"]["state"] == STATE_INVALID
    for name in ("c", "d", "e", "f"):
        assert by_name[name]["value"] is None
        assert by_name[name]["valid"] is False


def test_resolve_formula_namespace_leere_zeilenliste():
    namespace, diagnostics = proxy().resolve_formula_namespace([])
    assert namespace == {}
    assert diagnostics == []
