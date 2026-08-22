"""Eingeschränkter Formel-Interpreter für nutzerdefinierte Sensorwerte (D-045).

Wertet den Python-ähnlichen Code aus, den der Nutzer im Ingress-Panel unter
„Sensoren" hinterlegt. Der Regelzyklus läuft synchron in einem einzigen
asyncio-Prozess (app/main.py `_scheduler()`/`_run_cycle()`, app/ems/controller.py
`run_cycle()`) – hängender Code würde dort auch die Notabschaltung blockieren.
Deshalb kein `eval`/`exec` auf kompiliertem Python, sondern ein eigener,
baumwandelnder Auswerter über eine AST-Whitelist: nur Zuweisungen, Arithmetik,
Vergleiche, boolesche Verknüpfungen und if/else sind erlaubt. Ohne Schleifen,
Funktionsdefinitionen, Imports und Attributzugriffe ist die Ausführung
strukturell auf die Anzahl der Ausdrucksbausteine im Quelltext beschränkt – kein
Timeout und kein Prozess-/Thread-Wechsel nötig. Der Verzicht auf `exec()`
schließt außerdem das bekannte CPython-Verhalten aus, `__builtins__`
automatisch in den `globals`-Dict einzufügen, wenn keiner gesetzt ist.

Zahlen bleiben während der gesamten Auswertung `float` (IEEE 754, feste Breite).
Das ist keine Kosmetik: Python-`int` hat beliebige Genauigkeit, und `a = a * a`
40 Mal wiederholt – ganz ohne Schleife, rein durch erlaubte Zuweisungen und
Multiplikationen – ließe eine Ganzzahl auf Hunderte Milliarden Stellen wachsen.
`float * float` ist dagegen unabhängig vom Operandenwert O(1) und läuft bei
Überlauf in `inf`, was die abschließende `math.isfinite()`-Prüfung ohnehin
abfängt.

Bewusst ohne Abhängigkeit auf `ems.*` oder `configuration.py`: läge dieses Modul
unter `app/ems/` und importierte von dort etwas aus `ems.state`, entstünde beim
Laden von `configuration.py` ein zirkulärer Import (configuration.py →
app.formula → ems.state → ems/__init__.py → ems.controller → configuration.py).
Dieses Modul bekommt daher nur ein fertiges Dict aufgelöster Werte übergeben,
nie eine HA-Entity-ID.

Vertrag für `variable_names`/`namespace`: Für jede Formel-Zeile mit dem Namen
`<n>` müssen sowohl `<n>` (Wert oder `None`) als auch `<n>_valid` (bool)
enthalten sein – Letzteres lässt eine Formel Verfügbarkeit selbst prüfen, bevor
sie einen möglicherweise ungültigen Wert verrechnet (siehe
`StateProxy.resolve_formula_namespace` in `app/ems/state.py`).
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

# Nur diese Funktionen darf ein Formel-Code aufrufen.
FUNCTION_WHITELIST = {"abs": abs, "min": min, "max": max, "round": round}

# Reservierte Ausgabevariablen – dürfen nicht als Zeilen-Variablenname vergeben
# werden (geprüft in app/configuration.py, das diese Konstante importiert).
RESERVED_OUTPUT_NAMES = ("ueberschuss", "hausbilanz")

# Zweite Absicherung neben der AST-Whitelist: verhindert unangemessen große
# Eingaben, ohne dass das je eine reale Formel beträfe.
MAX_SOURCE_LENGTH = 4000
MAX_NODES = 500

_ALLOWED_STMT_TYPES = (ast.Assign, ast.If)
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub, ast.Not)
_ALLOWED_BOOLOPS = (ast.And, ast.Or)
_ALLOWED_CMPOPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)


@dataclass(frozen=True)
class FormulaResult:
    """Ergebnis eines Formel-Laufs. `valid=False` heißt für den Aufrufer: auf den
    bestehenden Entitäts-Pfad zurückfallen – ein Regelzyklus bricht dafür nie ab."""

    value: Optional[float]
    valid: bool
    error: Optional[str]
    error_line: Optional[int]


def _fail(message: str, line: Optional[int] = None) -> FormulaResult:
    return FormulaResult(value=None, valid=False, error=message, error_line=line)


class _ForbiddenNode(Exception):
    """Wird beim statischen Prüfen für jedes nicht erlaubte Konstrukt geworfen."""

    def __init__(self, message: str, line: Optional[int]):
        super().__init__(message)
        self.message = message
        self.line = line


class _EvalError(Exception):
    """Interner Fehler beim Auswerten – von `run_formula()` immer gefangen."""


def _check_stmts(stmts, allowed: frozenset, where: str) -> None:
    for stmt in stmts:
        if not isinstance(stmt, _ALLOWED_STMT_TYPES):
            raise _ForbiddenNode(
                f"{where}: nur Zuweisungen und if/else sind erlaubt, nicht "
                f"'{type(stmt).__name__}'.",
                getattr(stmt, "lineno", None),
            )
        _check_node(stmt, allowed)


def _check_node(node: ast.AST, allowed: frozenset) -> None:
    """Wirft `_ForbiddenNode`, sobald ein nicht erlaubtes Konstrukt auftaucht.

    Jeder Zweig endet mit `return` – was zu keinem Zweig passt, fällt auf den
    letzten `raise` durch. Das macht die Prüfung „deny by default": ein neuer
    AST-Knotentyp, an den beim Schreiben nicht gedacht wurde, ist automatisch
    verboten statt automatisch erlaubt.
    """
    line = getattr(node, "lineno", None)

    if isinstance(node, ast.Module):
        _check_stmts(node.body, allowed, "Hauptteil")
        return

    if isinstance(node, ast.Assign):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise _ForbiddenNode("Zuweisungsziel muss ein einfacher Variablenname sein.", line)
        _check_node(node.value, allowed)
        return

    if isinstance(node, ast.If):
        _check_node(node.test, allowed)
        _check_stmts(node.body, allowed, "if-Zweig")
        _check_stmts(node.orelse, allowed, "else-Zweig")
        return

    if isinstance(node, ast.IfExp):
        _check_node(node.test, allowed)
        _check_node(node.body, allowed)
        _check_node(node.orelse, allowed)
        return

    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, _ALLOWED_BOOLOPS):
            raise _ForbiddenNode("Nicht erlaubter boolescher Operator.", line)
        for value in node.values:
            _check_node(value, allowed)
        return

    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARYOPS):
            raise _ForbiddenNode("Nicht erlaubter unärer Operator.", line)
        _check_node(node.operand, allowed)
        return

    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise _ForbiddenNode(f"Operator '{type(node.op).__name__}' ist nicht erlaubt.", line)
        _check_node(node.left, allowed)
        _check_node(node.right, allowed)
        return

    if isinstance(node, ast.Compare):
        for op in node.ops:
            if not isinstance(op, _ALLOWED_CMPOPS):
                raise _ForbiddenNode("Nicht erlaubter Vergleichsoperator.", line)
        _check_node(node.left, allowed)
        for comparator in node.comparators:
            _check_node(comparator, allowed)
        return

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTION_WHITELIST:
            name = node.func.id if isinstance(node.func, ast.Name) else "…"
            raise _ForbiddenNode(f"Funktion '{name}' ist nicht erlaubt.", line)
        if node.keywords:
            raise _ForbiddenNode("Schlüsselwort-Argumente sind nicht erlaubt.", line)
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                raise _ForbiddenNode("'*args' ist nicht erlaubt.", line)
            _check_node(arg, allowed)
        return

    if isinstance(node, ast.Name):
        if node.id.startswith("__"):
            raise _ForbiddenNode(f"Name '{node.id}' ist nicht erlaubt.", line)
        if isinstance(node.ctx, ast.Load) and node.id not in allowed:
            raise _ForbiddenNode(f"Unbekannter Name '{node.id}'.", line)
        return

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return
        raise _ForbiddenNode("Nur Zahlen und Wahrheitswerte sind als Literal erlaubt.", line)

    raise _ForbiddenNode(f"'{type(node).__name__}' ist nicht erlaubt.", line)


def _assigned_names(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            yield node.targets[0].id


def validate_formula_source(source: str, variable_names: Iterable[str],
                            output_name: str) -> Optional[str]:
    """Rein statische Prüfung, führt nichts aus. `None` heißt: der Code ist gültig.

    `variable_names` muss für jede Formel-Zeile sowohl `<n>` als auch `<n>_valid`
    enthalten (siehe Modul-Docstring).
    """
    if not source.strip():
        return None  # Leerer Code ist gültig – bedeutet „keine Formel".
    if len(source) > MAX_SOURCE_LENGTH:
        return f"Code ist länger als {MAX_SOURCE_LENGTH} Zeichen."

    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        return f"Syntaxfehler in Zeile {exc.lineno}: {exc.msg}"

    node_count = sum(1 for _ in ast.walk(tree))
    if node_count > MAX_NODES:
        return f"Code hat mehr als {MAX_NODES} Ausdrucksbausteine."

    # Namen, die der Code selbst irgendwo zuweist (Zwischenvariablen wie `x` in
    # `x = pv * 2`), dürfen anschließend auch gelesen werden – nicht nur die
    # eingangs deklarierten Zeilen-Variablen. `_assigned_names` läuft hier bewusst
    # VOR `_check_node`: sie erkennt ausschließlich die bereits selbst erlaubte
    # Form „ein Name als einziges Zuweisungsziel" (dieselbe Form, die
    # `_check_node` unten ohnehin durchsetzt), erweitert die Whitelist also nie
    # um eine Zuweisungsform, die nicht auch unabhängig davon zulässig wäre.
    assigned = set(_assigned_names(tree))
    allowed = frozenset(variable_names) | {output_name} | assigned
    try:
        _check_node(tree, allowed)
    except _ForbiddenNode as exc:
        prefix = f"Zeile {exc.line}: " if exc.line else ""
        return f"{prefix}{exc.message}"

    if output_name not in assigned:
        return f"Der Code muss der Variable '{output_name}' einen Wert zuweisen."

    return None


def _compare(op: ast.cmpop, left: float, right: float) -> bool:
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Gt):
        return left > right
    return left >= right  # ast.GtE – alles andere ist durch _check_node bereits ausgeschlossen.


def _eval(node: ast.AST, env: Dict[str, object]) -> float:
    """Wertet einen bereits geprüften Ausdrucksknoten aus.

    Boolesche Verknüpfungen, Vergleiche und if/else werten so wenig aus, wie
    zum Ergebnis nötig ist (echtes Kurzschluss-Verhalten wie in Python) – so
    kann eine Formel mit `pv_valid and pv > 0` einen ungültigen Wert gefahrlos
    ausschließen, statt beim Dereferenzieren von `pv` selbst zu scheitern.
    """
    if isinstance(node, ast.Constant):
        return float(node.value)

    if isinstance(node, ast.Name):
        value = env.get(node.id)
        if value is None:
            raise _EvalError(f"'{node.id}' hat keinen gültigen Wert.")
        return float(value)

    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, env)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        return 0.0 if operand else 1.0  # ast.Not

    if isinstance(node, ast.BinOp):
        left = _eval(node.left, env)
        right = _eval(node.right, env)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        # ast.Pow: negative Basis mit nicht-ganzzahligem Exponenten erzeugt in
        # Python stillschweigend eine komplexe Zahl (`(-1.0) ** 0.5`) – hier
        # explizit ausgeschlossen statt das später als Absturz zu entdecken.
        if left < 0 and not float(right).is_integer():
            raise _EvalError(
                "Potenz mit negativer Basis und nicht-ganzzahligem Exponenten ist nicht definiert.")
        result = left ** right
        if isinstance(result, complex):
            raise _EvalError("Ergebnis der Potenz ist keine reelle Zahl.")
        return result

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = 1.0
            for value_node in node.values:
                result = _eval(value_node, env)
                if not result:
                    return result
            return result
        result = 0.0  # ast.Or
        for value_node in node.values:
            result = _eval(value_node, env)
            if result:
                return result
        return result

    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, env)
            if not _compare(op, left, right):
                return 0.0
            left = right
        return 1.0

    if isinstance(node, ast.IfExp):
        return _eval(node.body, env) if _eval(node.test, env) else _eval(node.orelse, env)

    if isinstance(node, ast.Call):
        func = FUNCTION_WHITELIST[node.func.id]  # durch _check_node bereits geprüft
        args = [_eval(arg, env) for arg in node.args]
        return float(func(*args))

    raise _EvalError(f"'{type(node).__name__}' kann nicht ausgewertet werden.")


def _exec_stmts(stmts, env: Dict[str, object]) -> None:
    for stmt in stmts:
        if isinstance(stmt, ast.Assign):
            env[stmt.targets[0].id] = _eval(stmt.value, env)
        else:  # ast.If – durch _check_node bereits auf diese zwei Typen begrenzt
            if _eval(stmt.test, env):
                _exec_stmts(stmt.body, env)
            else:
                _exec_stmts(stmt.orelse, env)


def run_formula(source: str, namespace: Dict[str, object], output_name: str) -> FormulaResult:
    """Validiert und führt den Code gegen `namespace` aus.

    Wirft nie selbst – jeder Fehler kommt als `FormulaResult(valid=False, …)`
    zurück, damit ein Regelzyklus nie an einer kaputten Formel abbricht (siehe
    Modul-Docstring).
    """
    if not source.strip():
        return _fail("Kein Code hinterlegt.")

    error = validate_formula_source(source, namespace.keys(), output_name)
    if error is not None:
        return _fail(error)

    tree = ast.parse(source, mode="exec")
    env: Dict[str, object] = dict(namespace)

    try:
        _exec_stmts(tree.body, env)
    except _EvalError as exc:
        return _fail(str(exc))
    except ZeroDivisionError:
        return _fail("Division durch 0.")
    except OverflowError:
        return _fail("Zwischenergebnis zu groß.")
    except RecursionError:
        return _fail("Ausdruck zu tief verschachtelt.")

    result = env.get(output_name)
    if result is None:
        return _fail(f"'{output_name}' wurde nicht gesetzt.")

    value = float(result)
    if not math.isfinite(value):
        return _fail(f"'{output_name}' ist keine endliche Zahl (NaN/Unendlich).")

    return FormulaResult(value=value, valid=True, error=None, error_line=None)
