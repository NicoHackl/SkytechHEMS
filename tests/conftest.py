"""Gemeinsame Test-Hilfen."""

from typing import Optional

from ems.state import StateProxy

# Attribute, die ein korrekt angelegter HA-Helfer mitbringt. Ohne sie hielte die
# Schreibziel-Prüfung jeden Speicher für kaputt: der signierte Sollwert braucht
# ein negatives Minimum, die Betriebsart genau drei Optionen. Ein Test, der ein
# defektes Ziel prüfen will, überschreibt sie gezielt über `attributes`.
_DEFAULT_ATTRIBUTES = {
    "_anforderung_leistung_w": {"min": -20000.0, "max": 20000.0, "step": 1},
    "_anforderung_leistung_a": {"min": 0.0, "max": 64.0, "step": 1},
    "_anforderung_betriebsart": {"options": ["laden", "entladen", "standby"]},
    "_modus": {"options": ["auto", "manuell", "aus"]},
    "_betriebsart": {"options": ["auto", "nur_laden", "nur_entladen", "standby"]},
}


def _default_attributes(entity_id: str) -> dict:
    for suffix, attributes in _DEFAULT_ATTRIBUTES.items():
        if entity_id.endswith(suffix):
            return dict(attributes)
    return {}


def make_states(
    mapping: dict,
    last_changed: Optional[str] = None,
    attributes: Optional[dict[str, dict]] = None,
) -> StateProxy:
    """Baut einen StateProxy aus {entity_id: state}.

    `last_changed` (ISO-String) gilt für alle Einträge; None bedeutet Epoch 0,
    sodass Altersberechnungen (anforderung_age_s, switch_age_s) sehr groß werden
    und Zeitschwellen damit als erfüllt gelten.
    """
    states = {}
    for eid, val in mapping.items():
        states[eid] = {
            "state": None if val is None else str(val),
            "attributes": (attributes or {}).get(eid, _default_attributes(eid)),
            "last_changed": last_changed,
        }
    return StateProxy(states)
