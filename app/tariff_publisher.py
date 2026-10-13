"""Anzeige-Sensoren des dynamischen Strompreises (D-065, Phase P3).

`sensor.ems_dyn_preis` und `sensor.ems_dyn_pv_prognose` entstehen aus dem
Statusobjekt des Preis- und Prognosemoduls. Grenzen wie bei den übrigen
Publishern (D-046, D-057, D-062):

* Es schaltet nichts. Die Sensoren sind reine Anzeige und haben keinen Regelpfad.
* Es wirft nie. Ein misslungener Schreibvorgang kostet höchstens die Anzeige.
* Geschrieben wird nur bei geändertem Inhalt oder wenn die Entität im
  Schnappschuss fehlt (nach einem HA-Neustart sind per `POST /api/states`
  erzeugte Entitäten weg). Die Attribute tragen deshalb nichts, was sich jede
  Minute ändert – sonst zeichnete der Recorder jede Minute einen neuen Zustand auf.
* Die Kurven gehen nicht in Attribute; sie gehören in Data Insight.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

PRICE_ENTITY_ID = "sensor.ems_dyn_preis"
PV_ENTITY_ID = "sensor.ems_dyn_pv_prognose"
UNAVAILABLE = "unavailable"


def _slot(slot: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not slot:
        return None
    return {"von": slot["von_iso"], "bis": slot["bis_iso"], "preis": slot["preis"]}


def build_states(status: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Tripel (entity_id, state, attributes); leer, wenn das Modul aus ist."""
    if not status.get("aktiv"):
        return []
    result: List[Tuple[str, str, Dict[str, Any]]] = []

    price = status.get("preis") or {}
    valid = bool(price.get("gueltig"))
    result.append((PRICE_ENTITY_ID, f"{price['aktuell']['preis']}" if valid else UNAVAILABLE, {
        "friendly_name":       "EMS Dynamischer Strompreis",
        "icon":                "mdi:currency-eur",
        "unit_of_measurement": "€/kWh",
        "state_class":         "measurement",
        "gueltig":             valid,
        "grund":               price.get("grund"),
        "quelle":              price.get("entity"),
        "raster_min":          price.get("raster_min"),
        "horizont_bis":        price.get("horizont_bis_iso"),
        "morgen_vorhanden":    price.get("morgen_vorhanden"),
        "guenstigster_slot":   _slot(price.get("guenstigster")),
        "teuerster_slot":      _slot(price.get("teuerster")),
    }))

    pv = status.get("pv") or {}
    rest = pv.get("rest_heute") or {}
    curve = pv.get("kurve") or {}
    result.append((PV_ENTITY_ID, f"{rest['wert_kwh']}" if rest.get("gueltig") else UNAVAILABLE, {
        "friendly_name":       "EMS PV-Prognose Rest heute",
        "icon":                "mdi:solar-power-variant",
        "unit_of_measurement": "kWh",
        "device_class":        "energy",
        "gueltig":             bool(rest.get("gueltig")),
        "grund":               rest.get("grund"),
        "heute_kwh":           (pv.get("heute") or {}).get("wert_kwh"),
        "morgen_kwh":          (pv.get("morgen") or {}).get("wert_kwh"),
        "kurve_gueltig":       bool(curve.get("gueltig")),
        "kurve_bis":           curve.get("bis_iso"),
    }))
    return result


class TariffPublisher:
    """Merkt sich den zuletzt geschriebenen Inhalt je Sensor."""

    def __init__(self) -> None:
        self._last: Dict[str, Tuple[str, Dict[str, Any]]] = {}

    async def publish(self, ha_client, status: Dict[str, Any], states: Dict[str, Any]) -> int:
        """Schreibt geänderte oder fehlende Sensoren. Liefert die Anzahl Schreibvorgänge. Wirft nie."""
        written = 0
        try:
            for entity_id, state, attributes in build_states(status):
                content = (state, attributes)
                if self._last.get(entity_id) == content and entity_id in states:
                    continue
                if await ha_client.set_state(entity_id, state, attributes):
                    self._last[entity_id] = content
                    written += 1
        except Exception as exc:
            log.warning("Anzeige-Sensoren des dynamischen Strompreises nicht veröffentlicht: %s", exc)
        return written
