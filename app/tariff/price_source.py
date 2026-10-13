"""Preiskurve aus dem konfigurierten HA-Sensor lesen und prüfen (D-065).

Erwartet wird das Format von `sensor.epex_spot_data_total_price_2`: Zustand =
aktueller Endpreis, Attribut `data` = Liste von `{start_time, end_time,
price_per_kwh}`. Der Sensor liefert den tatsächlich zu zahlenden Endpreis; hier
wird nichts aufgeschlagen und nichts umgerechnet.

Grenzen dieses Moduls:

* Es spricht nicht mit Home Assistant. Es bekommt einen Zustand aus dem
  Schnappschuss des HAClient.
* Es kennt keinen Ersatzwert. Jede verletzte Regel macht die ganze Kurve
  ungültig, der Grund steht im Ergebnis (Invariante 3 aus D-065).
* Es rechnet über Zeitstempel, nie über Slot-Anzahlen. Tage mit 92 oder 100
  Viertelstunden (Zeitumstellung) sind deshalb kein Sonderfall.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")

INTERVAL_AUTO = "auto"
INTERVAL_CHOICES = (INTERVAL_AUTO, "15", "60")
SUPPORTED_RASTERS_MIN = (15, 60)
SUPPORTED_UNITS = ("€/kWh", "EUR/kWh")
UNAVAILABLE_STATES = ("unavailable", "unknown")


@dataclass(frozen=True)
class PriceSlot:
    start: datetime
    end: datetime
    price: float


@dataclass
class PriceCurve:
    """Ergebnis der Prüfung. Bei `valid = False` sind `slots` leer."""

    valid: bool
    reason: Optional[str] = None
    raster_min: Optional[int] = None
    detected_raster_min: Optional[int] = None
    slots: List[PriceSlot] = field(default_factory=list)
    current: Optional[PriceSlot] = None
    unit: Optional[str] = None

    @property
    def horizon_until(self) -> Optional[datetime]:
        return self.slots[-1].end if self.slots else None


def format_berlin(moment: datetime, with_seconds: bool = False) -> str:
    """Für Menschen: TT.MM.JJJJ hh:mm in Berliner Zeit, ohne Zonenangabe (Regel 9)."""
    return moment.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M:%S" if with_seconds else "%d.%m.%Y %H:%M")


def parse_timestamp(raw: Any) -> Optional[datetime]:
    """ISO-Zeitstempel mit Zonenangabe; ohne Zone ist er mehrdeutig und ungültig."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def _finite_number(raw: Any) -> Optional[float]:
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _invalid(reason: str, **extra: Any) -> PriceCurve:
    return PriceCurve(valid=False, reason=reason, **extra)


def parse_price_curve(state: Optional[dict], interval_setting: str, now: datetime) -> PriceCurve:
    """Liest und prüft die Preiskurve. `now` muss eine Zeitzone tragen."""
    if state is None:
        return _invalid("Preissensor nicht gefunden")
    raw_state = str(state.get("state") or "")
    if raw_state in UNAVAILABLE_STATES:
        return _invalid(f"Preissensor meldet {raw_state}")
    attributes = state.get("attributes") or {}

    unit = attributes.get("unit_of_measurement")
    if unit not in SUPPORTED_UNITS:
        shown = unit if unit else "keine"
        return _invalid(f"Einheit {shown} wird nicht unterstützt (erwartet €/kWh)")

    data = attributes.get("data")
    if not isinstance(data, list) or not data:
        return _invalid("Attribut data fehlt oder ist leer", unit=unit)

    slots: List[PriceSlot] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            return _invalid(f"Eintrag {index + 1} ist kein Objekt", unit=unit)
        start = parse_timestamp(entry.get("start_time"))
        end = parse_timestamp(entry.get("end_time"))
        price = _finite_number(entry.get("price_per_kwh"))
        if start is None or end is None:
            return _invalid(f"Eintrag {index + 1}: Zeitstempel fehlt oder hat keine Zeitzone", unit=unit)
        if price is None:
            return _invalid(f"Eintrag {index + 1}: Preis fehlt oder ist keine endliche Zahl", unit=unit)
        if end <= start:
            return _invalid(f"Eintrag {index + 1}: Ende liegt nicht nach dem Beginn", unit=unit)
        slots.append(PriceSlot(start, end, price))

    durations = {int((slot.end - slot.start).total_seconds() // 60) for slot in slots}
    exact = all((slot.end - slot.start).total_seconds() % 60 == 0 for slot in slots)
    if len(durations) != 1 or not exact:
        return _invalid("Gemischte Rasterlängen in der Preiskurve", unit=unit)
    detected = durations.pop()
    if detected not in SUPPORTED_RASTERS_MIN:
        return _invalid(f"Raster von {detected} min wird nicht unterstützt (erwartet 15 oder 60 min)",
                        detected_raster_min=detected, unit=unit)
    if interval_setting != INTERVAL_AUTO and int(interval_setting) != detected:
        return _invalid(
            f"Raster passt nicht zur Auswahl (Sensor: {detected} min, gewählt: {interval_setting} min)",
            detected_raster_min=detected, unit=unit)

    for previous, following in zip(slots, slots[1:]):
        if following.start < previous.start:
            return _invalid("Preiskurve ist nicht aufsteigend sortiert", detected_raster_min=detected, unit=unit)
        if following.start != previous.end:
            return _invalid(
                f"Lücke oder Überschneidung zwischen {format_berlin(previous.end)} und {format_berlin(following.start)}",
                detected_raster_min=detected, unit=unit)

    current = next((slot for slot in slots if slot.start <= now < slot.end), None)
    if current is None:
        return _invalid("Aktueller Zeitpunkt liegt nicht in der Preiskurve", detected_raster_min=detected, unit=unit)

    return PriceCurve(valid=True, raster_min=detected, detected_raster_min=detected, slots=slots,
                      current=current, unit=unit)


def end_of_tomorrow(now: datetime) -> datetime:
    """Ende des morgigen Berliner Kalendertags, unabhängig von der Zeitumstellung."""
    local = now.astimezone(BERLIN)
    day_after = (local + timedelta(days=2)).date()
    return datetime(day_after.year, day_after.month, day_after.day, tzinfo=BERLIN)


def upcoming(curve: PriceCurve, now: datetime) -> List[PriceSlot]:
    """Laufender und alle späteren Slots."""
    return [slot for slot in curve.slots if slot.end > now]
