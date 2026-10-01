"""Regeln der Notabschaltung (D-059) ohne Laufzeitabhängigkeiten.

Getrennt von `emergency.py`, weil `configuration.py` diese Regeln zum Validieren
braucht und `emergency.py` über `ems` wiederum `configuration` importiert. Eine
Quelle für Validierung, Ausführung und Oberfläche.
"""

import math
from typing import Any, Dict, Optional, Tuple

# Gespeichert wird die Python-Schreibweise, angezeigt die mathematische.
OPERATORS: Tuple[str, ...] = ("==", "!=", ">", ">=", "<", "<=")
NUMERIC_OPERATORS: Tuple[str, ...] = (">", ">=", "<", "<=")
OPERATOR_LABELS: Dict[str, str] = {
    "==": "=", "!=": "≠", ">": ">", ">=": "≥", "<": "<", "<=": "≤",
}

# Welche Art Wert eine Zielzeile je Domain trägt. Einzige Quelle für
# Validierung, Ausführung und Oberfläche (über `supported` in GET /api/config).
TARGET_ON_OFF = "on_off"
TARGET_OPTION = "option"
TARGET_NUMBER = "number"
TARGET_PRESS = "press"
TARGET_RUN = "run"
TARGET_KINDS: Dict[str, str] = {
    "switch": TARGET_ON_OFF,
    "input_boolean": TARGET_ON_OFF,
    "light": TARGET_ON_OFF,
    "fan": TARGET_ON_OFF,
    "select": TARGET_OPTION,
    "input_select": TARGET_OPTION,
    "number": TARGET_NUMBER,
    "input_number": TARGET_NUMBER,
    "button": TARGET_PRESS,
    "input_button": TARGET_PRESS,
    "script": TARGET_RUN,
}
ON_OFF_VALUES: Tuple[str, ...] = ("on", "off")

# Zustände, bei denen die Bedingung nicht auswertbar ist. Sie lösen bewusst
# nicht aus: sonst stünde nach jedem HA-Neustart eine Notabschaltung an.
UNUSABLE_STATES = ("unavailable", "unknown", "none", "")


def as_number(text: Any) -> Optional[float]:
    """Endliche Zahl oder None. Ein Dezimalkomma wird akzeptiert."""
    if isinstance(text, bool) or text is None:
        return None
    try:
        number = float(str(text).strip().replace(",", "."))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def condition_error(entity: str, operator: str, value: str) -> Dict[str, str]:
    """Feldfehler einer Bedingung, Schlüssel ohne Präfix. Leer = gültig.

    Ohne Entität ist die Notabschaltung aus; Operator und Wert werden dann
    nicht geprüft, damit ein halb ausgefülltes Formular speicherbar bleibt.
    """
    errors: Dict[str, str] = {}
    if not entity:
        return errors
    if operator not in OPERATORS:
        errors["operator"] = "Zulässig sind =, ≠, >, ≥, < oder ≤."
    if not value.strip():
        errors["value"] = "Sollwert ist ein Pflichtfeld."
    elif operator in NUMERIC_OPERATORS and as_number(value) is None:
        errors["value"] = f"Für „{OPERATOR_LABELS[operator]}“ ist eine Zahl nötig."
    return errors


def target_error(entity: str, value: str) -> Dict[str, str]:
    """Feldfehler einer Zielzeile, Schlüssel ohne Präfix. Leer = gültig."""
    errors: Dict[str, str] = {}
    if not entity:
        errors["entity"] = "Entität ist ein Pflichtfeld."
        return errors
    domain = entity.split(".", 1)[0]
    kind = TARGET_KINDS.get(domain)
    if kind is None:
        errors["entity"] = (
            f"Domain „{domain}“ wird nicht unterstützt. Zulässig: "
            f"{', '.join(sorted(TARGET_KINDS))}."
        )
        return errors
    if kind == TARGET_ON_OFF and value not in ON_OFF_VALUES:
        errors["value"] = "An oder Aus wählen."
    elif kind == TARGET_OPTION and not value.strip():
        errors["value"] = "Option ist ein Pflichtfeld."
    elif kind == TARGET_NUMBER and as_number(value) is None:
        errors["value"] = "Zahl erwartet."
    return errors
