"""Abgleich mit Skytech Data Insight (D-065, Phase P4).

Was hier entschieden wird – die Datenbank selbst spricht nur `insight_client`:

1. **Rollen:** welche HA-Sensoren das HEMS in Data Insight braucht, unter
   welcher Rolle. Fehlende werden angelegt, vorhandene übernommen, nicht mehr
   gebrauchte stillgelegt (Vertrag 0.2, „Verwaltete Sensoren“, „Rollen“).
2. **Preis- und PV-Läufe:** ein Preislauf, wenn sich die Kurve geändert hat; ein
   PV-Lauf stündlich oder bei geänderter Kurve, höchstens alle 15 min.
3. **Grundlast:** `hems.grundlast_w` je abgeschlossenem 15-min-Slot aus den in
   Data Insight aufgezeichneten Einzelsensoren. Dieselbe Rechnung füllt Lücken
   nach einem Ausfall (höchstens 10 Tage zurück).

Grundlast = Hausverbrauch − Σ Istleistung der HEMS-Verbraucher
            − Σ Leistung der Speicher mit `tariff_in_house_load` (positiv = laden).
Der Hausverbrauch-Sensor dieser Anlage (E3DC) enthält alle Überschussverbraucher
und die Netto-Leistung der AC-Speicher, nicht aber den E3DC-Akku.

Ein Fehler hier betrifft nur die Speicherung, nie den Regelzyklus und nie die
Anzeige des Preis- und Prognosemoduls.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from insight_client import InsightClient, InsightError, InsightSettings
from tariff.price_source import PriceCurve, format_berlin
from tariff.pv_source import PvCurve

log = logging.getLogger(__name__)

SLOT = timedelta(minutes=15)
# Erst so lange nach Slot-Ende rechnen: Data Insight braucht die Minutenwerte.
SLOT_DELAY = timedelta(minutes=2)
MAX_BACKFILL = timedelta(days=10)
MIN_COVERAGE = 0.8 * SLOT.total_seconds()
RECONCILE_INTERVAL_S = 15 * 60
PV_RUN_INTERVAL_S = 60 * 60
PV_RUN_MIN_GAP_S = 15 * 60
PV_HORIZON = timedelta(hours=48)
GRUNDLAST_ROLE = "grundlast"
GRUNDLAST_ENTITY = "hems.grundlast_w"
_ROLE_SUFFIX_RE = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class RoleSpec:
    role: str
    entity_id: str
    name: str
    category: str
    quantity: str
    unit: Optional[str]
    source: str = "ha"


@dataclass
class GrundlastTerm:
    """Ein Summand der Grundlast: Rolle, Vorzeichen, Faktor (z. B. Leistung × Schaltanteil)."""

    role: str
    sign: float
    factor: float = 1.0
    needs_watt: bool = True


@dataclass
class SyncStatus:
    konfiguriert: bool = False
    verbunden: bool = False
    host: Optional[str] = None
    grund: Optional[str] = None
    letzter_abgleich: Optional[str] = None
    rollen: List[Dict[str, Any]] = field(default_factory=list)
    hinweise: List[str] = field(default_factory=list)
    letzter_preislauf: Optional[str] = None
    letzter_pv_lauf: Optional[str] = None
    grundlast_bis: Optional[str] = None
    grundlast_grund: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


def _floor_slot(moment: datetime) -> datetime:
    moment = moment.astimezone(timezone.utc)
    return moment.replace(minute=moment.minute - moment.minute % 15, second=0, microsecond=0)


def _unit(states: Dict[str, Any], entity_id: str) -> Optional[str]:
    unit = ((states.get(entity_id) or {}).get("attributes") or {}).get("unit_of_measurement")
    return str(unit) if unit else None


def build_roles(options: Dict[str, Any], devices: List[Dict[str, Any]], states: Dict[str, Any]
                ) -> Tuple[List[RoleSpec], List[GrundlastTerm], List[str]]:
    """Rollen, Summanden der Grundlast und Hinweise aus Optionen und Geräten."""
    specs: List[RoleSpec] = []
    terms: List[GrundlastTerm] = []
    notes: List[str] = []

    def add(role: str, entity: str, name: str, category: str, quantity: str) -> None:
        if entity:
            specs.append(RoleSpec(role, entity, name, category, quantity, _unit(states, entity)))

    house = options.get("tariff_house_load_entity") or ""
    add("hausverbrauch", house, "HEMS Hausverbrauch", "verbraucher", "leistung")
    add("pv_ist", options.get("pv_actual_entity") or "", "HEMS PV-Leistung", "pv", "leistung")
    add("preis", options.get("tariff_price_entity") or "", "HEMS Strompreis", "netz", "preis")
    add("pv_prognose_heute", options.get("pv_today_entity") or "", "HEMS PV-Prognose heute", "pv", "energie")
    add("pv_prognose_morgen", options.get("pv_tomorrow_entity") or "", "HEMS PV-Prognose morgen", "pv", "energie")
    add("pv_prognose_rest_heute", options.get("pv_today_remaining_entity") or "",
        "HEMS PV-Prognose Rest heute", "pv", "energie")

    grundlast_ok = bool(house)
    if not house:
        notes.append("Ohne Hausverbrauch-Sensor keine Grundlast")
    for device in devices:
        name = device.get("name") or ""
        label = device.get("label") or name
        if not _ROLE_SUFFIX_RE.match(name):
            notes.append(f"Gerät {name!r}: Name taugt nicht als Rollenbezeichner, übersprungen")
            grundlast_ok = False
            continue
        cls = device.get("class")
        if cls == "controllable":
            add(f"verbraucher_ist:{name}", device.get("actual_power_entity") or "",
                f"HEMS {label} Istleistung", "verbraucher", "leistung")
            terms.append(GrundlastTerm(f"verbraucher_ist:{name}", -1.0))
        elif cls == "binary":
            if device.get("power_actual_entity"):
                add(f"verbraucher_ist:{name}", device["power_actual_entity"],
                    f"HEMS {label} Istleistung", "verbraucher", "leistung")
                terms.append(GrundlastTerm(f"verbraucher_ist:{name}", -1.0))
            else:
                add(f"verbraucher_schaltzustand:{name}", device.get("switch_entity") or "",
                    f"HEMS {label} Schaltzustand", "verbraucher", "zustand")
                power = float(device.get("power_w") or 0.0)
                terms.append(GrundlastTerm(f"verbraucher_schaltzustand:{name}", -1.0, power, needs_watt=False))
        elif cls == "battery":
            add(f"speicher_soc:{name}", device.get("soc_entity") or "", f"HEMS {label} Ladezustand",
                "speicher", "ladezustand")
            power_entity = device.get("power_entity") or ""
            if power_entity:
                add(f"speicher_leistung:{name}", power_entity, f"HEMS {label} Leistung", "speicher", "leistung")
            if device.get("tariff_in_house_load"):
                if not power_entity:
                    notes.append(f"Speicher {name}: getrennte Lade-/Entladesensoren werden für die Grundlast "
                                 "noch nicht unterstützt")
                    grundlast_ok = False
                else:
                    sign = -1.0 if (device.get("power_sign") or "positiv_laden") == "positiv_laden" else 1.0
                    terms.append(GrundlastTerm(f"speicher_leistung:{name}", sign))

    if grundlast_ok:
        specs.append(RoleSpec(GRUNDLAST_ROLE, GRUNDLAST_ENTITY, "HEMS Grundlast", "verbraucher", "leistung",
                              "W", source="hems"))
    else:
        terms = []
    return specs, terms, notes


def compute_grundlast(values: Dict[str, Dict[datetime, Any]], terms: List[GrundlastTerm],
                      slots: List[datetime]) -> Tuple[List[datetime], List[float], Optional[str]]:
    """Grundlast je Slot; Slots mit fehlenden oder lückenhaften Werten entfallen."""
    for role in ["hausverbrauch"] + [term.role for term in terms if term.needs_watt]:
        units = {value.unit for value in values.get(role, {}).values()}
        if units and units != {"W"}:
            return [], [], f"Rolle {role} hat die Einheit {', '.join(sorted(str(u) for u in units))}, erwartet W"
    times: List[datetime] = []
    results: List[float] = []
    for slot in slots:
        house = values.get("hausverbrauch", {}).get(slot)
        if house is None or house.mean is None or house.coverage_s < MIN_COVERAGE:
            continue
        total = house.mean
        complete = True
        for term in terms:
            value = values.get(term.role, {}).get(slot)
            if value is None or value.mean is None or value.coverage_s < MIN_COVERAGE:
                complete = False
                break
            total += term.sign * term.factor * value.mean
        if complete:
            times.append(slot)
            results.append(round(total, 1))
    return times, results, None


class InsightSync:
    """Zustand des Abgleichs. `tick` wird im Takt des Preis- und Prognosemoduls gerufen."""

    def __init__(self, options: Dict[str, Any], devices: List[Dict[str, Any]],
                 resolve_host: Callable[[], Any], clock: Callable[[], float] = time.monotonic,
                 database: str = "skytech") -> None:
        self.options = options
        self._database = database
        self.devices = devices
        self._resolve_host = resolve_host
        self._clock = clock
        self.client: Optional[InsightClient] = None
        self.status = SyncStatus(konfiguriert=bool(options.get("insight_password")))
        if not self.status.konfiguriert:
            self.status.grund = "Kein Passwort für Data Insight eingetragen"
        self._role_ids: Dict[str, int] = {}
        self._terms: List[GrundlastTerm] = []
        self._last_reconcile: Optional[float] = None
        self._price_signature: Optional[Tuple] = None
        self._pv_signature: Optional[Tuple] = None
        self._last_pv_run: Optional[float] = None

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()

    async def tick(self, now: datetime, states: Dict[str, Any],
                   price: Optional[PriceCurve], pv_curve: Optional[PvCurve],
                   pv_details: Dict[str, Optional[float]]) -> Dict[str, Any]:
        if not self.status.konfiguriert:
            return self.status.as_dict()
        try:
            await self._ensure_client()
            assert self.client is not None
            await self.client.connect()
            self.status.verbunden, self.status.grund = True, None
            if self._last_reconcile is None or self._clock() - self._last_reconcile >= RECONCILE_INTERVAL_S:
                await self._reconcile(states, now)
            await self._write_price_run(price, now)
            await self._write_pv_run(pv_curve, pv_details, now)
            await self._write_grundlast(now)
        except InsightError as exc:
            self.status.verbunden, self.status.grund = False, str(exc)
            log.warning("Data Insight: %s", exc)
        return self.status.as_dict()

    # ------------------------------------------------------------------

    async def _ensure_client(self) -> None:
        if self.client is not None:
            return
        host = self.options.get("insight_host") or "auto"
        if host == "auto":
            host = await self._resolve_host()
            if not host:
                raise InsightError("Skytech Data Insight ist nicht installiert oder nicht gefunden")
        self.status.host = host
        self.client = InsightClient(InsightSettings(
            host=host, port=int(self.options.get("insight_port") or 5432),
            password=str(self.options.get("insight_password") or ""), database=self._database))

    async def _reconcile(self, states: Dict[str, Any], now: datetime) -> None:
        assert self.client is not None
        specs, terms, notes = build_roles(self.options, self.devices, states)
        current = await self.client.current_assignments()
        managed = await self.client.managed_sensor_ids()
        role_ids: Dict[str, int] = {}
        for spec in specs:
            sensor_id = await self.client.ensure_sensor(spec.entity_id, None, spec.name, spec.category,
                                                        spec.quantity, spec.unit, spec.source)
            if current.get(spec.role, (None, None))[0] != sensor_id:
                await self.client.assign(spec.role, sensor_id)
            role_ids[spec.role] = sensor_id
        used = set(role_ids.values())
        for sensor_id, active in managed.items():
            if active and sensor_id not in used:
                await self.client.deactivate_sensor(sensor_id)
        self._role_ids, self._terms = role_ids, terms
        self._last_reconcile = self._clock()
        self.status.rollen = [{"rolle": spec.role, "entity": spec.entity_id, "sensor_id": role_ids[spec.role]}
                              for spec in specs]
        self.status.hinweise = notes
        self.status.letzter_abgleich = format_berlin(now, with_seconds=True)

    async def _write_price_run(self, price: Optional[PriceCurve], now: datetime) -> None:
        if price is None or not price.valid or not price.slots:
            return
        signature = tuple((slot.start, slot.price) for slot in price.slots)
        if signature == self._price_signature:
            return
        assert self.client is not None
        if self._price_signature is None:
            # Nach einem Neustart: steht genau diese Kurve schon in Data Insight, kein zweiter Lauf.
            stored = await self.client.price_values(price.slots[0].start, price.slots[-1].end)
            if all(abs(stored.get(slot.start, float("nan")) - slot.price) < 1e-9 for slot in price.slots):
                self._price_signature = signature
                return
        entity = self.options.get("tariff_price_entity") or ""
        await self.client.write_run(
            kind="preis", source=entity, created=now, raster_min=int(price.raster_min or 15),
            valid_from=price.slots[0].start, valid_until=price.slots[-1].end, unit="€/kWh", method=None,
            details={"entity": entity}, times=[slot.start for slot in price.slots],
            values=[slot.price for slot in price.slots])
        self._price_signature = signature
        self.status.letzter_preislauf = format_berlin(now, with_seconds=True)

    async def _write_pv_run(self, curve: Optional[PvCurve], details: Dict[str, Optional[float]],
                            now: datetime) -> None:
        if curve is None or not curve.valid or curve.raster_min != 15:
            return
        start = _floor_slot(now)
        slots = [slot for slot in curve.slots if start <= slot.start < start + PV_HORIZON]
        if not slots:
            return
        signature = tuple((slot.start, slot.watts, slot.p10, slot.p90) for slot in slots)
        since = None if self._last_pv_run is None else self._clock() - self._last_pv_run
        changed = signature != self._pv_signature
        if since is not None and (since < PV_RUN_MIN_GAP_S or (not changed and since < PV_RUN_INTERVAL_S)):
            return
        assert self.client is not None
        entity = self.options.get("pv_curve_entity") or ""
        await self.client.write_run(
            kind="pv", source=entity, created=now, raster_min=15, valid_from=slots[0].start,
            valid_until=slots[-1].start + SLOT, unit="W", method=None,
            details={"entity": entity, "ist_rolle": "pv_ist", "heute_kwh": details.get("heute"),
                     "morgen_kwh": details.get("morgen"), "rest_heute_kwh": details.get("rest_heute")},
            times=[slot.start for slot in slots], values=[slot.watts for slot in slots],
            p10=[slot.p10 for slot in slots], p90=[slot.p90 for slot in slots])
        self._pv_signature, self._last_pv_run = signature, self._clock()
        self.status.letzter_pv_lauf = format_berlin(now, with_seconds=True)

    async def _write_grundlast(self, now: datetime) -> None:
        sensor_id = self._role_ids.get(GRUNDLAST_ROLE)
        if sensor_id is None:
            self.status.grundlast_grund = "Grundlast nicht konfiguriert"
            return
        assert self.client is not None
        latest_start = _floor_slot(now - SLOT_DELAY) - SLOT
        last = await self.client.last_slot(GRUNDLAST_ROLE)
        if last is not None and self.status.grundlast_bis is None:
            self.status.grundlast_bis = format_berlin(last + SLOT)
        start = (last + SLOT) if last is not None else _floor_slot(now - MAX_BACKFILL)
        start = max(start, _floor_slot(now - MAX_BACKFILL))
        if start > latest_start:
            return
        roles = ["hausverbrauch"] + [term.role for term in self._terms]
        values = await self.client.role_values(roles, start, latest_start + SLOT)
        slots = []
        moment = start
        while moment <= latest_start:
            slots.append(moment)
            moment += SLOT
        times, results, reason = compute_grundlast(values, self._terms, slots)
        self.status.grundlast_grund = reason
        if times:
            await self.client.write_values(sensor_id, times, results)
            self.status.grundlast_bis = format_berlin(times[-1] + SLOT)
