"""StateProxy, Resolve-Vertrag und gemeinsam genutzte Hilfsfunktionen.

Der Resolve-Vertrag ist die einzige Stelle, an der entschieden wird, wie ein
fehlender, nicht verfügbarer oder unbrauchbarer HA-State ersetzt wird. Keine
Geräteklasse baut sich dafür eine eigene Kette – sonst laufen die Ersatzwerte
auseinander und niemand kann später sagen, welcher Wert gerade wirkt.
"""

import datetime
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

# Zustand eines gelesenen States. `missing` und `unavailable` verwenden denselben
# Ersatzwert, sind aber verschiedene Ursachen: das eine ist ein Konfigurations-
# fehler, das andere ein Ausfall zur Laufzeit.
STATE_VALID       = "valid"
STATE_MISSING     = "missing"
STATE_UNAVAILABLE = "unavailable"
STATE_INVALID     = "invalid"

# Woher der wirksame Wert stammt.
SOURCE_HA       = "ha"
SOURCE_ADDON    = "addon"
SOURCE_INTERNAL = "internal"

# HA meldet einen ausgefallenen Sensor über den State, nicht über das Fehlen der
# Entität. `None` kommt bei einem Helfer ohne gesetzten Wert vor.
_UNAVAILABLE_STATES = ("unavailable", "unknown", "none", "")

_TRUE_STATES = ("on", "true", "1", "yes")
_FALSE_STATES = ("off", "false", "0", "no")


@dataclass(frozen=True)
class Resolved:
    """Ergebnis einer Auflösung: Wert, Ursache und Quelle.

    `value` ist immer der wirksame Wert – auch dann, wenn er nicht aus Home
    Assistant stammt. `state` sagt, warum, `source` sagt, woher.
    """

    value: Any
    state: str
    source: str

    @property
    def from_ha(self) -> bool:
        return self.source == SOURCE_HA


class StateProxy:
    """Kapselt einen HA-State-Snapshot; bildet pyscripts state.get() / state.getattr() nach."""

    def __init__(self, states: Dict[str, Dict]):
        self._states = states

    # ------------------------------------------------------------------
    # Roher Zugriff
    # ------------------------------------------------------------------

    def get(self, entity_id: str, default: Any = None) -> Any:
        if entity_id.endswith(".last_changed"):
            base = entity_id[: -len(".last_changed")]
            return (self._states.get(base) or {}).get("last_changed", default)
        entry = self._states.get(entity_id)
        if entry is None:
            return default
        return entry.get("state", default)

    def getattr(self, entity_id: str) -> Optional[Dict]:
        entry = self._states.get(entity_id)
        return entry.get("attributes") if entry else None

    def has(self, entity_id: str) -> bool:
        """Ist die Entität im Schnappschuss vorhanden?

        `get()` allein kann das nicht beantworten: eine fehlende Entität und eine
        vorhandene mit State `null` liefern beide `None`.
        """
        return entity_id in self._states

    def availability(self, entity_id: str) -> str:
        """`missing`, `unavailable` oder `valid` – ohne den Wert zu prüfen."""
        if not self.has(entity_id):
            return STATE_MISSING
        raw = self.get(entity_id)
        if raw is None or str(raw).strip().lower() in _UNAVAILABLE_STATES:
            return STATE_UNAVAILABLE
        return STATE_VALID

    # ------------------------------------------------------------------
    # Resolve-Vertrag
    # ------------------------------------------------------------------

    def resolve_number(self, entity_id: str, *,
                       addon: Optional[float] = None,
                       internal: Optional[float] = None,
                       minimum: Optional[float] = None,
                       maximum: Optional[float] = None) -> Resolved:
        """Zahl aus HA, sonst Add-on-Feld, sonst interner Default.

        Ein gültiger Wert `0` ist ein Wert und wird nie ersetzt – deshalb steht
        hier nirgends `wert or fallback`. Nicht endliche Werte (NaN, ±inf) und
        Werte außerhalb eines zwingenden Bereichs gelten als `invalid`.
        """
        availability = self.availability(entity_id)
        if availability != STATE_VALID:
            return self._number_fallback(availability, addon, internal)

        try:
            value = float(self.get(entity_id))
        except (TypeError, ValueError):
            return self._number_fallback(STATE_INVALID, addon, internal)
        if not math.isfinite(value):
            return self._number_fallback(STATE_INVALID, addon, internal)
        if minimum is not None and value < minimum:
            return self._number_fallback(STATE_INVALID, addon, internal)
        if maximum is not None and value > maximum:
            return self._number_fallback(STATE_INVALID, addon, internal)
        return Resolved(value, STATE_VALID, SOURCE_HA)

    def resolve_bool(self, entity_id: str, *,
                     fallback: bool = False,
                     missing_fallback: Optional[bool] = None) -> Resolved:
        """Schalter aus HA, sonst Ersatzwert.

        `missing_fallback` trennt „Entität gar nicht angelegt" von „Entität
        ausgefallen". Der Speicher braucht genau das: eine fehlende
        `laden_erlaubt` heißt erlaubt, eine ausgefallene heißt gesperrt.
        """
        if missing_fallback is None:
            missing_fallback = fallback
        availability = self.availability(entity_id)
        if availability == STATE_MISSING:
            return Resolved(missing_fallback, STATE_MISSING, SOURCE_INTERNAL)
        if availability == STATE_UNAVAILABLE:
            return Resolved(fallback, STATE_UNAVAILABLE, SOURCE_INTERNAL)

        raw = str(self.get(entity_id)).strip().lower()
        if raw in _TRUE_STATES:
            return Resolved(True, STATE_VALID, SOURCE_HA)
        if raw in _FALSE_STATES:
            return Resolved(False, STATE_VALID, SOURCE_HA)
        return Resolved(fallback, STATE_INVALID, SOURCE_INTERNAL)

    def resolve_select(self, entity_id: str, options: Iterable[str], *,
                       fallback: str,
                       addon: Optional[str] = None) -> Resolved:
        """Auswahlwert aus HA, sonst Add-on-Feld, sonst interner Default."""
        allowed = tuple(options)
        availability = self.availability(entity_id)
        if availability != STATE_VALID:
            return self._select_fallback(availability, addon, fallback)
        raw = str(self.get(entity_id)).strip()
        if raw not in allowed:
            return self._select_fallback(STATE_INVALID, addon, fallback)
        return Resolved(raw, STATE_VALID, SOURCE_HA)

    # ------------------------------------------------------------------
    # Interne Fallback-Auswahl
    # ------------------------------------------------------------------

    @staticmethod
    def _number_fallback(state: str, addon: Optional[float],
                         internal: Optional[float]) -> Resolved:
        if addon is not None:
            return Resolved(float(addon), state, SOURCE_ADDON)
        if internal is not None:
            return Resolved(float(internal), state, SOURCE_INTERNAL)
        return Resolved(None, state, SOURCE_INTERNAL)

    @staticmethod
    def _select_fallback(state: str, addon: Optional[str], internal: str) -> Resolved:
        if addon is not None:
            return Resolved(addon, state, SOURCE_ADDON)
        return Resolved(internal, state, SOURCE_INTERNAL)


def safe_float(val: Any, default: float = 0.0) -> float:
    """Wandelt einen Wert robust in float um; bei Fehlern wird der Default geliefert.

    Bewusst ohne Endlichkeitsprüfung: für die diagnostizierbare Auflösung ist
    `StateProxy.resolve_number()` zuständig. Diese Funktion bleibt der kurze Weg
    für Werte, die nicht aus einer HA-Entität stammen.
    """
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def parse_ts(last_changed: Any) -> float:
    """Wandelt einen ISO-Zeitstempel (oder numerischen Wert) in einen Unix-Float um."""
    if last_changed is None:
        return 0.0
    try:
        if isinstance(last_changed, (int, float)):
            return float(last_changed)
        dt = datetime.datetime.fromisoformat(str(last_changed).replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0
