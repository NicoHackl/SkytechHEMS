"""Tests für den Formel-Interpreter (D-045).

`formula.py` liegt bewusst außerhalb von `ems/` und wird hier komplett isoliert
getestet – ohne StateProxy, ohne HA-State. Die Auflösung „HA-Entität → Wert"
ist Sache von `StateProxy.resolve_formula_namespace()` (siehe test_state.py).
"""

import pytest
from hypothesis import given, settings, strategies as st

from formula import (
    FUNCTION_WHITELIST, RESERVED_OUTPUT_NAMES,
    FormulaResult, run_formula, validate_formula_source,
)


def ns(**values):
    """Baut ein Namespace-Dict mit automatischen `<name>_valid`-Begleitflaggen
    (Default: gültig, außer der Wert ist None) – spiegelt, was
    `StateProxy.resolve_formula_namespace()` zur Laufzeit liefert."""
    result = dict(values)
    for name, value in values.items():
        result.setdefault(f"{name}_valid", value is not None)
    return result


# ---- Normalfall: erlaubte Konstrukte liefern das erwartete Ergebnis ----

ALLOWED_CASES = [
    ("ueberschuss = pv - haus", ns(pv=1000.0, haus=300.0), 700.0),
    ("ueberschuss = pv + haus if pv_valid else 0", ns(pv=100.0, haus=50.0), 150.0),
    ("x = pv * 2\nueberschuss = x - haus", ns(pv=10.0, haus=5.0), 15.0),
    ("if pv > haus:\n    ueberschuss = pv\nelse:\n    ueberschuss = haus",
     ns(pv=700.0, haus=300.0), 700.0),
    ("ueberschuss = min(pv, haus)", ns(pv=700.0, haus=300.0), 300.0),
    ("ueberschuss = max(pv, 0) - abs(haus)", ns(pv=-5.0, haus=-3.0), -3.0),
    ("ueberschuss = round(pv / 3)", ns(pv=10.0), 3.0),
    ("ueberschuss = pv > 0 and haus > 0", ns(pv=5.0, haus=5.0), 1.0),
    ("ueberschuss = pv > 0 and haus > 0", ns(pv=-5.0, haus=5.0), 0.0),
    ("ueberschuss = pv or haus", ns(pv=0.0, haus=7.0), 7.0),
    ("ueberschuss = -pv", ns(pv=5.0), -5.0),
    ("ueberschuss = (-2) ** 3", ns(), -8.0),
    ("ueberschuss = pv if pv_valid else 0", ns(pv=None, haus=0.0), 0.0),
    ("ueberschuss = 1 if (pv_valid and pv > 0) else 0", ns(pv=None), 0.0),
]


@pytest.mark.parametrize("code,namespace,expected", ALLOWED_CASES)
def test_erlaubte_formel_liefert_erwarteten_wert(code, namespace, expected):
    result = run_formula(code, namespace, "ueberschuss")
    assert result.valid is True, result.error
    assert result.value == pytest.approx(expected)


def test_leerer_code_ist_als_konfiguration_gueltig_aber_liefert_keinen_wert():
    """Leer heißt „keine Formel" – gültig für die Config-Validierung (Abschnitt
    Fehlerfall unten prüft das explizit –, aber run_formula liefert dafür nie
    einen Wert, damit der Aufrufer sauber auf die konfigurierte Entität fällt."""
    assert validate_formula_source("", [], "ueberschuss") is None
    result = run_formula("", ns(pv=1.0), "ueberschuss")
    assert result.valid is False


# ---- Fehlerfall: verbotene Konstrukte werden abgelehnt ----

FORBIDDEN_SNIPPETS = [
    "for i in [1, 2]:\n    ueberschuss = i",
    "while pv > 0:\n    ueberschuss = 1",
    "def f():\n    return 1\nueberschuss = f()",
    "class X:\n    pass\nueberschuss = 1",
    "import os\nueberschuss = 1",
    "from os import path\nueberschuss = 1",
    "ueberschuss = (lambda: 1)()",
    "ueberschuss = pv.real",
    "ueberschuss = pv[0]",
    "ueberschuss = [1, 2][0]",
    "ueberschuss = {1: 2}[1]",
    "ueberschuss = (1, 2)[0]",
    "ueberschuss = {1, 2}",
    "ueberschuss = [x for x in [1]][0]",
    "ueberschuss = __import__('os')",
    "ueberschuss = f'{pv}'",
    "ueberschuss = (n := 3)",
    "ueberschuss = sum([pv, haus])",
    "ueberschuss, x = 1, 2",
    "a = b = 1\nueberschuss = a",
    "ueberschuss = 1\nueberschuss += 1",
    "try:\n    ueberschuss = 1\nexcept Exception:\n    pass",
    "with open('x') as f:\n    ueberschuss = 1",
    "assert pv > 0\nueberschuss = 1",
    "raise ValueError()",
    "global pv\nueberschuss = 1",
    "ueberschuss = 1\ndel ueberschuss",
    "ueberschuss = pv is haus",
    "ueberschuss = pv in [1, 2]",
    "ueberschuss = *[1, 2],",
    "ueberschuss = __builtins__",
    "ueberschuss = os.system('echo hi')",
    "ueberschuss = unbekannter_name",
]


@pytest.mark.parametrize("code", FORBIDDEN_SNIPPETS)
def test_verbotenes_konstrukt_wird_abgelehnt(code):
    error = validate_formula_source(code, ["pv", "pv_valid", "haus", "haus_valid"], "ueberschuss")
    assert error is not None, f"hätte abgelehnt werden müssen: {code!r}"

    result = run_formula(code, ns(pv=1.0, haus=1.0), "ueberschuss")
    assert result.valid is False


def test_syntaxfehler_wird_mit_zeile_gemeldet():
    error = validate_formula_source("ueberschuss = (", [], "ueberschuss")
    assert error is not None
    assert "Syntaxfehler" in error


def test_fehlende_zuweisung_an_ausgabevariable():
    error = validate_formula_source("x = pv - haus", ["pv", "haus"], "ueberschuss")
    assert error == "Der Code muss der Variable 'ueberschuss' einen Wert zuweisen."


def test_division_durch_null_faellt_sauber_zurueck():
    result = run_formula("ueberschuss = pv / haus", ns(pv=10.0, haus=0.0), "ueberschuss")
    assert result.valid is False
    assert "0" in result.error


def test_ungeschuetzter_none_wert_scheitert_sauber_statt_zu_werfen():
    """Ohne den `_valid`-Guard zu prüfen, mit einem ungültigen Sensor zu rechnen,
    ist ein Formel-Fehler – nie ein Absturz des Regelzyklus."""
    result = run_formula("ueberschuss = pv - haus",
                         ns(pv=None, haus=500.0), "ueberschuss")
    assert result.valid is False
    assert "pv" in result.error


def test_ueberlauf_bei_riesiger_potenz_faellt_sauber_zurueck():
    """`10.0 ** 400` überschreitet den float-Wertebereich – CPython wirft dafür
    `OverflowError` statt still `inf` zurückzugeben. Beide Fälle sind bei einer
    Formel ohnehin abgedeckt: `run_formula()` fängt `OverflowError` gezielt ab,
    und ein durchgerutschtes `inf` würde die abschließende isfinite()-Prüfung
    abfangen (siehe test_wiederholtes_quadrieren_..., das genau diesen Weg nimmt)."""
    result = run_formula("ueberschuss = 10.0 ** 400", ns(), "ueberschuss")
    assert result.valid is False


def test_pow_negative_basis_mit_gebrochenem_exponenten_wird_abgelehnt():
    """`(-8) ** 0.5` würde in echtem Python still eine komplexe Zahl erzeugen –
    hier ein sauberer Formel-Fehler statt eines späteren Absturzes."""
    result = run_formula("ueberschuss = (-8) ** 0.5", ns(), "ueberschuss")
    assert result.valid is False


def test_zeilennamen_kollidieren_nicht_mit_ausgabevariablen():
    for reserved in RESERVED_OUTPUT_NAMES:
        assert reserved in ("ueberschuss", "hausbilanz")  # Vertragsprüfung, siehe configuration.py


def test_funktions_whitelist_enthaelt_nur_die_dokumentierten_namen():
    assert set(FUNCTION_WHITELIST) == {"abs", "min", "max", "round"}


# ---- Regressionstest: Bigint-Eskalation ohne jede Schleife ----

def test_wiederholtes_quadrieren_bleibt_endlich_statt_zu_einer_riesenzahl_anzuwachsen():
    """`a = a * a` 40 Mal hintereinander würde als Python-`int` (beliebige
    Genauigkeit) auf ~2^(2^40) anwachsen – eine Zahl mit hunderten Milliarden
    Stellen, allein durch Zuweisung und Multiplikation, ganz ohne Schleife.
    Als `float` läuft das kontrolliert in `inf`. Bliebe die Float-Erzwingung
    aus, würde dieser Test nicht fehlschlagen, sondern hängen oder den
    Testlauf mit einem Speicherfehler abbrechen – das macht eine Regression
    hier praktisch unübersehbar, auch ohne explizite Zeitmessung.
    """
    code = "a = pv\n" + "a = a * a\n" * 40 + "ueberschuss = a"
    result = run_formula(code, ns(pv=2.0), "ueberschuss")
    assert result.valid is False
    assert "endlich" in result.error.lower()


# ---- Hypothesis: der Interpreter ist eine totale Funktion – nie ein Absturz ----
#
# Anders als die Pool-Verteilung (test_allocation_properties.py) hat eine
# Formel-Sprache keine numerische Eigenschaft, die sich über zufällige gültige
# Formeln generativ prüfen ließe, ohne selbst einen Python-Code-Generator zu
# schreiben. Die für einen handgeschriebenen Parser/Interpreter wertvollste
# Hypothesis-Eigenschaft ist Robustheit gegen beliebigen Text: `validate_
# formula_source()` und `run_formula()` dürfen NIE eine Exception nach außen
# durchlassen, komplett unabhängig davon, was als Code hineinkommt.

_random_source = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),  # keine Surrogate (macht encode() instabil)
    max_size=200,
)


@settings(max_examples=200)
@given(source=_random_source)
def test_validate_wirft_nie_bei_beliebigem_text(source):
    result = validate_formula_source(source, ["pv", "pv_valid"], "ueberschuss")
    assert result is None or isinstance(result, str)


@settings(max_examples=200)
@given(source=_random_source)
def test_run_formula_wirft_nie_bei_beliebigem_text(source):
    result = run_formula(source, ns(pv=1.0), "ueberschuss")
    assert isinstance(result, FormulaResult)
    assert result.valid in (True, False)
