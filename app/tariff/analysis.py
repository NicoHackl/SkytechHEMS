"""Reichweite, Kennzahlen und Netzlade-Freigabe (D-065, Phase P5) – reine Anzeige.

Alles hier ist Datenerhebung für die spätere Steuerung (Plan §12). Es schaltet
nichts und fließt in keine Regelentscheidung ein.

* **Speicher:** SoC, Grenzen und Ladeleistung kommen aus dem Status des letzten
  Regelzyklus, Kapazität und Wirkungsgrade aus der Gerätekonfiguration.
* **Reichweite:** Vorausrechnung je 15-min-Slot: Defizit (Grundlast − PV)
  entlädt, Überschuss lädt (bis voll). Dreimal gerechnet: Median, vorsichtig
  (Verbrauch p90, PV p10) und zuversichtlich (Verbrauch p10, PV p90). Alle
  Speicher zählen als ein Gesamtspeicher; Laden höchstens mit der Summe ihrer
  Ladeleistungen.
* **Netzladen zulässig** = Freigabe UND (Manuell ODER PV zu wenig); je Speicher
  zusätzlich dessen Schalter. „PV zu wenig“ ist bis zur Entscheidung über die
  Steuerungslogik immer unbekannt und damit falsch (Plan E-18).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from tariff.load_forecast import SLOT, LoadForecast
from tariff.price_source import PriceCurve, PriceSlot, end_of_tomorrow, format_berlin, upcoming
from tariff.pv_source import PvCurve

FREIGABE_ENTITY = "input_boolean.ems_netzladen_freigabe"
MANUELL_ENTITY = "input_boolean.ems_netzladen_manuell"
DEFAULT_EFFICIENCY = 0.92


def battery_switch_entity(prefix: str) -> str:
    return f"input_boolean.ems_{prefix}_netzladen_erlaubt"


@dataclass(frozen=True)
class BatteryInfo:
    name: str
    label: str
    prefix: str
    valid: bool
    reason: Optional[str]
    soc: float = 0.0
    soc_min: float = 0.0
    soc_max: float = 100.0
    capacity_kwh: float = 0.0
    charge_kw: float = 0.0
    eta_charge: float = DEFAULT_EFFICIENCY
    eta_discharge: float = DEFAULT_EFFICIENCY

    @property
    def usable_kwh(self) -> float:
        return max(self.soc - self.soc_min, 0.0) / 100 * self.capacity_kwh * self.eta_discharge

    @property
    def usable_max_kwh(self) -> float:
        return max(self.soc_max - self.soc_min, 0.0) / 100 * self.capacity_kwh * self.eta_discharge


def batteries_from(cycle_status: Dict[str, Any], devices: List[Dict[str, Any]]) -> List[BatteryInfo]:
    """Speicher aus dem Zyklusstatus und der Gerätekonfiguration."""
    config = {device.get("name"): device for device in devices if device.get("class") == "battery"}
    result: List[BatteryInfo] = []
    for entry in (cycle_status or {}).get("devices") or []:
        if entry.get("type") != "battery":
            continue
        name = entry.get("id") or ""
        device = config.get(name, {})
        label = entry.get("label") or name
        prefix = entry.get("entity_prefix") or name
        capacity = float(device.get("capacity_kwh") or entry.get("capacity_kwh") or 0.0)
        if capacity <= 0:
            result.append(BatteryInfo(name, label, prefix, False, "Kapazität nicht konfiguriert (capacity_kwh)"))
            continue
        if not entry.get("sensoren_gueltig", True):
            result.append(BatteryInfo(name, label, prefix, False, "SoC oder Leistung ungültig"))
            continue
        result.append(BatteryInfo(
            name, label, prefix, True, None,
            soc=float(entry.get("soc_prozent") or 0.0),
            soc_min=float(entry.get("soc_min_prozent") or 0.0),
            soc_max=float(entry.get("soc_max_prozent") or 100.0),
            capacity_kwh=capacity,
            charge_kw=float(entry.get("max_ladeleistung_w") or 0.0) / 1000,
            eta_charge=float(device.get("tariff_efficiency_charge") or DEFAULT_EFFICIENCY),
            eta_discharge=float(device.get("tariff_efficiency_discharge") or DEFAULT_EFFICIENCY),
        ))
    return result


def _switch(states: Dict[str, Any], entity: str) -> Tuple[bool, bool]:
    """(an, vorhanden). Fehlt der Helfer oder ist er nicht auswertbar: aus."""
    state = states.get(entity)
    if state is None:
        return False, False
    return str(state.get("state")) == "on", True


# ---------------------------------------------------------------------------
# Reichweite
# ---------------------------------------------------------------------------

def _pv_watts(curve: Optional[PvCurve], moment: datetime, attr: str) -> Optional[float]:
    if curve is None or not curve.valid or curve.raster_min is None:
        return None
    step = timedelta(minutes=curve.raster_min)
    for slot in curve.slots:
        if slot.start <= moment < slot.start + step:
            value = getattr(slot, attr) if attr != "watts" else slot.watts
            return slot.watts if value is None else value
    return None


@dataclass
class Reach:
    until: Optional[datetime]      # None = reicht über den Horizont
    horizon_end: datetime
    pv_kwh: float                  # PV-Prognose von jetzt bis `until` bzw. Horizontende
    deficit_after_kwh: float       # Netzbezug nach dem Leerlaufen bis zum nächsten Überschuss
    next_surplus: Optional[datetime]


def simulate(now: datetime, start_kwh: float, max_kwh: float, eta_in: float, load: LoadForecast,
             pv: Optional[PvCurve], load_attr: str = "p50", pv_attr: str = "watts",
             charge_kw: Optional[float] = None) -> Optional[Reach]:
    """Vorausrechnung des Gesamtspeichers; None, wenn keine Prognose vorliegt."""
    if not load.valid or not load.slots:
        return None
    energy = start_kwh
    until: Optional[datetime] = None
    pv_kwh = 0.0
    deficit_after = 0.0
    next_surplus: Optional[datetime] = None
    horizon_end = load.slots[-1].start + SLOT
    simulated = False
    for slot in load.slots:
        begin = max(slot.start, now)
        hours = (slot.start + SLOT - begin).total_seconds() / 3600
        if hours <= 0:
            continue
        pv_w = _pv_watts(pv, slot.start, pv_attr)
        if pv_w is None:
            horizon_end = slot.start
            break
        simulated = True
        load_w = getattr(slot, load_attr)
        net_kwh = (load_w - pv_w) * hours / 1000
        if until is None:
            pv_kwh += pv_w * hours / 1000
            if net_kwh > 0:
                if energy - net_kwh < 0:
                    until = begin + timedelta(hours=hours * energy / net_kwh) if net_kwh else begin
                    deficit_after += net_kwh - energy
                    energy = 0.0
                else:
                    energy -= net_kwh
            else:
                surplus_kwh = -net_kwh if charge_kw is None else min(-net_kwh, charge_kw * hours)
                energy = min(max_kwh, energy + surplus_kwh * eta_in)
        else:
            if net_kwh < 0:
                next_surplus = slot.start
                break
            deficit_after += net_kwh
    if not simulated:
        return None
    return Reach(until, horizon_end, round(pv_kwh, 2), round(deficit_after, 2), next_surplus)


def first_surplus(now: datetime, load: LoadForecast, pv: Optional[PvCurve]) -> Optional[datetime]:
    for slot in load.slots:
        if slot.start + SLOT <= now:
            continue
        pv_w = _pv_watts(pv, slot.start, "watts")
        if pv_w is not None and pv_w > slot.p50:
            return slot.start
    return None


# ---------------------------------------------------------------------------
# Preisfenster
# ---------------------------------------------------------------------------

def cheapest_block(slots: List[PriceSlot], count: int, until: Optional[datetime]) -> Optional[Dict[str, Any]]:
    """Günstigster zusammenhängender Block aus `count` Slots, der vor `until` endet."""
    candidates = [slot for slot in slots if until is None or slot.end <= until]
    if count <= 0 or len(candidates) < count:
        return None
    best: Optional[Tuple[float, int]] = None
    for index in range(len(candidates) - count + 1):
        block = candidates[index:index + count]
        if any(block[i].end != block[i + 1].start for i in range(count - 1)):
            continue
        mean = sum(slot.price for slot in block) / count
        if best is None or mean < best[0]:
            best = (mean, index)
    if best is None:
        return None
    block = candidates[best[1]:best[1] + count]
    return {"von": format_berlin(block[0].start), "bis": format_berlin(block[-1].end),
            "von_iso": block[0].start.isoformat(), "bis_iso": block[-1].end.isoformat(),
            "slots": count, "preis_mittel": round(best[0], 5)}


# ---------------------------------------------------------------------------
# Gesamtauswertung
# ---------------------------------------------------------------------------

def _iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.isoformat() if moment else None


def _text(moment: Optional[datetime]) -> Optional[str]:
    return format_berlin(moment) if moment else None


def analyse(now: datetime, *, cycle_status: Dict[str, Any], devices: List[Dict[str, Any]],
            states: Dict[str, Any], price: Optional[PriceCurve], pv: Optional[PvCurve],
            load: Optional[LoadForecast], load_reason: Optional[str]) -> Dict[str, Any]:
    """Alle Anzeigen von Phase P5 als ein Objekt (Teil von `api/tariff/status`)."""
    batteries = batteries_from(cycle_status, devices)
    valid_batteries = [battery for battery in batteries if battery.valid]
    usable = sum(battery.usable_kwh for battery in valid_batteries)
    usable_max = sum(battery.usable_max_kwh for battery in valid_batteries)
    capacity = sum(battery.capacity_kwh for battery in valid_batteries)
    eta_in = (sum(battery.eta_charge * battery.eta_discharge * battery.capacity_kwh for battery in valid_batteries)
              / capacity) if capacity else DEFAULT_EFFICIENCY ** 2
    charge_kw = sum(battery.charge_kw for battery in valid_batteries)

    # Verbrauchsprognose
    load_view: Dict[str, Any] = {"gueltig": bool(load and load.valid), "grund": load_reason}
    if load is not None:
        load_view.update({"methode": "profil_v1", "historie_tage": load.history_days,
                          "erstellt": _text(load.created)})
        if load.valid:
            until_tomorrow = end_of_tomorrow(now)
            load_view.update({
                "bis_ende_morgen_kwh": round(load.energy_kwh(now, until_tomorrow), 2),
                "naechste_24h_kwh": round(load.energy_kwh(now, now + timedelta(hours=24)), 2),
                "naechste_24h_p10_kwh": round(load.energy_kwh(now, now + timedelta(hours=24), "p10"), 2),
                "naechste_24h_p90_kwh": round(load.energy_kwh(now, now + timedelta(hours=24), "p90"), 2),
                "aktuell_w": (current.p50 if (current := load.slot_at(now)) else None),
            })
            load_view["grund"] = None

    # Reichweite
    reach_view: Dict[str, Any] = {
        "nutzbar_kwh": round(usable, 2), "nutzbar_max_kwh": round(usable_max, 2),
        "je_speicher": [{"name": b.name, "label": b.label, "gueltig": b.valid, "grund": b.reason,
                         "soc_prozent": b.soc if b.valid else None,
                         "nutzbar_kwh": round(b.usable_kwh, 2) if b.valid else None,
                         "ladeleistung_kw": round(b.charge_kw, 2) if b.valid else None}
                        for b in batteries],
    }
    reaches: Dict[str, Optional[Reach]] = {}
    if load is not None and load.valid and pv is not None and pv.valid and valid_batteries:
        reaches = {
            "median": simulate(now, usable, usable_max, eta_in, load, pv, "p50", "watts", charge_kw),
            "vorsichtig": simulate(now, usable, usable_max, eta_in, load, pv, "p90", "p10", charge_kw),
            "zuversichtlich": simulate(now, usable, usable_max, eta_in, load, pv, "p10", "p90", charge_kw),
        }
    for key, reach in reaches.items():
        reach_view[key] = None if reach is None else {
            "bis": _text(reach.until), "bis_iso": _iso(reach.until),
            "ueber_horizont": reach.until is None, "horizont_bis": _text(reach.horizon_end),
            "horizont_bis_iso": _iso(reach.horizon_end),
        }
    median = reaches.get("median")
    if not valid_batteries:
        reach_view["grund"] = "Kein Speicher mit Kapazität und gültigen Messwerten"
    elif load is None or not load.valid:
        reach_view["grund"] = "Ohne Verbrauchsprognose keine Reichweite"
    elif pv is None or not pv.valid:
        reach_view["grund"] = "Ohne PV-Prognose keine Reichweite"
    elif median is None:
        reach_view["grund"] = "Keine Vorausrechnung möglich"
    else:
        reach_view["grund"] = None

    # Kennzahlen (Plan 5.7)
    figures: Dict[str, Any] = {}
    coming = upcoming(price, now) if price is not None and price.valid else []
    if median is not None:
        limit = median.until or median.horizon_end
        surplus = first_surplus(now, load, pv) if load is not None else None
        hours_needed = (median.deficit_after_kwh / charge_kw) if charge_kw > 0 else None
        raster_h = (price.raster_min / 60) if price is not None and price.valid and price.raster_min else 0.25
        block = max(1, math.ceil(hours_needed / raster_h)) if hours_needed else 1
        figures = {
            "reichweite_h": (round((median.until - now).total_seconds() / 3600, 2) if median.until else None),
            "pv_im_fenster_kwh": median.pv_kwh,
            "defizit_bis_pv_kwh": median.deficit_after_kwh,
            "naechster_ueberschuss_ab": _text(surplus), "naechster_ueberschuss_ab_iso": _iso(surplus),
            "ladeblock_slots": block,
            "guenstigstes_fenster_reichweite": cheapest_block(coming, block, limit) if coming else None,
            "guenstigstes_fenster_gesamt": cheapest_block(coming, block, None) if coming else None,
            "horizont_reicht": bool(coming and coming[-1].end >= limit),
        }
    if coming and price is not None and price.current is not None:
        cheaper = sum(1 for slot in coming if slot.price < price.current.price)
        figures["preis_rang_jetzt_prozent"] = round(100 * cheaper / max(len(coming) - 1, 1), 1)

    # Netzlade-Freigabe
    freigabe, freigabe_da = _switch(states, FREIGABE_ENTITY)
    manuell, manuell_da = _switch(states, MANUELL_ENTITY)
    pv_too_low: Optional[bool] = None
    allowed = freigabe and (manuell or bool(pv_too_low))
    if not freigabe:
        reason = "Netzladesystem nicht freigegeben" + ("" if freigabe_da else " (Helfer fehlt)")
    elif not allowed:
        reason = "Weder manuell angefordert noch PV-Kriterium erfüllt (Kriterium noch offen)"
    else:
        reason = "Manuell angefordert"
    per_battery = []
    for battery in batteries:
        entity = battery_switch_entity(battery.prefix)
        erlaubt, vorhanden = _switch(states, entity)
        per_battery.append({"name": battery.name, "label": battery.label, "entity": entity,
                            "erlaubt": erlaubt, "vorhanden": vorhanden, "zulaessig": allowed and erlaubt})
    grid_view = {
        "zulaessig": allowed, "grund": reason,
        "freigabe": freigabe, "freigabe_vorhanden": freigabe_da, "freigabe_entity": FREIGABE_ENTITY,
        "manuell": manuell, "manuell_vorhanden": manuell_da, "manuell_entity": MANUELL_ENTITY,
        "pv_zu_wenig": pv_too_low, "je_speicher": per_battery,
    }
    return {"verbrauch": load_view, "speicher": reach_view, "kennzahlen": figures, "netzladen": grid_view}
