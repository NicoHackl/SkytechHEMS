"""PV-Prognose von Helios lesen und prüfen (D-065).

Drei Tagessensoren in kWh (heute, morgen, Rest heute) und eine Kurve im
Attribut eines weiteren Sensors: Liste von `{datetime, watts, p10, p90}`.
`datetime` ist der Beginn eines Slots, die Slotlänge ergibt sich aus dem Abstand
der Einträge.

Wie beim Preis gilt: kein Ersatzwert, kein stilles Umrechnen von Einheiten.
Ein ungültiger Tageswert lässt die übrigen Werte und die Kurve unberührt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from tariff.price_source import BERLIN, UNAVAILABLE_STATES, _finite_number, parse_timestamp

ENERGY_UNITS = ("kWh",)
SUPPORTED_RASTERS_MIN = (15, 60)


@dataclass
class EnergyValue:
    valid: bool
    value_kwh: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class PvSlot:
    start: datetime
    watts: float
    p10: Optional[float]
    p90: Optional[float]


@dataclass
class PvCurve:
    valid: bool
    reason: Optional[str] = None
    raster_min: Optional[int] = None
    slots: List[PvSlot] = field(default_factory=list)

    @property
    def until(self) -> Optional[datetime]:
        if not self.slots or self.raster_min is None:
            return None
        return self.slots[-1].start + timedelta(minutes=self.raster_min)

    def energy_per_day_kwh(self) -> Dict[date, float]:
        """Tagessummen nach Berliner Kalendertag – zur Plausibilisierung gegen die Tagessensoren."""
        result: Dict[date, float] = {}
        if self.raster_min is None:
            return result
        hours = self.raster_min / 60
        for slot in self.slots:
            day = slot.start.astimezone(BERLIN).date()
            result[day] = result.get(day, 0.0) + slot.watts * hours / 1000
        return result


def parse_energy(state: Optional[dict]) -> EnergyValue:
    """Ein Tageswert in kWh, mindestens 0."""
    if state is None:
        return EnergyValue(False, reason="Sensor nicht gefunden")
    raw = str(state.get("state") or "")
    if raw in UNAVAILABLE_STATES:
        return EnergyValue(False, reason=f"Sensor meldet {raw}")
    unit = (state.get("attributes") or {}).get("unit_of_measurement")
    if unit not in ENERGY_UNITS:
        return EnergyValue(False, reason=f"Einheit {unit or 'keine'} wird nicht unterstützt (erwartet kWh)")
    value = _finite_number(raw)
    if value is None or value < 0:
        return EnergyValue(False, reason="Kein gültiger Zahlenwert ≥ 0")
    return EnergyValue(True, value_kwh=value)


def _optional_band(raw: Any) -> tuple[bool, Optional[float]]:
    if raw is None:
        return True, None
    value = _finite_number(raw)
    return (value is not None and value >= 0), value


def parse_pv_curve(state: Optional[dict], attribute: str, now: datetime) -> PvCurve:
    """Liest die Prognosekurve aus `attribute`; `now` muss eine Zeitzone tragen."""
    if state is None:
        return PvCurve(False, reason="Sensor der Prognosekurve nicht gefunden")
    data = (state.get("attributes") or {}).get(attribute)
    if not isinstance(data, list) or not data:
        return PvCurve(False, reason=f"Attribut {attribute} fehlt oder ist leer")

    slots: List[PvSlot] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            return PvCurve(False, reason=f"Eintrag {index + 1} ist kein Objekt")
        start = parse_timestamp(entry.get("datetime"))
        watts = _finite_number(entry.get("watts"))
        ok_p10, p10 = _optional_band(entry.get("p10"))
        ok_p90, p90 = _optional_band(entry.get("p90"))
        if start is None:
            return PvCurve(False, reason=f"Eintrag {index + 1}: Zeitstempel fehlt oder hat keine Zeitzone")
        if watts is None or watts < 0 or not ok_p10 or not ok_p90:
            return PvCurve(False, reason=f"Eintrag {index + 1}: Leistung fehlt oder ist kein Wert ≥ 0")
        slots.append(PvSlot(start, watts, p10, p90))

    if len(slots) < 2:
        return PvCurve(False, reason="Zu wenige Einträge, um das Raster zu bestimmen")
    steps = {(following.start - previous.start).total_seconds() for previous, following in zip(slots, slots[1:])}
    if len(steps) != 1:
        return PvCurve(False, reason="Kurve ist lückenhaft, unsortiert oder hat gemischte Abstände")
    step_s = steps.pop()
    if step_s <= 0 or step_s % 60 or int(step_s // 60) not in SUPPORTED_RASTERS_MIN:
        return PvCurve(False, reason="Abstand der Einträge muss 15 oder 60 min betragen")
    curve = PvCurve(True, raster_min=int(step_s // 60), slots=slots)
    if curve.until is not None and curve.until <= now:
        return PvCurve(False, reason="Kurve liegt vollständig in der Vergangenheit")
    return curve
