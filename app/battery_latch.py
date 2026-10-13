"""Sperre am Ladedeckel der Speicher über einen Neustart hinweg (D-066).

Ein Speicher, der soc_max erreicht hat, bleibt für das Laden gesperrt, bis der
SoC soc_max_hysteresis_percent darunter fällt. Diese Sperre lag bisher nur im
Speicher des Add-ons: Ein Neustart im Hysterese-Band (z. B. 99 % bei soc_max
100 % und 3 % Wiedereinstieg) gab das Laden wieder frei, obwohl es noch
gesperrt sein sollte.

Gespeichert wird in einer kleinen JSON-Datei unter /data – neben dem Merker der
Notabschaltung (D-059) und den internen Ersatzwerten (D-061) die dritte eigene
Persistenz des Add-ons. Schlüssel ist die Geräte-ID.

Anders als die beiden anderen Dateien ist diese nur ein Zwischenstand: Fehlt
sie oder ist sie unlesbar, startet das HEMS wie bisher ohne Sperre, und eine
beschädigte Datei wird beim nächsten Wechsel überschrieben. Ein Schreibfehler
hält die Regelung nicht an.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from json_file import write_json_atomic

log = logging.getLogger(__name__)

BATTERY_LATCH_FILENAME = "speicher_sperre.json"


class BatteryLatchStore:
    """Die Datei der Speicher-Sperren. Fehlend oder kaputt = keine Sperre."""

    def __init__(self, path: Path):
        self.path = path
        # Zuletzt gelesener oder geschriebener Stand. None = unbekannt, der
        # erste Aufruf von save() schreibt dann in jedem Fall.
        self._saved: Optional[Dict[str, bool]] = None

    def load(self) -> Dict[str, bool]:
        if not self.path.exists():
            self._saved = {}
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            latches = data.get("latches") if isinstance(data, dict) else None
            if not isinstance(latches, dict):
                raise ValueError("Feld 'latches' fehlt oder ist kein Objekt")
        except Exception as exc:
            log.error("Speicher-Sperre: Datei %s ist unlesbar (%s) – Start ohne Sperre, "
                      "sie wird beim nächsten Wechsel neu geschrieben.", self.path, exc)
            return {}
        result: Dict[str, bool] = {}
        for device_id, value in latches.items():
            if isinstance(value, bool):
                result[str(device_id)] = value
            else:
                log.warning("Speicher-Sperre: ungültiger Wert für %s – ignoriert.", device_id)
        self._saved = dict(result)
        return result

    def save(self, latches: Dict[str, bool]) -> None:
        """Schreibt nur bei einer Änderung. Ein Fehler wird geloggt, nicht geworfen."""
        if latches == self._saved:
            return
        try:
            write_json_atomic(self.path, {"latches": latches})
        except OSError as exc:
            log.warning("Speicher-Sperre konnte nicht gespeichert werden: %s", exc)
            return
        self._saved = dict(latches)
