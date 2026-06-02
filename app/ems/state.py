"""StateProxy and shared helper utilities."""

import datetime
from typing import Any, Dict, Optional


class StateProxy:
    """Wraps a HA states dict snapshot; mimics pyscript's state.get() / state.getattr()."""

    def __init__(self, states: Dict[str, Dict]):
        self._states = states

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


def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def parse_ts(last_changed: Any) -> float:
    """Parse an ISO timestamp string (or numeric) to a Unix float."""
    if last_changed is None:
        return 0.0
    try:
        if isinstance(last_changed, (int, float)):
            return float(last_changed)
        dt = datetime.datetime.fromisoformat(str(last_changed).replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0
