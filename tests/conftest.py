"""Gemeinsame Test-Hilfen."""

from typing import Optional

from ems.state import StateProxy


def make_states(mapping: dict, last_changed: Optional[str] = None) -> StateProxy:
    """Baut einen StateProxy aus {entity_id: state}.

    `last_changed` (ISO-String) gilt für alle Einträge; None bedeutet Epoch 0,
    sodass Altersberechnungen (anforderung_age_s, switch_age_s) sehr groß werden
    und Zeitschwellen damit als erfüllt gelten.
    """
    states = {}
    for eid, val in mapping.items():
        states[eid] = {
            "state": None if val is None else str(val),
            "attributes": {},
            "last_changed": last_changed,
        }
    return StateProxy(states)
