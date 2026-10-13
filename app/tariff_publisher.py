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
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

PRICE_ENTITY_ID = "sensor.ems_dyn_preis"
PV_ENTITY_ID = "sensor.ems_dyn_pv_prognose"
LOAD_ENTITY_ID = "sensor.ems_dyn_verbrauch_prognose"
REACH_ENTITY_ID = "sensor.ems_dyn_speicher_reichweite"
WINDOW_ENTITY_ID = "sensor.ems_dyn_preisfenster"
GRID_ENTITY_ID = "sensor.ems_dyn_netzladen"
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

    # Phase P5 – nur vorhanden, wenn die Auswertung gelaufen ist.
    if "verbrauch" not in status:
        return result
    load = status.get("verbrauch") or {}
    result.append((LOAD_ENTITY_ID, f"{load['bis_ende_morgen_kwh']}" if load.get("gueltig") else UNAVAILABLE, {
        "friendly_name":       "EMS Verbrauchsprognose bis Ende morgen",
        "icon":                "mdi:home-lightning-bolt-outline",
        "unit_of_measurement": "kWh",
        "device_class":        "energy",
        "gueltig":             bool(load.get("gueltig")),
        "grund":               load.get("grund"),
        "methode":             load.get("methode"),
        "historie_tage":       load.get("historie_tage"),
        "naechste_24h_kwh":    load.get("naechste_24h_kwh"),
        "p10_kwh":             load.get("naechste_24h_p10_kwh"),
        "p90_kwh":             load.get("naechste_24h_p90_kwh"),
    }))

    storage = status.get("speicher") or {}
    median = storage.get("median") or {}
    reach_ok = bool(median) and storage.get("grund") is None
    reach_state = (_round_quarter(median.get("bis_iso")) if median.get("bis_iso")
                   else (UNAVAILABLE if not reach_ok else "über Horizont"))
    result.append((REACH_ENTITY_ID, reach_state if reach_ok else UNAVAILABLE, {
        "friendly_name":       "EMS Speicher-Reichweite",
        "icon":                "mdi:battery-clock-outline",
        "gueltig":             reach_ok,
        "grund":               storage.get("grund"),
        "nutzbar_kwh":         _round(storage.get("nutzbar_kwh"), 1),
        "reichweite_vorsichtig": _round_quarter((storage.get("vorsichtig") or {}).get("bis_iso")),
        "reichweite_zuversichtlich": _round_quarter((storage.get("zuversichtlich") or {}).get("bis_iso")),
        "ueber_horizont":      median.get("ueber_horizont"),
    }))

    figures = status.get("kennzahlen") or {}
    window = figures.get("guenstigstes_fenster_reichweite") or {}
    overall = figures.get("guenstigstes_fenster_gesamt") or {}
    result.append((WINDOW_ENTITY_ID, f"{window['preis_mittel']}" if window else UNAVAILABLE, {
        "friendly_name":       "EMS Günstigstes Ladefenster",
        "icon":                "mdi:clock-check-outline",
        "unit_of_measurement": "€/kWh",
        "gueltig":             bool(window),
        "von":                 window.get("von_iso"),
        "bis":                 window.get("bis_iso"),
        "gesamt_preis":        overall.get("preis_mittel"),
        "gesamt_von":          overall.get("von_iso"),
        "gesamt_bis":          overall.get("bis_iso"),
        "horizont_reicht":     figures.get("horizont_reicht"),
    }))

    grid = status.get("netzladen") or {}
    result.append((GRID_ENTITY_ID, "zulaessig" if grid.get("zulaessig") else "gesperrt", {
        "friendly_name":       "EMS Netzladen",
        "icon":                "mdi:transmission-tower-import",
        "grund":               grid.get("grund"),
        "freigabe":            grid.get("freigabe"),
        "manuell":             grid.get("manuell"),
        "pv_zu_wenig":         grid.get("pv_zu_wenig"),
        "je_speicher":         {entry["name"]: entry["zulaessig"] for entry in grid.get("je_speicher") or []},
    }))
    return result


def _round(value: Optional[float], digits: int) -> Optional[float]:
    return None if value is None else round(value, digits)


def _round_quarter(iso: Optional[str]) -> Optional[str]:
    """Auf die Viertelstunde gerundet, damit der Sensor nicht jede Minute neu aufgezeichnet wird."""
    if not iso:
        return None
    moment = datetime.fromisoformat(iso)
    minutes = round((moment.minute + moment.second / 60) / 15) * 15
    return (moment.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)).isoformat()


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
