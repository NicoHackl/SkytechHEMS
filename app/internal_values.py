"""HEMS-interne Ersatzwerte für HA-Helfer (D-061).

Fehlt ein Helfer der Namenskonvention, ist er ausgefallen oder ungültig, kann
sein Wert im Steuerung-Tab direkt im HEMS eingegeben werden. Der HA-Helfer hat
immer Vorrang; der interne Wert greift erst danach und vor Add-on-Feld und
internem Default (Reihenfolge siehe ems/state.py).

Gespeichert wird in einer kleinen JSON-Datei unter /data – nach dem Merker der
Notabschaltung (D-059) die zweite eigene Persistenz des Add-ons. Schlüssel ist
die entity_id; das Präfix ist unveränderlich, ein Rename ist eine Neuanlage.

Freigaben und Zwang nimmt der Speicher nie an (`is_gate_entity`): sie gibt es
ausschließlich als echten HA-Helfer.
"""

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, Optional

from ems.state import is_gate_entity
from json_file import write_json_atomic

log = logging.getLogger(__name__)

INTERNAL_VALUES_FILENAME = "interne_werte.json"

_ON_VALUES = (True, "on", "true", 1, "1")
_OFF_VALUES = (False, "off", "false", 0, "0")


class InternalValueError(Exception):
    """Ein Wert wird abgelehnt. Die Meldung ist deutsch und für die Oberfläche gedacht."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_value(item: Dict[str, Any], raw: Any) -> Any:
    """Prüft einen Eingabewert gegen den Steuerschema-Eintrag und liefert ihn typgerecht.

    Ohne HA-Helfer fehlen dessen Attribute min/max/options – die Grenzen stehen
    deshalb im Steuerschema selbst (`min`, `max`, `step`, `integer`, `options`).
    """
    if not item.get("internal_editable"):
        raise InternalValueError(
            f"{item.get('label', item.get('entity'))} ist nur über den HA-Helfer einstellbar.")
    kind = item.get("kind")
    if kind == "bool":
        if raw in _ON_VALUES:
            return True
        if raw in _OFF_VALUES:
            return False
        raise InternalValueError("Erwartet wird An oder Aus.")
    if kind == "select":
        value = str(raw)
        if value not in (item.get("options") or []):
            raise InternalValueError(
                f"Ungültige Auswahl „{value}“. Erlaubt: {', '.join(item.get('options') or [])}.")
        return value
    if kind == "number":
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise InternalValueError("Erwartet wird eine Zahl.") from None
        if not math.isfinite(value):
            raise InternalValueError("Erwartet wird eine endliche Zahl.")
        minimum, maximum = item.get("min"), item.get("max")
        if minimum is not None and value < minimum:
            raise InternalValueError(f"Der Wert darf nicht kleiner als {minimum:g} sein.")
        if maximum is not None and value > maximum:
            raise InternalValueError(f"Der Wert darf nicht größer als {maximum:g} sein.")
        if item.get("integer") and not value.is_integer():
            raise InternalValueError("Erwartet wird eine ganze Zahl.")
        return value
    raise InternalValueError("Dieser Helfertyp ist intern nicht einstellbar.")


class InternalValueStore:
    """Die Datei der internen Ersatzwerte.

    Fehlend = leer. Unlesbar = leer und `file_error` gesetzt; Schreiben ist dann
    gesperrt, damit die beschädigte Datei nicht stillschweigend überschrieben
    wird. Anders als beim Notabschaltungs-Merker gibt es kein „im Zweifel aktiv“:
    ohne internen Wert greift die bisherige Kette aus Add-on-Feld und Default.
    """

    def __init__(self, path: Path):
        self.path = path
        self._values: Dict[str, Any] = {}
        self.file_error = ""

    def load(self) -> None:
        self._values, self.file_error = {}, ""
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            values = data.get("values") if isinstance(data, dict) else None
            if not isinstance(values, dict):
                raise ValueError("Feld 'values' fehlt oder ist kein Objekt")
        except Exception as exc:
            self.file_error = (f"Datei {self.path} ist unlesbar ({exc}) – interne Werte wirken nicht. "
                               "Datei reparieren oder löschen.")
            log.error("Interne Werte: %s", self.file_error)
            return
        for entity_id, value in values.items():
            if is_gate_entity(str(entity_id)):
                log.warning("Interne Werte: %s ist nur als HA-Helfer zulässig – ignoriert.", entity_id)
            elif isinstance(value, (bool, str)) or _is_number(value):
                self._values[str(entity_id)] = value
            else:
                log.warning("Interne Werte: ungültiger Wert für %s – ignoriert.", entity_id)

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._values)

    def get(self, entity_id: str) -> Optional[Any]:
        return self._values.get(entity_id)

    def set(self, entity_id: str, value: Any) -> None:
        """Erwartet einen bereits per `validate_value` geprüften Wert."""
        if is_gate_entity(entity_id):
            raise InternalValueError("Freigaben und Zwang sind nur über den HA-Helfer einstellbar.")
        self._write({**self._values, entity_id: value})

    def reset(self, entity_id: str) -> None:
        if entity_id not in self._values:
            return
        rest = dict(self._values)
        del rest[entity_id]
        self._write(rest)

    def _write(self, values: Dict[str, Any]) -> None:
        if self.file_error:
            raise InternalValueError(self.file_error)
        try:
            write_json_atomic(self.path, {"values": values})
        except OSError as exc:
            raise InternalValueError(f"Interne Werte konnten nicht gespeichert werden: {exc}") from exc
        self._values = values
