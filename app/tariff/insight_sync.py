"""Abgleich mit Skytech Data Insight (D-065, Phasen P4 und P5; Vertrag 0.3).

Was hier entschieden wird – die Datenbank selbst spricht nur `insight_client`:

1. **Rollen:** welche HA-Sensoren das HEMS in Data Insight braucht, unter
   welcher Rolle. Fehlende werden angelegt, vorhandene übernommen, nicht mehr
   gebrauchte stillgelegt (Vertrag 0.3, „Verwaltete Sensoren“, „Rollen“).
   Leistungsrollen nur mit W, Zählerrollen nur mit kWh/Wh – sonst ein Hinweis.
2. **Preis- und PV-Läufe:** ein Preislauf, wenn sich die Kurve geändert hat; ein
   PV-Lauf stündlich oder bei geänderter Kurve, höchstens alle 15 min.
3. **Grundlast:** `hems.grundlast_w` je abgeschlossener Minute aus den in
   Data Insight aufgezeichneten Minutenwerten der Einzelsensoren. Dieselbe
   Rechnung füllt Lücken nach einem Ausfall (höchstens 10 Tage zurück). Der
   Fortschritt zählt nur echte Rohwerte, Data Insight führt hems.* nicht fort.

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
from tariff import load_forecast
from tariff.analysis import FREIGABE_ENTITY, MANUELL_ENTITY, battery_switch_entity
from tariff.load_forecast import LoadForecast
from tariff.price_source import PriceCurve, format_berlin
from tariff.pv_source import PvCurve

log = logging.getLogger(__name__)

SLOT = timedelta(minutes=15)
MINUTE = timedelta(minutes=1)
# Grundlast je Minute (Vertrag 0.3). Erst so lange nach Minutenende rechnen:
# Data Insight braucht die Minutenwerte der Einzelsensoren.
MINUTE_DELAY = timedelta(minutes=2)
MAX_BACKFILL = timedelta(days=10)
# Je Takt höchstens so viel nachrechnen; je Schreibaufruf ein Tag (Grenze 10 000 Werte).
BACKFILL_PER_TICK = timedelta(days=2)
WRITE_CHUNK = timedelta(days=1)
MIN_COVERAGE = 0.8 * MINUTE.total_seconds()
# Selbstheilung: so weit zurück nach fehlenden Grundlast-Minuten suchen, so oft.
HEAL_WINDOW = timedelta(hours=24)
HEAL_INTERVAL_S = 15 * 60
MIN_SLOT_COVERAGE = 0.8 * SLOT.total_seconds()
POWER_UNITS = ("W",)
ENERGY_UNITS = ("kWh", "Wh")
RECONCILE_INTERVAL_S = 15 * 60
PV_RUN_INTERVAL_S = 60 * 60
PV_RUN_MIN_GAP_S = 15 * 60
PV_HORIZON = timedelta(hours=48)
GRUNDLAST_ROLE = "grundlast"
GRUNDLAST_ENTITY = "hems.grundlast_w"
LOAD_RUN_INTERVAL_S = 60 * 60
ANALYSIS_RUN_INTERVAL_S = 60 * 60
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
    counter: bool = False


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
    letzter_verbrauchslauf: Optional[str] = None
    letzte_auswertung: Optional[str] = None
    grundlast_bis: Optional[str] = None
    grundlast_grund: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


def _floor_minute(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(second=0, microsecond=0)


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

    def add(role: str, entity: str, name: str, category: str, quantity: str,
            units: Tuple[str, ...] = (), counter: bool = False) -> bool:
        """Rolle aufnehmen; mit `units` nur bei passender Einheit (unbekannte Einheit wird nicht geprüft)."""
        if not entity:
            return False
        unit = _unit(states, entity)
        if units and unit is not None and unit not in units:
            notes.append(f"{role}: {entity} hat die Einheit {unit}, erwartet {' oder '.join(units)} – "
                         "Rolle nicht zugeordnet")
            return False
        specs.append(RoleSpec(role, entity, name, category, quantity, unit, counter=counter))
        return True

    house = options.get("tariff_house_load_entity") or ""
    house_ok = add("hausverbrauch", house, "HEMS Hausverbrauch", "verbraucher", "leistung", POWER_UNITS)
    add("pv_ist", options.get("pv_actual_entity") or "", "HEMS PV-Leistung", "pv", "leistung", POWER_UNITS)
    # Netzanschluss und Energiezähler (Vertrag 0.3): nur Datenerhebung.
    add("netz_leistung", options.get("tariff_grid_power_entity") or "", "HEMS Netzleistung", "netz", "leistung",
        POWER_UNITS)
    for role, key, name, category in (
            ("netz_bezug_energie", "tariff_grid_import_energy_entity", "HEMS Netzbezug Energie", "netz"),
            ("netz_einspeisung_energie", "tariff_grid_export_energy_entity", "HEMS Netzeinspeisung Energie", "netz"),
            ("pv_ist_energie", "pv_actual_energy_entity", "HEMS PV-Ertrag Energie", "pv"),
            ("hausverbrauch_energie", "tariff_house_load_energy_entity", "HEMS Hausverbrauch Energie",
             "verbraucher")):
        add(role, options.get(key) or "", name, category, "energie", ENERGY_UNITS, counter=True)
    add("preis", options.get("tariff_price_entity") or "", "HEMS Strompreis", "netz", "preis")
    add("pv_prognose_heute", options.get("pv_today_entity") or "", "HEMS PV-Prognose heute", "pv", "energie")
    add("pv_prognose_morgen", options.get("pv_tomorrow_entity") or "", "HEMS PV-Prognose morgen", "pv", "energie")
    add("pv_prognose_rest_heute", options.get("pv_today_remaining_entity") or "",
        "HEMS PV-Prognose Rest heute", "pv", "energie")

    grundlast_ok = house_ok
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
            if not add(f"verbraucher_ist:{name}", device.get("actual_power_entity") or "",
                       f"HEMS {label} Istleistung", "verbraucher", "leistung", POWER_UNITS):
                grundlast_ok = False
            terms.append(GrundlastTerm(f"verbraucher_ist:{name}", -1.0))
        elif cls == "binary":
            if device.get("power_actual_entity"):
                if not add(f"verbraucher_ist:{name}", device["power_actual_entity"],
                           f"HEMS {label} Istleistung", "verbraucher", "leistung", POWER_UNITS):
                    grundlast_ok = False
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
            power_ok = bool(power_entity) and add(f"speicher_leistung:{name}", power_entity, f"HEMS {label} Leistung",
                                                  "speicher", "leistung", POWER_UNITS)
            add(f"speicher_laden_energie:{name}", device.get("tariff_charge_energy_entity") or "",
                f"HEMS {label} Laden Energie", "speicher", "energie", ENERGY_UNITS, counter=True)
            add(f"speicher_entladen_energie:{name}", device.get("tariff_discharge_energy_entity") or "",
                f"HEMS {label} Entladen Energie", "speicher", "energie", ENERGY_UNITS, counter=True)
            if device.get("tariff_in_house_load") and power_entity and not power_ok:
                grundlast_ok = False
            if device.get("tariff_in_house_load"):
                if not power_entity:
                    notes.append(f"Speicher {name}: getrennte Lade-/Entladesensoren werden für die Grundlast "
                                 "noch nicht unterstützt")
                    grundlast_ok = False
                else:
                    sign = -1.0 if (device.get("power_sign") or "positiv_laden") == "positiv_laden" else 1.0
                    terms.append(GrundlastTerm(f"speicher_leistung:{name}", sign))

    # Schalter des Netzladens (Phase P5): nur, wenn es die Helfer in HA gibt.
    for role, entity, name in (("schalter_netzladen_freigabe", FREIGABE_ENTITY, "HEMS Netzladen Freigabe"),
                               ("schalter_netzladen_manuell", MANUELL_ENTITY, "HEMS Netzladen manuell")):
        if entity in states:
            specs.append(RoleSpec(role, entity, name, "sonstiges", "zustand", None))
    batteries = [device for device in devices if device.get("class") == "battery"
                 and _ROLE_SUFFIX_RE.match(device.get("name") or "")]
    for device in batteries:
        entity = battery_switch_entity(device.get("entity_prefix") or device["name"])
        if entity in states:
            specs.append(RoleSpec(f"schalter_netzladen_erlaubt:{device['name']}", entity,
                                  f"HEMS {device.get('label') or device['name']} Netzladen erlaubt",
                                  "sonstiges", "zustand", None))

    # Eigene Reihen des HEMS (Vertrag „HEMS-eigene Messreihen“).
    if grundlast_ok:
        specs.append(RoleSpec(GRUNDLAST_ROLE, GRUNDLAST_ENTITY, "HEMS Grundlast", "verbraucher", "leistung",
                              "W", source="hems"))
    else:
        terms = []
    specs.append(RoleSpec("nutzbar", "hems.nutzbar_kwh", "HEMS Speicher nutzbar", "speicher", "energie",
                          "kWh", source="hems"))
    specs.append(RoleSpec("reichweite", "hems.reichweite_h", "HEMS Speicher Reichweite", "speicher", "sonstiges",
                          "h", source="hems"))
    specs.append(RoleSpec("netzladen_zulaessig", "hems.netzladen_zulaessig", "HEMS Netzladen zulässig",
                          "sonstiges", "zustand", None, source="hems"))
    for device in batteries:
        specs.append(RoleSpec(f"netzladen_zulaessig:{device['name']}", f"hems.netzladen_zulaessig_{device['name']}",
                              f"HEMS {device.get('label') or device['name']} Netzladen zulässig",
                              "sonstiges", "zustand", None, source="hems"))
    return specs, terms, notes


def series_samples(analysis: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Momentanwerte der eigenen Reihen aus der Auswertung; None = kein Wert."""
    speicher = analysis.get("speicher") or {}
    kennzahlen = analysis.get("kennzahlen") or {}
    netz = analysis.get("netzladen") or {}
    samples: Dict[str, Optional[float]] = {
        "nutzbar": speicher.get("nutzbar_kwh"),
        "reichweite": kennzahlen.get("reichweite_h"),
        "netzladen_zulaessig": 1.0 if netz.get("zulaessig") else 0.0,
    }
    for entry in netz.get("je_speicher") or []:
        samples[f"netzladen_zulaessig:{entry['name']}"] = 1.0 if entry.get("zulaessig") else 0.0
    return samples


def compute_grundlast(values: Dict[str, Dict[datetime, Any]], terms: List[GrundlastTerm],
                      slots: List[datetime]) -> Tuple[List[datetime], List[float], Optional[str]]:
    """Grundlast je Minute; Minuten mit fehlenden oder lückenhaften Werten (< 48 s) entfallen.

    Ebenso Minuten, in denen der Hausverbrauch keinen einzigen Rohwert hatte (`count == 0`): Der
    Sensor meldet im Betrieb alle paar Sekunden; ohne Meldung war die Aufzeichnung unterbrochen,
    und die Werte sind nur fortgeführt (Referenzanlage 13.10.2026: 5635 W statt rund 2800 W).
    """
    for role in ["hausverbrauch"] + [term.role for term in terms if term.needs_watt]:
        units = {value.unit for value in values.get(role, {}).values()}
        if units and units != {"W"}:
            return [], [], f"Rolle {role} hat die Einheit {', '.join(sorted(str(u) for u in units))}, erwartet W"
    times: List[datetime] = []
    results: List[float] = []
    for slot in slots:
        house = values.get("hausverbrauch", {}).get(slot)
        if house is None or house.mean is None or house.coverage_s < MIN_COVERAGE or house.count == 0:
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
        self.load_forecast: Optional[LoadForecast] = None
        self.load_reason: Optional[str] = ("Ohne Data Insight keine Verbrauchsprognose"
                                           if not self.status.konfiguriert else "Noch keine Prognose")
        self._last_load_run: Optional[float] = None
        self._last_analysis_run: Optional[float] = None
        self._runs_this_tick = False
        self._last_series_minute: Optional[datetime] = None
        self._grundlast_from: Optional[datetime] = None
        self._last_heal: Optional[float] = None

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
            self._runs_this_tick = False
            await self._write_price_run(price, now)
            await self._write_pv_run(pv_curve, pv_details, now)
            await self._write_grundlast(now)
            await self._heal_grundlast(now)
            await self._refresh_load_forecast(now)
        except InsightError as exc:
            self.status.verbunden, self.status.grund = False, str(exc)
            if self.load_forecast is None:
                self.load_reason = f"Data Insight nicht verbunden: {exc}"
            log.warning("Data Insight: %s", exc)
        return self.status.as_dict()

    async def record(self, now: datetime, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Eigene Reihen je Minute und Auswertungslauf schreiben. Wirft nie."""
        if not self.status.konfiguriert or not self.status.verbunden or self.client is None:
            return self.status.as_dict()
        try:
            await self._record_series(now, analysis)
            await self._write_analysis_run(now, analysis)
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
                                                        spec.quantity, spec.unit, spec.source, spec.counter)
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
        self._runs_this_tick = True
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
        self._runs_this_tick = True
        self.status.letzter_pv_lauf = format_berlin(now, with_seconds=True)

    async def _write_grundlast(self, now: datetime) -> None:
        sensor_id = self._role_ids.get(GRUNDLAST_ROLE)
        if sensor_id is None:
            self.status.grundlast_grund = "Grundlast nicht konfiguriert"
            return
        assert self.client is not None
        # Letzte vollständig verfügbare Minute: ihr Ende liegt mindestens MINUTE_DELAY zurück.
        end = _floor_minute(now - MINUTE_DELAY)
        if self._grundlast_from is None:
            # Fortschritt nur aus echten Rohwerten (anzahl > 0), nie aus fortgeführten Minuten.
            last = await self.client.last_minute(GRUNDLAST_ROLE)
            if last is not None:
                self.status.grundlast_bis = format_berlin(last + MINUTE)
            self._grundlast_from = (last + MINUTE) if last is not None else _floor_minute(now - MAX_BACKFILL)
        start = max(self._grundlast_from, _floor_minute(now - MAX_BACKFILL))
        stop = min(end, start + BACKFILL_PER_TICK)
        roles = ["hausverbrauch"] + [term.role for term in self._terms]
        chunk = start
        while chunk < stop:
            chunk_end = min(chunk + WRITE_CHUNK, stop)
            values = await self.client.role_values(roles, chunk, chunk_end, minutes=True)
            minutes = []
            moment = chunk
            while moment < chunk_end:
                minutes.append(moment)
                moment += MINUTE
            times, results, reason = compute_grundlast(values, self._terms, minutes)
            self.status.grundlast_grund = reason
            if times:
                await self.client.write_values(sensor_id, times, results)
                self.status.grundlast_bis = format_berlin(times[-1] + MINUTE)
            chunk = chunk_end
        # Auch Minuten ohne Ergebnis gelten als bearbeitet – sonst hinge der Fortschritt an einer Lücke.
        # Die jüngsten Minuten bleiben offen: die Einzelsensoren können noch nachgeliefert werden.
        self._grundlast_from = max(start, stop - MINUTE_DELAY)

    async def _heal_grundlast(self, now: datetime) -> None:
        """Fehlende Grundlast-Minuten der letzten 24 h nachrechnen.

        Fehlten die Quellwerte beim ersten Versuch (Data Insight neu gestartet, Lücke erst später
        aus dem HA-Verlauf nachgeladen), entfiel die Minute. Ist sie jetzt vollständig, wird sie
        hier geschrieben; vorhandene Minuten verwirft die Datenbank als Duplikat.
        """
        sensor_id = self._role_ids.get(GRUNDLAST_ROLE)
        if sensor_id is None or self._grundlast_from is None:
            return
        if self._last_heal is not None and self._clock() - self._last_heal < HEAL_INTERVAL_S:
            return
        self._last_heal = self._clock()
        assert self.client is not None
        end = self._grundlast_from
        start = max(_floor_minute(now - HEAL_WINDOW), end - HEAL_WINDOW)
        if start >= end:
            return
        roles = [GRUNDLAST_ROLE, "hausverbrauch"] + [term.role for term in self._terms]
        values = await self.client.role_values(roles, start, end, minutes=True)
        present = {moment for moment, value in values.get(GRUNDLAST_ROLE, {}).items()
                   if value.count is None or value.count > 0}
        missing = []
        moment = start
        while moment < end:
            if moment not in present:
                missing.append(moment)
            moment += MINUTE
        times, results, _ = compute_grundlast(values, self._terms, missing)
        if times:
            written = await self.client.write_values(sensor_id, times, results)
            if written:
                log.info("Grundlast: %d fehlende Minuten nachgerechnet.", written)

    # ------------------------------------------------------------------
    # Phase P5: Verbrauchsprognose, eigene Reihen, Auswertungslauf
    # ------------------------------------------------------------------

    async def _refresh_load_forecast(self, now: datetime) -> None:
        if self._last_load_run is not None and self._clock() - self._last_load_run < LOAD_RUN_INTERVAL_S:
            return
        assert self.client is not None
        values = await self.client.role_values([GRUNDLAST_ROLE], now - load_forecast.HISTORY, now)
        history = {slot: value.mean for slot, value in values.get(GRUNDLAST_ROLE, {}).items()
                   if value.mean is not None and value.coverage_s >= MIN_SLOT_COVERAGE}
        result = load_forecast.forecast(history, now)
        self.load_forecast, self.load_reason = result, result.reason
        self._last_load_run = self._clock()
        if not result.valid:
            return
        await self.client.write_run(
            kind="verbrauch", source=f"hems:{load_forecast.METHOD}", created=now, raster_min=15,
            valid_from=result.slots[0].start, valid_until=result.slots[-1].start + SLOT, unit="W",
            method=load_forecast.METHOD,
            details={"ist_rolle": GRUNDLAST_ROLE, "historie_tage": result.history_days,
                     "parameter": load_forecast.PARAMETERS},
            times=[slot.start for slot in result.slots], values=[slot.p50 for slot in result.slots],
            p10=[slot.p10 for slot in result.slots], p90=[slot.p90 for slot in result.slots])
        self._runs_this_tick = True
        self.status.letzter_verbrauchslauf = format_berlin(now, with_seconds=True)

    async def _record_series(self, now: datetime, analysis: Dict[str, Any]) -> None:
        """Momentanwert je Takt (60 s) zum Minutenbeginn (Vertrag 0.3); fehlende Takte bleiben Lücken."""
        minute = _floor_minute(now)
        if minute == self._last_series_minute:
            return
        assert self.client is not None
        for role, value in series_samples(analysis).items():
            sensor_id = self._role_ids.get(role)
            if sensor_id is not None and value is not None:
                await self.client.write_values(sensor_id, [minute], [round(float(value), 3)])
        self._last_series_minute = minute

    async def _write_analysis_run(self, now: datetime, analysis: Dict[str, Any]) -> None:
        figures = analysis.get("kennzahlen") or {}
        speicher = analysis.get("speicher") or {}
        if not figures:
            return
        due = (self._last_analysis_run is None or self._runs_this_tick
               or self._clock() - self._last_analysis_run >= ANALYSIS_RUN_INTERVAL_S)
        if not due:
            return
        assert self.client is not None
        median = speicher.get("median") or {}
        details = {
            **figures,
            "nutzbar_kwh": speicher.get("nutzbar_kwh"),
            "reichweite_bis": {key: (speicher.get(key) or {}).get("bis_iso")
                               for key in ("median", "vorsichtig", "zuversichtlich")},
            "netzladen_zulaessig": (analysis.get("netzladen") or {}).get("zulaessig"),
        }
        start = _floor_slot(now)
        horizon = median.get("horizont_bis_iso")
        end = datetime.fromisoformat(horizon) if horizon else start + timedelta(hours=48)
        await self.client.write_run(
            kind="auswertung", source="hems:kennzahlen", created=now, raster_min=15,
            valid_from=start, valid_until=max(end, start + SLOT), unit="kWh", method="kennzahlen_v1",
            details=details, times=[], values=[])
        self._last_analysis_run = self._clock()
        self.status.letzte_auswertung = format_berlin(now, with_seconds=True)
