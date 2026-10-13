"""Verbrauchsprognose `profil_v1` für die Grundlast (D-065, Phase P5).

Deterministisch und nachvollziehbar:

1. Historie: `hems.grundlast_w` der letzten 28 Tage im 15-min-Raster (aus Data
   Insight, Rolle `grundlast`).
2. Tagtyp nach Berliner Kalender: Werktag, Samstag, Sonntag. Feiertage werden in
   v1 nicht erkannt (Plan E-10).
3. Je Uhrzeit-Slot (Berliner Ortszeit) und Tagtyp ein gewichteter Median der
   passenden Tage; jüngere Tage zählen mehr (Halbwertszeit 7 Tage). Dazu p10 und
   p90 als gewichtete Quantile für das Unsicherheitsband. Gibt es für Tagtyp und
   Uhrzeit weniger als zwei Werte, zählen alle Tagtypen dieser Uhrzeit.
4. Horizont 48 h. Weniger als 7 Tage Historie: keine Prognose, kein Ersatzwert.

Gerechnet wird über Zeitstempel. Tage mit 92 oder 100 Viertelstunden sind
kein Sonderfall: der Schlüssel ist die Ortszeit hh:mm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from tariff.price_source import BERLIN

METHOD = "profil_v1"
HISTORY = timedelta(days=28)
HORIZON = timedelta(hours=48)
SLOT = timedelta(minutes=15)
MIN_HISTORY_DAYS = 7
HALF_LIFE_DAYS = 7.0
MIN_SAMPLES = 2
PARAMETERS = {"historie_tage": 28, "halbwertszeit_tage": HALF_LIFE_DAYS, "tagtypen": ["werktag", "samstag", "sonntag"],
              "quantile": [0.1, 0.5, 0.9], "min_historie_tage": MIN_HISTORY_DAYS, "horizont_h": 48}


@dataclass(frozen=True)
class LoadSlot:
    start: datetime
    p50: float
    p10: float
    p90: float


@dataclass
class LoadForecast:
    valid: bool
    reason: Optional[str] = None
    created: Optional[datetime] = None
    history_days: int = 0
    slots: List[LoadSlot] = field(default_factory=list)

    def slot_at(self, moment: datetime) -> Optional[LoadSlot]:
        for slot in self.slots:
            if slot.start <= moment < slot.start + SLOT:
                return slot
        return None

    def energy_kwh(self, start: datetime, end: datetime, attr: str = "p50") -> float:
        """Energie der Prognose in [start, end), anteilig für angeschnittene Slots."""
        total = 0.0
        for slot in self.slots:
            begin, finish = max(slot.start, start), min(slot.start + SLOT, end)
            if finish > begin:
                total += getattr(slot, attr) * (finish - begin).total_seconds() / 3600 / 1000
        return total


def day_type(moment: datetime) -> str:
    weekday = moment.astimezone(BERLIN).weekday()
    return "samstag" if weekday == 5 else ("sonntag" if weekday == 6 else "werktag")


def _local_key(moment: datetime) -> str:
    return moment.astimezone(BERLIN).strftime("%H:%M")


def weighted_quantile(samples: List[Tuple[float, float]], q: float) -> float:
    """Gewichtetes Quantil (Wert, Gewicht) mit linearer Interpolation der kumulierten Mitten."""
    ordered = sorted(samples)
    total = sum(weight for _, weight in ordered)
    if len(ordered) == 1 or total <= 0:
        return ordered[0][0]
    positions = []
    cumulative = 0.0
    for value, weight in ordered:
        positions.append(((cumulative + weight / 2) / total, value))
        cumulative += weight
    if q <= positions[0][0]:
        return positions[0][1]
    if q >= positions[-1][0]:
        return positions[-1][1]
    for (p_low, v_low), (p_high, v_high) in zip(positions, positions[1:]):
        if p_low <= q <= p_high:
            share = 0.0 if p_high == p_low else (q - p_low) / (p_high - p_low)
            return v_low + share * (v_high - v_low)
    return positions[-1][1]


def floor_slot(moment: datetime) -> datetime:
    moment = moment.astimezone(timezone.utc)
    return moment.replace(minute=moment.minute - moment.minute % 15, second=0, microsecond=0)


def forecast(history: Dict[datetime, float], now: datetime) -> LoadForecast:
    """Prognose ab dem laufenden Slot für 48 h aus der Grundlast-Historie."""
    history = {slot: value for slot, value in history.items() if now - HISTORY <= slot < now}
    days = {slot.astimezone(BERLIN).date() for slot in history}
    if len(days) < MIN_HISTORY_DAYS:
        return LoadForecast(False, reason=f"Historie zu kurz ({len(days)} von {MIN_HISTORY_DAYS} Tagen)",
                            created=now, history_days=len(days))

    by_key: Dict[Tuple[str, str], List[Tuple[float, float]]] = {}
    by_time: Dict[str, List[Tuple[float, float]]] = {}
    for slot, value in history.items():
        age_days = (now - slot).total_seconds() / 86400
        weight = 0.5 ** (age_days / HALF_LIFE_DAYS)
        time_key = _local_key(slot)
        by_key.setdefault((day_type(slot), time_key), []).append((value, weight))
        by_time.setdefault(time_key, []).append((value, weight))

    slots: List[LoadSlot] = []
    moment = floor_slot(now)
    end = moment + HORIZON
    while moment < end:
        time_key = _local_key(moment)
        samples = by_key.get((day_type(moment), time_key), [])
        if len(samples) < MIN_SAMPLES:
            samples = by_time.get(time_key, [])
        if samples:
            slots.append(LoadSlot(moment, round(weighted_quantile(samples, 0.5), 1),
                                  round(weighted_quantile(samples, 0.1), 1),
                                  round(weighted_quantile(samples, 0.9), 1)))
        moment += SLOT
    if not slots:
        return LoadForecast(False, reason="Keine passenden Werte in der Historie", created=now,
                            history_days=len(days))
    return LoadForecast(True, created=now, history_days=len(days), slots=slots)
