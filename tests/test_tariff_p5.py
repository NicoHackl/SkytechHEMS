"""Dynamischer Strompreis, Phase P5 (D-065): Verbrauchsprognose, Reichweite,
Kennzahlen, Netzlade-Freigabe und deren Speicherung in Data Insight.

Alles hier ist reine Anzeige; geprüft wird Rechnung und Datenfluss, keine Regelung.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from insight_client import RoleValue
from configuration import normalize_options, validate_options
from tariff import analysis, load_forecast
from tariff.analysis import analyse, batteries_from, cheapest_block, simulate
from tariff.load_forecast import LoadForecast, LoadSlot, day_type, forecast, weighted_quantile
from tariff.price_source import BERLIN, parse_price_curve, upcoming
from tariff.pv_source import parse_pv_curve
from tariff_publisher import build_states

from test_insight import DEVICES, STATES, _sync
from test_tariff import NOW, price_state, pv_curve_state

UTC = timezone.utc
SLOT = timedelta(minutes=15)


def _history(now, days, value=lambda slot: 1000.0):
    start = load_forecast.floor_slot(now) - timedelta(days=days)
    result, moment = {}, start
    while moment < now:
        result[moment] = value(moment)
        moment += SLOT
    return result


def _flat_load(now, watts=1000.0, hours=48):
    first = load_forecast.floor_slot(now)
    return LoadForecast(True, created=now, history_days=14,
                        slots=[LoadSlot(first + SLOT * i, watts, watts * 0.8, watts * 1.2)
                               for i in range(hours * 4)])


# ---------------------------------------------------------------------------
# Verbrauchsprognose profil_v1
# ---------------------------------------------------------------------------

def test_weighted_quantile():
    assert weighted_quantile([(1, 1), (2, 1), (3, 1)], 0.5) == 2
    assert weighted_quantile([(1, 1), (10, 3)], 0.5) == pytest.approx(7.75)
    assert weighted_quantile([(5, 1)], 0.9) == 5


def test_forecast_needs_seven_days_of_history():
    history = {datetime(2026, 10, day, 10, 0, tzinfo=UTC): 500.0 for day in range(6, 12)}
    result = forecast(history, NOW)
    assert not result.valid and result.reason == "Historie zu kurz (6 von 7 Tagen)" and result.slots == []


def test_forecast_uses_day_types():
    now = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)          # Freitag
    history = _history(now, 21, lambda slot: 800.0 if day_type(slot) != "werktag" else 400.0)
    result = forecast(history, now)
    assert result.valid and result.history_days >= 21 and len(result.slots) == 192
    assert result.slots[0].start == now
    assert result.slot_at(datetime(2026, 10, 16, 15, 0, tzinfo=UTC)).p50 == 400.0
    assert result.slot_at(datetime(2026, 10, 17, 15, 0, tzinfo=UTC)).p50 == 800.0
    assert result.energy_kwh(now, now + timedelta(hours=2)) == pytest.approx(0.8)


def test_forecast_is_keyed_by_local_time_across_dst_change():
    now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)          # Zeitumstellung am 25.10.2026
    history = _history(now, 14, lambda slot: slot.astimezone(BERLIN).hour * 100.0)
    result = forecast(history, now)
    assert len(result.slots) == 192                          # 48 h über Zeitstempel, nicht über Slotnummern
    # 02:30 Sommerzeit und 02:30 Winterzeit bekommen denselben Wert.
    assert result.slot_at(datetime(2026, 10, 25, 0, 30, tzinfo=UTC)).p50 == 200.0
    assert result.slot_at(datetime(2026, 10, 25, 1, 30, tzinfo=UTC)).p50 == 200.0


# ---------------------------------------------------------------------------
# Speicher, Reichweite, Preisfenster
# ---------------------------------------------------------------------------

CYCLE = {"devices": [
    {"type": "battery", "id": "acspeicher1", "label": "AC Speicher 1", "entity_prefix": "acspeicher1",
     "sensoren_gueltig": True, "soc_prozent": 50.0, "soc_min_prozent": 10.0, "soc_max_prozent": 100.0,
     "capacity_kwh": 10.0, "max_ladeleistung_w": 5000},
    {"type": "battery", "id": "e3dc_speicher", "label": "E3DC", "entity_prefix": "e3dc_speicher",
     "sensoren_gueltig": True, "soc_prozent": 80.0, "capacity_kwh": 0},
    {"type": "controllable", "id": "heizstab"},
]}


def test_batteries_from_cycle_status_and_config():
    batteries = batteries_from(CYCLE, DEVICES)
    assert [battery.name for battery in batteries] == ["acspeicher1", "e3dc_speicher"]
    ac, e3dc = batteries
    assert ac.valid and ac.usable_kwh == pytest.approx(0.4 * 10 * 0.92) and ac.charge_kw == 5.0
    assert ac.usable_max_kwh == pytest.approx(0.9 * 10 * 0.92)
    assert not e3dc.valid and "Kapazität" in e3dc.reason


def test_simulation_reach_deficit_and_next_surplus():
    pv = parse_pv_curve(pv_curve_state(), "forecast", NOW)
    reach = simulate(NOW, 3.68, 8.28, 0.85, _flat_load(NOW), pv)
    # 1000 W Grundlast, nachts keine PV: 3,68 kWh reichen 3,68 h.
    assert reach.until == NOW + timedelta(hours=3.68)
    assert reach.pv_kwh == 0.0
    # Danach Netzbezug bis 10:00 Berliner Zeit, dann Überschuss.
    assert reach.next_surplus == datetime(2026, 10, 13, 8, 0, tzinfo=UTC)
    gap = (reach.next_surplus - reach.until).total_seconds() / 3600
    assert reach.deficit_after_kwh == pytest.approx(gap, abs=0.01)


def test_simulation_charges_on_surplus_and_reaches_beyond_horizon():
    now = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)            # 10:00, PV 4000 W
    pv = parse_pv_curve(pv_curve_state(), "forecast", now)
    reach = simulate(now, 1.0, 50.0, 0.85, _flat_load(now, 200.0), pv)
    assert reach.until is None and reach.horizon_end == now + timedelta(hours=48)
    assert reach.pv_kwh > 0
    assert simulate(now, 1.0, 50.0, 0.85, LoadForecast(False), pv) is None
    # Ladeleistung begrenzt: 3,8 kW Überschuss eine Viertelstunde lang, danach 1 kW Last ohne PV.
    evening = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    slots = LoadForecast(True, slots=[LoadSlot(now, 200.0, 200.0, 200.0)]
                         + [LoadSlot(evening + SLOT * i, 1000.0, 1000.0, 1000.0) for i in range(4)])
    unlimited = simulate(now, 0.0, 50.0, 0.85, slots, pv)
    limited = simulate(now, 0.0, 50.0, 0.85, slots, pv, charge_kw=1.0)
    assert unlimited.until == evening + timedelta(hours=0.95 * 0.85)
    assert limited.until == evening + timedelta(hours=0.25 * 0.85)


def test_cheapest_block_respects_limit_and_contiguity():
    curve = parse_price_curve(price_state(price=lambda i: 0.10 if 100 <= i < 104 else 0.40), "auto", NOW)
    slots = upcoming(curve, NOW)
    best = cheapest_block(slots, 4, None)
    assert best["von"] == "13.10.2026 01:00" and best["bis"] == "13.10.2026 02:00"
    assert best["preis_mittel"] == pytest.approx(0.10)
    limited = cheapest_block(slots, 4, datetime(2026, 10, 12, 22, 0, tzinfo=UTC))
    assert limited["preis_mittel"] == pytest.approx(0.40)
    assert cheapest_block(slots, 500, None) is None


# ---------------------------------------------------------------------------
# Gesamtauswertung und Netzlade-Freigabe
# ---------------------------------------------------------------------------

SWITCHES = {
    analysis.FREIGABE_ENTITY: {"state": "on"},
    analysis.MANUELL_ENTITY: {"state": "on"},
    "input_boolean.ems_acspeicher1_netzladen_erlaubt": {"state": "on"},
}


def _analyse(states=SWITCHES, load=None, pv=True):
    price = parse_price_curve(price_state(), "auto", NOW)
    curve = parse_pv_curve(pv_curve_state(), "forecast", NOW) if pv else None
    return analyse(NOW, cycle_status=CYCLE, devices=DEVICES, states=states, price=price, pv=curve,
                   load=_flat_load(NOW) if load is None else load, load_reason=None)


def test_analysis_figures():
    result = _analyse()
    load, storage, figures = result["verbrauch"], result["speicher"], result["kennzahlen"]
    assert load["gueltig"] and load["naechste_24h_kwh"] == pytest.approx(24.0)
    assert load["bis_ende_morgen_kwh"] == pytest.approx(27 + 55 / 60, abs=0.01)   # 20:05 bis 00:00 übermorgen
    assert storage["grund"] is None and storage["nutzbar_kwh"] == pytest.approx(3.68)
    assert storage["median"]["bis"] == "12.10.2026 23:45"
    assert storage["vorsichtig"]["bis_iso"] < storage["median"]["bis_iso"] < storage["zuversichtlich"]["bis_iso"]
    assert figures["reichweite_h"] == pytest.approx(3.68)
    assert figures["naechster_ueberschuss_ab"] == "13.10.2026 10:00"
    # Defizit ~10,2 kWh bei 5 kW Ladeleistung → 9 Viertelstunden.
    assert figures["ladeblock_slots"] == 9
    assert figures["guenstigstes_fenster_reichweite"]["von"] == "12.10.2026 20:00"
    assert figures["horizont_reicht"] is True
    assert figures["preis_rang_jetzt_prozent"] == 0.0


def test_analysis_without_forecasts_gives_reasons():
    no_load = _analyse(load=LoadForecast(False, reason="Historie zu kurz (3 von 7 Tagen)"))
    assert no_load["speicher"]["grund"] == "Ohne Verbrauchsprognose keine Reichweite"
    assert no_load["kennzahlen"].get("reichweite_h") is None
    assert _analyse(pv=False)["speicher"]["grund"] == "Ohne PV-Prognose keine Reichweite"


def test_grid_charging_permission_is_display_only_logic():
    grid = _analyse()["netzladen"]
    assert grid["zulaessig"] is True and grid["grund"] == "Manuell angefordert"
    per = {entry["name"]: entry for entry in grid["je_speicher"]}
    assert per["acspeicher1"]["zulaessig"] is True
    assert per["e3dc_speicher"]["zulaessig"] is False and per["e3dc_speicher"]["vorhanden"] is False

    without_manual = _analyse({**SWITCHES, analysis.MANUELL_ENTITY: {"state": "off"}})["netzladen"]
    assert without_manual["zulaessig"] is False and without_manual["pv_zu_wenig"] is None
    off = _analyse({})["netzladen"]
    assert off["zulaessig"] is False and off["grund"] == "Netzladesystem nicht freigegeben (Helfer fehlt)"


def test_publisher_adds_p5_sensors():
    status = {"aktiv": True, "preis": {}, "pv": {}, **_analyse()}
    states = {entity: (state, attrs) for entity, state, attrs in build_states(status)}
    assert states["sensor.ems_dyn_verbrauch_prognose"][0] == f"{status['verbrauch']['bis_ende_morgen_kwh']}"
    reach_state, reach_attrs = states["sensor.ems_dyn_speicher_reichweite"]
    assert reach_state == "2026-10-12T21:45:00+00:00" and reach_attrs["nutzbar_kwh"] == 3.7
    assert states["sensor.ems_dyn_preisfenster"][1]["von"] == "2026-10-12T20:00:00+02:00"
    assert states["sensor.ems_dyn_netzladen"] == ("zulaessig", states["sensor.ems_dyn_netzladen"][1])
    assert states["sensor.ems_dyn_netzladen"][1]["je_speicher"] == {"acspeicher1": True, "e3dc_speicher": False}
    assert len(build_states({"aktiv": True, "preis": {}, "pv": {}})) == 2


# ---------------------------------------------------------------------------
# Speicherung in Data Insight
# ---------------------------------------------------------------------------

def test_sync_writes_load_forecast_run_hourly():
    sync, ticks = _sync()
    sync.client.role_data = {"grundlast": {slot: RoleValue(value, 900.0, "W")
                                           for slot, value in _history(NOW, 14).items()}}
    asyncio.run(sync.tick(NOW, STATES, None, None, {}))
    run = next(run for run in sync.client.runs if run["kind"] == "verbrauch")
    assert run["source"] == "hems:profil_v1" and run["method"] == "profil_v1" and run["unit"] == "W"
    assert len(run["times"]) == len(run["p10"]) == len(run["p90"]) == 192
    assert set(run["details"]) == {"ist_rolle", "historie_tage", "parameter"}
    assert sync.load_forecast.valid and sync.status.letzter_verbrauchslauf
    ticks["t"] = 600
    asyncio.run(sync.tick(NOW, STATES, None, None, {}))
    assert sum(run["kind"] == "verbrauch" for run in sync.client.runs) == 1


def test_sync_short_history_gives_reason_without_run():
    sync, _ = _sync()
    asyncio.run(sync.tick(NOW, STATES, None, None, {}))
    assert not sync.load_forecast.valid and sync.load_reason == "Historie zu kurz (0 von 7 Tagen)"
    assert not any(run["kind"] == "verbrauch" for run in sync.client.runs)


def test_sync_records_slot_means_and_analysis_run():
    sync, ticks = _sync()
    asyncio.run(sync.tick(NOW, {**STATES, **SWITCHES}, None, None, {}))
    assert "schalter_netzladen_freigabe" in sync.client.assignments
    assert "schalter_netzladen_erlaubt:acspeicher1" in sync.client.assignments
    assert "schalter_netzladen_erlaubt:e3dc_speicher" not in sync.client.assignments

    result = _analyse()
    asyncio.run(sync.record(NOW, result))
    runs = [run for run in sync.client.runs if run["kind"] == "auswertung"]
    assert len(runs) == 1 and runs[0]["times"] == [] and runs[0]["source"] == "hems:kennzahlen"
    assert runs[0]["details"]["reichweite_h"] == pytest.approx(3.68)

    later = {**result, "speicher": {**result["speicher"], "nutzbar_kwh": 5.68}}
    asyncio.run(sync.record(NOW + timedelta(minutes=5), later))
    assert sync.client.values == []                          # Slot noch nicht vorbei
    ticks["t"] = 600
    asyncio.run(sync.record(NOW + timedelta(minutes=15), later))
    written = {sensor_id: (times, values) for sensor_id, times, values in sync.client.values}
    nutzbar = sync.client.sensors["hems.nutzbar_kwh"][0]
    assert written[nutzbar] == ([datetime(2026, 10, 12, 18, 0, tzinfo=UTC)], [4.68])
    zulaessig = sync.client.sensors["hems.netzladen_zulaessig"][0]
    assert written[zulaessig][1] == [1.0]
    # Keine neuen Läufe in diesem Takt und keine Stunde vergangen: kein zweiter Auswertungslauf.
    assert sum(run["kind"] == "auswertung" for run in sync.client.runs) == 1


def test_options_battery_efficiencies():
    battery = {"name": "sp", "class": "battery", "soc_entity": "sensor.soc", "power_entity": "sensor.p",
               "available_charge_power_w": 1000, "available_discharge_power_w": 1000}
    base = {"residual_power_entity": "sensor.ueberschuss"}
    ok = validate_options(normalize_options({**base, "devices": [battery]}))
    assert ok.devices[0]["tariff_efficiency_charge"] == 0.92 and not ok.inactive_devices
    bad = validate_options(normalize_options({**base, "devices": [{**battery, "tariff_efficiency_charge": 0.4}]}))
    assert bad.devices == [] and "tariff_efficiency_charge" in str(bad.inactive_devices[0])
