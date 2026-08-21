"""Tests für StateProxy und die Hilfsfunktionen (safe_float, parse_ts)."""

import datetime

from ems.state import StateProxy, safe_float, parse_ts


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
