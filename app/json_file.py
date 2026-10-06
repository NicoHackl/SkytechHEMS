"""Atomares Schreiben kleiner JSON-Dateien unter /data.

Gemeinsam genutzt vom Merker der Notabschaltung (D-059) und den HEMS-internen
Ersatzwerten (D-061): erst eine temporäre Datei vollständig schreiben, dann
umbenennen – ein Absturz mitten im Schreiben hinterlässt nie eine halbe Datei.
"""

import json
import os
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, payload: Any) -> None:
    """Schreibt atomar. Wirft OSError, wenn das Dateisystem nicht mitspielt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
