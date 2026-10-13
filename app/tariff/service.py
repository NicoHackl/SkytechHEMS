"""Preis- und Prognosemodul: Auswertung im eigenen Takt (D-065, Phase P3).

Das Modul liest ausschließlich den Zustandsschnappschuss, den der Regelzyklus
ohnehin holt – es löst keine eigene HA-Abfrage aus und nimmt nie den
Schreib-Lock des Zyklus. Es schaltet nichts: das Ergebnis ist reine Anzeige
(Statusobjekt für `GET api/tariff/status` und die Anzeige-Sensoren).

Invarianten (ADR D-065):

1. Ein Fehler hier beeinflusst den Regelzyklus nie.
2. Fehlende oder ungültige Daten ergeben einen Grund im Status, nie einen
   Ersatzwert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Dict, List, Optional

from tariff.price_source import (
    BERLIN, INTERVAL_AUTO, PriceCurve, PriceSlot, end_of_tomorrow, format_berlin, parse_price_curve, upcoming,
)
from tariff.pv_source import EnergyValue, PvCurve, parse_energy, parse_pv_curve

# Takt des Moduls. Der Zustand kommt aus dem Schnappschuss des Regelzyklus.
TARIFF_INTERVAL_S = 60
# Älter darf der Schnappschuss nicht sein, sonst gilt nichts als aktuell.
MAX_SNAPSHOT_AGE_S = 300
# So viele kommende Slots liefert der Status für die Tabelle der Oberfläche.
UPCOMING_LIMIT = 96

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass(frozen=True)
class TariffConfig:
    enabled: bool
    price_entity: str
    price_interval: str
    tomorrow_warning_time: str
    pv_today_entity: str
    pv_tomorrow_entity: str
    pv_today_remaining_entity: str
    pv_curve_entity: str
    pv_curve_attribute: str

    @staticmethod
    def option_keys() -> tuple:
        return ("tariff_enabled", "tariff_price_entity", "tariff_price_interval", "tariff_tomorrow_warning_time",
                "pv_today_entity", "pv_tomorrow_entity", "pv_today_remaining_entity", "pv_curve_entity",
                "pv_curve_attribute")

    @classmethod
    def from_options(cls, options: Dict[str, Any]) -> "TariffConfig":
        return cls(
            enabled=bool(options.get("tariff_enabled")),
            price_entity=str(options.get("tariff_price_entity") or ""),
            price_interval=str(options.get("tariff_price_interval") or INTERVAL_AUTO),
            tomorrow_warning_time=str(options.get("tariff_tomorrow_warning_time") or "15:00"),
            pv_today_entity=str(options.get("pv_today_entity") or ""),
            pv_tomorrow_entity=str(options.get("pv_tomorrow_entity") or ""),
            pv_today_remaining_entity=str(options.get("pv_today_remaining_entity") or ""),
            pv_curve_entity=str(options.get("pv_curve_entity") or ""),
            pv_curve_attribute=str(options.get("pv_curve_attribute") or "forecast"),
        )


def is_valid_time(text: str) -> bool:
    return bool(_TIME_RE.match(text or ""))


def _slot_view(slot: PriceSlot) -> Dict[str, Any]:
    start = slot.start.astimezone(BERLIN)
    end = slot.end.astimezone(BERLIN)
    return {
        "tag": start.strftime("%d.%m.%Y"),
        "von": start.strftime("%H:%M"),
        "bis": end.strftime("%H:%M"),
        "von_iso": slot.start.isoformat(),
        "bis_iso": slot.end.isoformat(),
        "preis": round(slot.price, 5),
    }


def _energy_view(entity: str, value: Optional[EnergyValue]) -> Dict[str, Any]:
    if not entity:
        return {"entity": "", "gueltig": False, "wert_kwh": None, "grund": "nicht konfiguriert"}
    assert value is not None
    return {"entity": entity, "gueltig": value.valid,
            "wert_kwh": None if value.value_kwh is None else round(value.value_kwh, 3),
            "grund": value.reason}


class TariffService:
    """Hält die letzte Auswertung. `evaluate` ist rein bis auf diesen Speicher."""

    def __init__(self, config: TariffConfig) -> None:
        self.config = config
        self.price: Optional[PriceCurve] = None
        self.pv_curve: Optional[PvCurve] = None
        self.pv_values: Dict[str, Optional[EnergyValue]] = {}
        self.status: Dict[str, Any] = self._disabled_status() if not config.enabled else {
            "aktiv": True, "stand": None, "grund": "Noch keine Auswertung", "preis": None, "pv": None,
        }

    def _disabled_status(self) -> Dict[str, Any]:
        return {"aktiv": False, "stand": None, "grund": "Dynamischer Strompreis ist ausgeschaltet",
                "preis": None, "pv": None}

    def evaluate(self, states: Dict[str, Any], snapshot_age_s: Optional[float], now: datetime) -> Dict[str, Any]:
        """Wertet den Schnappschuss aus und legt das Ergebnis in `status` ab."""
        config = self.config
        if not config.enabled:
            self.status = self._disabled_status()
            return self.status
        stale_reason: Optional[str] = None
        if snapshot_age_s is None:
            stale_reason = "Noch kein Zustand von Home Assistant"
        elif snapshot_age_s > MAX_SNAPSHOT_AGE_S:
            stale_reason = f"Zustand von Home Assistant ist {int(snapshot_age_s)} s alt"
        if stale_reason:
            states = {}

        self.price = parse_price_curve(states.get(config.price_entity), config.price_interval, now)
        self.pv_values = {
            key: (parse_energy(states.get(entity)) if entity else None)
            for key, entity in (("heute", config.pv_today_entity), ("morgen", config.pv_tomorrow_entity),
                                ("rest_heute", config.pv_today_remaining_entity))
        }
        self.pv_curve = (parse_pv_curve(states.get(config.pv_curve_entity), config.pv_curve_attribute, now)
                         if config.pv_curve_entity else None)

        self.status = {
            "aktiv": True,
            "stand": format_berlin(now, with_seconds=True),
            "grund": stale_reason,
            "preis": self._price_view(now, stale_reason),
            "pv": self._pv_view(stale_reason),
        }
        return self.status

    # ------------------------------------------------------------------

    def _price_view(self, now: datetime, stale_reason: Optional[str]) -> Dict[str, Any]:
        config, curve = self.config, self.price
        assert curve is not None
        view: Dict[str, Any] = {
            "entity": config.price_entity,
            "raster_einstellung": config.price_interval,
            "raster_erkannt_min": curve.detected_raster_min,
            "gueltig": curve.valid,
            "grund": stale_reason or curve.reason,
            "einheit": curve.unit,
        }
        if not curve.valid:
            return view
        horizon = curve.horizon_until
        assert horizon is not None and curve.current is not None
        coming = upcoming(curve, now)
        tomorrow_complete = horizon >= end_of_tomorrow(now)
        warning_due = now.astimezone(BERLIN).time() >= time.fromisoformat(config.tomorrow_warning_time) \
            if is_valid_time(config.tomorrow_warning_time) else False
        cheapest = min(coming, key=lambda slot: (slot.price, slot.start))
        dearest = max(coming, key=lambda slot: (slot.price, -slot.start.timestamp()))
        view.update({
            "raster_min": curve.raster_min,
            "aktuell": _slot_view(curve.current),
            "horizont_bis": format_berlin(horizon),
            "horizont_bis_iso": horizon.isoformat(),
            "stunden_voraus": round((horizon - now).total_seconds() / 3600, 1),
            "morgen_vorhanden": tomorrow_complete,
            "warnung": ("Preise für morgen fehlen noch" if warning_due and not tomorrow_complete else None),
            "guenstigster": _slot_view(cheapest),
            "teuerster": _slot_view(dearest),
            "kommend": [_slot_view(slot) for slot in coming[:UPCOMING_LIMIT]],
            "kommend_gesamt": len(coming),
        })
        return view

    def _pv_view(self, stale_reason: Optional[str]) -> Dict[str, Any]:
        config = self.config
        view: Dict[str, Any] = {
            "heute": _energy_view(config.pv_today_entity, self.pv_values.get("heute")),
            "morgen": _energy_view(config.pv_tomorrow_entity, self.pv_values.get("morgen")),
            "rest_heute": _energy_view(config.pv_today_remaining_entity, self.pv_values.get("rest_heute")),
        }
        curve = self.pv_curve
        if curve is None:
            view["kurve"] = {"entity": "", "attribut": config.pv_curve_attribute, "gueltig": False,
                             "grund": "nicht konfiguriert"}
        else:
            days: List[Dict[str, Any]] = [
                {"tag": day.strftime("%d.%m.%Y"), "kwh": round(kwh, 2)}
                for day, kwh in sorted(curve.energy_per_day_kwh().items())
            ]
            view["kurve"] = {
                "entity": config.pv_curve_entity,
                "attribut": config.pv_curve_attribute,
                "gueltig": curve.valid,
                "grund": stale_reason or curve.reason,
                "raster_min": curve.raster_min,
                "bis": format_berlin(curve.until) if curve.valid and curve.until else None,
                "bis_iso": curve.until.isoformat() if curve.valid and curve.until else None,
                "tage": days if curve.valid else [],
            }
        if stale_reason:
            for key in ("heute", "morgen", "rest_heute"):
                if view[key]["entity"]:
                    view[key].update({"gueltig": False, "wert_kwh": None, "grund": stale_reason})
        return view
