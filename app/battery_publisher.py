"""Veroeffentlichung des wirksamen Ladelimits je AC-Speicher (D-057).

Das Add-on schreibt nach jedem Regelzyklus fuer jeden Speicher (``class: battery``)
einen Anzeige-Sensor ``sensor.ems_<prefix>_lade_limit_w`` in die
HA-Zustandsmaschine. Sein State ist genau das Ladelimit, mit dem die Regelung im
selben Zyklus gerechnet hat: WR-Grenze, gegebenenfalls gesenkt durch eine
greifende Ladestufe (D-056), und 0 W, wenn Laden gesperrt, der SoC-Deckel
erreicht oder der SoC ungueltig ist.

Grenzen, die dieses Modul einhaelt — dieselben wie beim Flow-Publisher (D-046):

* Es schaltet nichts. Der Sensor ist reine Anzeige und hat keinen Regelpfad.
* Es wirft nie. Ein misslungener Anzeigeschrieb darf keinen Zyklus kosten.
* Es rechnet nichts selbst. Quelle ist ausschliesslich der Status des Zyklus,
  damit Sensor und interne Rechnung nicht auseinanderlaufen koennen.
"""

import logging
from typing import Any, Dict, List, Tuple

log = logging.getLogger(__name__)


def battery_limit_entity_id(prefix: str) -> str:
    return f"sensor.ems_{prefix}_lade_limit_w"


def build_battery_limit_states(status: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Je Speicher im Status ein Tripel (entity_id, state, attributes).

    Die Attribute tragen bewusst keinen Zeitstempel: bei unveraendertem Limit
    bleiben State und Attribute gleich, und Home Assistant zeichnet keine neue
    Zustandsaenderung auf.
    """
    result: List[Tuple[str, str, Dict[str, Any]]] = []
    for device in (status or {}).get("devices") or []:
        if device.get("type") != "battery":
            continue
        prefix = device.get("entity_prefix") or device.get("id")
        if not prefix:
            continue
        label = device.get("label") or prefix
        attributes: Dict[str, Any] = {
            "friendly_name":          f"EMS {label} Ladelimit",
            "icon":                   "mdi:battery-arrow-up",
            "unit_of_measurement":    "W",
            "device_class":           "power",
            "state_class":            "measurement",
            "ladestufe_aktiv":        device.get("ladestufe_aktiv"),
            "ladestufe_max_w":        device.get("ladestufe_max_w"),
            "wr_max_ladeleistung_w":  device.get("max_ladeleistung_w"),
            "blockiert_grund":        device.get("lade_blockiert_grund"),
            "soc_prozent":            device.get("soc_prozent"),
        }
        state = f"{round(float(device.get('lade_limit_w') or 0.0))}"
        result.append((battery_limit_entity_id(prefix), state, attributes))
    return result


async def publish_battery_limits(ha_client, status: Dict[str, Any]) -> None:
    """Schreibt die Ladelimit-Sensoren aller Speicher. Wirft nie."""
    try:
        for entity_id, state, attributes in build_battery_limit_states(status):
            await ha_client.set_state(entity_id, state, attributes)
    except Exception as exc:
        log.warning("Ladelimit der Speicher konnte nicht veröffentlicht werden: %s", exc)
