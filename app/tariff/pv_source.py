"""PV-Prognose von Helios lesen und prüfen (D-065).

Drei Tagessensoren in kWh (heute, morgen, Rest heute) und eine Kurve im
Attribut eines weiteren Sensors: Liste von `{datetime, watts, p10, p90}`.
`datetime` ist der Beginn eines Slots, die Slotlänge ergibt sich aus dem Abstand
der Einträge.

Wie beim Preis gilt: kein Ersatzwert, kein stilles Umrechnen von Einheiten.
Ein ungültiger Tageswert lässt die übrigen Werte und die Kurve unberührt.

Zeitumstellung: Helios zählt die Slots nach Berliner Wanduhr (je Tag 96
Viertelstunden). Die Kurve muss real lückenlos sein; toleriert wird nur dieses
eine Muster, und nur, wenn die betroffenen Werte 0 W sind (nachts):

* Herbst: Die doppelte Stunde 02:00–02:59 kommt nur einmal (Sommerzeit). Die
  fehlenden Slots der Winterzeit werden eingefügt, mit den Werten derselben
  Wanduhrzeit (`dst_filled`).
* Frühjahr: Helios liefert auch die übersprungene Stunde 02:00–02:59. Diese
  Zeiten gibt es nicht; ihr Offset passt nicht zu Berlin und sie doppeln reale
  Zeitpunkte der Sommerzeit. Sie werden verworfen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from tariff.price_source import BERLIN, UNAVAILABLE_STATES, _finite_number, format_berlin, parse_timestamp

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
    # Eingefügt für die doppelte Stunde der Herbst-Umstellung (Werte derselben Wanduhrzeit).
    dst_filled: bool = False


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
    slots, reason = _drop_spring_phantoms(slots)
    if reason:
        return PvCurve(False, reason=reason)
    if len(slots) < 2:
        return PvCurve(False, reason="Zu wenige Einträge, um das Raster zu bestimmen")
    raster = _raster(slots)
    if raster is None or raster.total_seconds() % 60 or int(raster.total_seconds() // 60) not in SUPPORTED_RASTERS_MIN:
        return PvCurve(False, reason="Abstand der Einträge muss 15 oder 60 min betragen")

    by_wall: Dict[datetime, PvSlot] = {}
    for slot in slots:
        by_wall.setdefault(_wall(slot.start), slot)
    complete: List[PvSlot] = [slots[0]]
    for previous, following in zip(slots, slots[1:]):
        step = following.start - previous.start
        if step <= timedelta(0):
            return PvCurve(False, reason=f"Kurve ist unsortiert oder doppelt bei {format_berlin(following.start)}")
        if step != raster:
            missing = _dst_gap(previous, following, raster)
            if missing is None:
                return PvCurve(False, reason=f"Kurve ist lückenhaft zwischen {format_berlin(previous.start)} "
                                             f"und {format_berlin(following.start)}")
            for k in range(1, missing + 1):
                start = _fixed_berlin(previous.start + raster * k)
                twin = by_wall.get(_wall(start))
                if twin is None or twin.start == start:
                    return PvCurve(False, reason=f"Zeitumstellung {_day(start)}: Werte der doppelten Stunde fehlen")
                if not _is_zero(twin):
                    return PvCurve(False, reason=f"Zeitumstellung {_day(start)}: Helios-Werte der doppelten "
                                                 "Stunde sind nicht 0 W")
                complete.append(PvSlot(start, twin.watts, twin.p10, twin.p90, dst_filled=True))
        complete.append(following)

    curve = PvCurve(True, raster_min=int(raster.total_seconds() // 60), slots=complete)
    if curve.until is not None and curve.until <= now:
        return PvCurve(False, reason="Kurve liegt vollständig in der Vergangenheit")
    return curve


def _wall(moment: datetime) -> datetime:
    """Berliner Wanduhrzeit ohne Zone; in der doppelten Herbststunde für beide Offsets gleich."""
    return moment.astimezone(BERLIN).replace(tzinfo=None)


def _fixed_berlin(moment: datetime) -> datetime:
    """Berliner Zeit mit festem Offset wie aus `parse_timestamp`. Nicht `ZoneInfo` selbst: Ein
    Zeitpunkt der doppelten Stunde mit `fold=1` ist laut PEP 495 nie gleich einem anderer Zonen."""
    return moment.astimezone(timezone(moment.astimezone(BERLIN).utcoffset() or timedelta(0)))


def _day(moment: datetime) -> str:
    return moment.astimezone(BERLIN).strftime("%d.%m.%Y")


def _is_zero(slot: PvSlot) -> bool:
    return slot.watts == 0 and not slot.p10 and not slot.p90


def _offset_matches_berlin(moment: datetime) -> bool:
    return moment.utcoffset() == moment.astimezone(BERLIN).utcoffset()


def _in_spring_gap(moment: datetime) -> bool:
    """Wanduhrzeit (mit dem mitgelieferten Offset gelesen) gibt es in Berlin nicht."""
    wall = moment.replace(tzinfo=None)
    local = wall.replace(tzinfo=BERLIN)
    return local.astimezone(timezone.utc).astimezone(BERLIN).replace(tzinfo=None) != wall


def _drop_spring_phantoms(slots: List[PvSlot]) -> tuple[List[PvSlot], Optional[str]]:
    """Frühjahr: Einträge der übersprungenen Stunde verwerfen, wenn sie reale Zeitpunkte doppeln."""
    phantoms = [slot for slot in slots if not _offset_matches_berlin(slot.start) and _in_spring_gap(slot.start)]
    if not phantoms:
        return slots, None
    # Über die Identität: `==` vergleicht Zeitpunkte real, ein Phantom gleicht seinem Doppel.
    phantom_ids = {id(slot) for slot in phantoms}
    real = {slot.start for slot in slots if id(slot) not in phantom_ids}
    dropped = {id(slot) for slot in phantoms if slot.start in real}
    for slot in phantoms:
        if id(slot) in dropped and not _is_zero(slot):
            return slots, (f"Zeitumstellung {_day(slot.start)}: Helios-Werte der übersprungenen Stunde "
                           "sind nicht 0 W")
    return [slot for slot in slots if id(slot) not in dropped], None


def _raster(slots: List[PvSlot]) -> Optional[timedelta]:
    """Häufigster Abstand (bei Gleichstand der kleinere) zwischen Einträgen ohne Offset-Wechsel dazwischen."""
    steps = [following.start - previous.start for previous, following in zip(slots, slots[1:])]
    plain = [step for step, previous, following in zip(steps, slots, slots[1:])
             if previous.start.astimezone(BERLIN).utcoffset() == following.start.astimezone(BERLIN).utcoffset()]
    candidates = [step for step in (plain or steps) if step > timedelta(0)]
    if not candidates:
        return None
    return max(set(candidates), key=lambda step: (candidates.count(step), -step))


def _dst_gap(previous: PvSlot, following: PvSlot, raster: timedelta) -> Optional[int]:
    """Anzahl fehlender Slots, wenn zwischen den Einträgen die Herbst-Umstellung liegt, sonst None.

    Muster: Abstand auf der Wanduhr = Raster, beide Offsets passen zu Berlin, Berlin wechselt
    dazwischen den Offset, und der reale Abstand ist um genau diesen Wechsel länger.
    """
    if not (_offset_matches_berlin(previous.start) and _offset_matches_berlin(following.start)):
        return None
    before, after = previous.start.utcoffset(), following.start.utcoffset()
    if before is None or after is None:
        return None
    shift = before - after
    if shift <= timedelta(0) or shift % raster:
        return None
    if _wall(following.start) - _wall(previous.start) != raster:
        return None
    if following.start - previous.start != raster + shift:
        return None
    return shift // raster
