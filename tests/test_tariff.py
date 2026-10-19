"""Preis- und Prognosemodul für den dynamischen Strompreis (D-065, Phase P3).

Geprüft werden die reinen Leser (Preiskurve, PV-Prognose), die Auswertung im
Dienst, die Anzeige-Sensoren und die neuen Add-on-Optionen. Die Formate folgen
den echten Sensoren der Referenzanlage (EPEX Spot, Helios).
"""

import asyncio
import math
from datetime import date, datetime, timedelta, timezone

from hypothesis import given, settings, strategies as st

from configuration import normalize_options, validate_options
from tariff.price_source import BERLIN, end_of_tomorrow, parse_price_curve
from tariff.pv_source import parse_energy, parse_pv_curve
from tariff.service import MAX_SNAPSHOT_AGE_S, TariffConfig, TariffService
from tariff_publisher import PRICE_ENTITY_ID, PV_ENTITY_ID, TariffPublisher, build_states

UTC = timezone.utc
# 12.10.2026 20:05 in Berlin (Sommerzeit).
NOW = datetime(2026, 10, 12, 18, 5, tzinfo=UTC)
DAY_START = datetime(2026, 10, 11, 22, 0, tzinfo=UTC)   # 12.10.2026 00:00 Berlin


def price_state(start=DAY_START, count=192, minutes=15, price=lambda i: 0.30 + i / 1000, unit="€/kWh",
                state="0.4766"):
    data = []
    for i in range(count):
        begin = start + timedelta(minutes=minutes * i)
        data.append({"start_time": begin.astimezone(BERLIN).isoformat(),
                     "end_time": (begin + timedelta(minutes=minutes)).astimezone(BERLIN).isoformat(),
                     "price_per_kwh": price(i)})
    return {"state": state, "attributes": {"unit_of_measurement": unit, "data": data}}


def pv_curve_state(start=DAY_START, count=672, minutes=15):
    forecast = []
    for i in range(count):
        moment = start + timedelta(minutes=minutes * i)
        hour = moment.astimezone(BERLIN).hour
        watts = 4000.0 if 10 <= hour < 14 else 0.0
        forecast.append({"datetime": moment.astimezone(BERLIN).isoformat(), "watts": watts,
                         "p10": watts * 0.8 if i else None, "p90": watts * 1.2 if i else None})
    return {"state": "0", "attributes": {"unit_of_measurement": "W", "forecast": forecast}}


def helios_state(day, days=7, minutes=15, watts=None):
    """Kurve wie Helios 2026.9.6 (`build_forecast_series`): ab Berliner Mitternacht `t += step` auf der
    Ortszeit mit Zone, also nach Wanduhr – im Herbst fehlt die zweite 02:00-Stunde, im Frühjahr
    kommen die übersprungenen Zeiten 02:00–02:45 mit +01:00 vor."""
    watts = watts or (lambda moment: 4000.0 if 10 <= moment.hour < 14 else 0.0)
    moment = datetime(day.year, day.month, day.day, tzinfo=BERLIN)
    end = moment + timedelta(days=days)
    forecast = []
    while moment < end:
        value = watts(moment)
        forecast.append({"datetime": moment.isoformat(), "watts": value, "p10": value * 0.8, "p90": value * 1.2})
        moment += timedelta(minutes=minutes)
    return {"state": "0", "attributes": {"unit_of_measurement": "W", "forecast": forecast}}


def _slots_on(curve, day):
    return [slot for slot in curve.slots if slot.start.astimezone(BERLIN).date() == day]


def _real_steps(curve):
    return {following.start - previous.start for previous, following in zip(curve.slots, curve.slots[1:])}


def energy(value, unit="kWh"):
    return {"state": str(value), "attributes": {"unit_of_measurement": unit}}


# ---------------------------------------------------------------------------
# Preiskurve
# ---------------------------------------------------------------------------

def test_valid_quarter_hour_curve_with_negative_prices():
    curve = parse_price_curve(price_state(price=lambda i: -0.05 if i == 100 else 0.30), "auto", NOW)
    assert curve.valid and curve.raster_min == 15 and curve.detected_raster_min == 15
    assert curve.current.start == datetime(2026, 10, 12, 18, 0, tzinfo=UTC)
    assert curve.horizon_until == datetime(2026, 10, 13, 22, 0, tzinfo=UTC)
    assert min(slot.price for slot in curve.slots) == -0.05


def test_hourly_curve_and_interval_setting():
    hourly = price_state(count=48, minutes=60)
    assert parse_price_curve(hourly, "auto", NOW).raster_min == 60
    assert parse_price_curve(hourly, "60", NOW).valid
    mismatch = parse_price_curve(hourly, "15", NOW)
    assert not mismatch.valid and "Sensor: 60 min, gewählt: 15 min" in mismatch.reason


def test_invalid_curves_name_their_reason():
    def broken(mutate):
        state = price_state()
        mutate(state)
        return parse_price_curve(state, "auto", NOW)

    cases = [
        (lambda s: s["attributes"].update(unit_of_measurement="ct/kWh"), "Einheit ct/kWh"),
        (lambda s: s["attributes"].pop("data"), "data fehlt"),
        (lambda s: s.update(state="unavailable"), "meldet unavailable"),
        (lambda s: s["attributes"]["data"][3].update(price_per_kwh=math.nan), "endliche Zahl"),
        (lambda s: s["attributes"]["data"][3].update(price_per_kwh=True), "endliche Zahl"),
        (lambda s: s["attributes"]["data"][3].update(start_time="2026-10-12T00:45:00"), "Zeitzone"),
        (lambda s: s["attributes"]["data"].pop(10), "Lücke"),
        (lambda s: s["attributes"]["data"].reverse(), "nicht aufsteigend"),
    ]
    for mutate, text in cases:
        result = broken(mutate)
        assert not result.valid and text in result.reason, (text, result.reason)
        assert result.slots == []
    assert "nicht gefunden" in parse_price_curve(None, "auto", NOW).reason
    assert "nicht in der Preiskurve" in parse_price_curve(price_state(), "auto", NOW + timedelta(days=3)).reason


def test_mixed_raster_is_invalid():
    state = price_state(count=4, minutes=60)
    state["attributes"]["data"].append({"start_time": "2026-10-12T04:00:00+02:00",
                                        "end_time": "2026-10-12T04:15:00+02:00", "price_per_kwh": 0.3})
    assert "Gemischte Rasterlängen" in parse_price_curve(state, "auto", DAY_START).reason


def test_daylight_saving_end_has_100_quarter_hours():
    """25.10.2026: Ende der Sommerzeit. Der Berliner Tag hat 25 Stunden."""
    start = datetime(2026, 10, 24, 22, 0, tzinfo=UTC)          # 25.10.2026 00:00 Berlin
    curve = parse_price_curve(price_state(start=start, count=100), "auto", start + timedelta(hours=10))
    assert curve.valid and len(curve.slots) == 100
    assert curve.horizon_until.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M") == "26.10.2026 00:00"
    assert end_of_tomorrow(datetime(2026, 10, 24, 12, 0, tzinfo=UTC)) == datetime(2026, 10, 25, 23, 0, tzinfo=UTC)


@settings(max_examples=60, deadline=None)
@given(raster=st.sampled_from([15, 60]), count=st.integers(min_value=2, max_value=200),
       prices=st.lists(st.floats(min_value=-1, max_value=2, allow_nan=False), min_size=200, max_size=200),
       position=st.floats(min_value=0, max_value=0.999))
def test_property_contiguous_curves_are_valid(raster, count, prices, position):
    state = price_state(count=count, minutes=raster, price=lambda i: prices[i])
    now = DAY_START + timedelta(minutes=raster * count * position)
    curve = parse_price_curve(state, "auto", now)
    assert curve.valid and curve.raster_min == raster
    assert curve.current.start <= now < curve.current.end
    assert curve.horizon_until == DAY_START + timedelta(minutes=raster * count)


@settings(max_examples=60, deadline=None)
@given(count=st.integers(min_value=3, max_value=100), gap=st.integers(min_value=1, max_value=98))
def test_property_any_gap_invalidates(count, gap):
    state = price_state(count=count)
    data = state["attributes"]["data"]
    del data[min(gap, len(data) - 2)]
    assert not parse_price_curve(state, "auto", DAY_START).valid


# ---------------------------------------------------------------------------
# PV-Prognose
# ---------------------------------------------------------------------------

def test_pv_energy_and_curve():
    assert parse_energy(energy("31.59")).value_kwh == 31.59
    assert "Einheit Wh" in parse_energy(energy(31590, "Wh")).reason
    assert "≥ 0" in parse_energy(energy(-1)).reason
    assert "unknown" in parse_energy({"state": "unknown", "attributes": {}}).reason

    curve = parse_pv_curve(pv_curve_state(), "forecast", NOW)
    assert curve.valid and curve.raster_min == 15
    per_day = curve.energy_per_day_kwh()
    assert len(per_day) == 7 and all(math.isclose(kwh, 16.0) for kwh in per_day.values())
    assert curve.until == DAY_START + timedelta(days=7)


def test_pv_curve_invalid_cases():
    state = pv_curve_state(count=4)
    del state["attributes"]["forecast"][1]
    assert "lückenhaft" in parse_pv_curve(state, "forecast", DAY_START).reason
    assert "fehlt" in parse_pv_curve(pv_curve_state(), "andere", NOW).reason
    old = parse_pv_curve(pv_curve_state(count=8), "forecast", NOW + timedelta(days=2))
    assert "Vergangenheit" in old.reason


AUTUMN_NOW = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)
SPRING_NOW = datetime(2027, 3, 26, 12, 0, tzinfo=UTC)


def test_pv_curve_autumn_dst_fills_second_hour_from_wall_clock_twins():
    state = helios_state(date(2026, 10, 19))
    assert len(state["attributes"]["forecast"]) == 672            # wie live am 19.10.2026
    curve = parse_pv_curve(state, "forecast", AUTUMN_NOW)
    assert curve.valid and curve.raster_min == 15 and len(curve.slots) == 676
    assert _real_steps(curve) == {timedelta(minutes=15)}
    assert len(_slots_on(curve, date(2026, 10, 25))) == 100
    filled = [slot for slot in curve.slots if slot.dst_filled]
    assert [slot.start for slot in filled] == [datetime(2026, 10, 25, 1, 15 * i, tzinfo=UTC) for i in range(4)]
    assert all(slot.watts == 0 and slot.p10 == 0 and slot.p90 == 0 for slot in filled)
    assert filled[0].start.isoformat() == "2026-10-25T02:00:00+01:00"
    assert curve.until == datetime(2026, 10, 26, tzinfo=BERLIN)
    assert curve.energy_per_day_kwh()[date(2026, 10, 25)] == 16.0

    hourly = parse_pv_curve(helios_state(date(2026, 10, 19), minutes=60), "forecast", AUTUMN_NOW)
    assert hourly.valid and hourly.raster_min == 60 and len(_slots_on(hourly, date(2026, 10, 25))) == 25
    assert [slot.start for slot in hourly.slots if slot.dst_filled] == [datetime(2026, 10, 25, 1, tzinfo=UTC)]


def test_pv_curve_dst_pattern_only_where_berlin_switches():
    # Echte Lücke von 75 min an einem gewöhnlichen Tag: ungültig, Grund nennt die Stelle.
    state = helios_state(date(2026, 10, 19))
    del state["attributes"]["forecast"][8:12]
    reason = parse_pv_curve(state, "forecast", AUTUMN_NOW).reason
    assert reason == "Kurve ist lückenhaft zwischen 19.10.2026 01:45 und 19.10.2026 03:00"

    # Scheinbare Umstellung am 20.10.2026 (Wanduhr lückenlos, Offset +01:00 ist an dem Tag falsch).
    state = helios_state(date(2026, 10, 19))
    for entry in state["attributes"]["forecast"]:
        if entry["datetime"].startswith("2026-10-20T") and entry["datetime"][11:16] >= "03:00":
            entry["datetime"] = entry["datetime"][:19] + "+01:00"
    assert "lückenhaft zwischen 20.10.2026 02:45" in parse_pv_curve(state, "forecast", AUTUMN_NOW).reason

    # Doppelte Stunde mit Leistung: nicht auffüllen.
    night = helios_state(date(2026, 10, 19), watts=lambda moment: 50.0 if moment.hour == 2 else 0.0)
    assert parse_pv_curve(night, "forecast", AUTUMN_NOW).reason == \
        "Zeitumstellung 25.10.2026: Helios-Werte der doppelten Stunde sind nicht 0 W"

    # Umstellung am Kurvenanfang: Wanduhr-Zwillinge fehlen.
    state = helios_state(date(2026, 10, 25), days=1)
    del state["attributes"]["forecast"][:11]                     # beginnt 02:45+02:00
    assert parse_pv_curve(state, "forecast", AUTUMN_NOW).reason == \
        "Zeitumstellung 25.10.2026: Werte der doppelten Stunde fehlen"


def test_pv_curve_spring_dst_drops_phantom_hour():
    state = helios_state(date(2027, 3, 26), days=4)
    phantoms = [entry["datetime"] for entry in state["attributes"]["forecast"]
                if entry["datetime"].startswith("2027-03-28T02:")]
    assert phantoms == [f"2027-03-28T02:{minute:02d}:00+01:00" for minute in (0, 15, 30, 45)]
    curve = parse_pv_curve(state, "forecast", SPRING_NOW)
    assert curve.valid and len(_slots_on(curve, date(2027, 3, 28))) == 92
    assert _real_steps(curve) == {timedelta(minutes=15)}
    assert len({slot.start for slot in curve.slots}) == len(curve.slots) == 4 * 96 - 4
    assert not any(slot.dst_filled for slot in curve.slots)

    hourly = parse_pv_curve(helios_state(date(2027, 3, 26), days=4, minutes=60), "forecast", SPRING_NOW)
    assert hourly.valid and len(_slots_on(hourly, date(2027, 3, 28))) == 23

    lit = helios_state(date(2027, 3, 26), days=4, watts=lambda moment: 50.0 if moment.hour == 2 else 0.0)
    assert parse_pv_curve(lit, "forecast", SPRING_NOW).reason == \
        "Zeitumstellung 28.03.2027: Helios-Werte der übersprungenen Stunde sind nicht 0 W"

    # Fall a – real lückenlos (01:45+01:00 → 03:00+02:00) – war schon gültig und bleibt es.
    real = parse_pv_curve(pv_curve_state(start=datetime(2027, 3, 27, 23, tzinfo=UTC), count=192), "forecast",
                          SPRING_NOW)
    assert real.valid and len(_slots_on(real, date(2027, 3, 28))) == 92


# ---------------------------------------------------------------------------
# Dienst und Anzeige-Sensoren
# ---------------------------------------------------------------------------

CONFIG = TariffConfig.from_options({
    "tariff_enabled": True, "tariff_price_entity": "sensor.preis", "tariff_price_interval": "auto",
    "tariff_tomorrow_warning_time": "15:00", "pv_today_entity": "sensor.pv_heute",
    "pv_tomorrow_entity": "sensor.pv_morgen", "pv_today_remaining_entity": "sensor.pv_rest",
    "pv_curve_entity": "sensor.pv_kurve", "pv_curve_attribute": "forecast",
})
STATES = {
    "sensor.preis": price_state(),
    "sensor.pv_heute": energy("31.59"), "sensor.pv_morgen": energy("35.15"), "sensor.pv_rest": energy("0"),
    "sensor.pv_kurve": pv_curve_state(),
}


def test_service_status_with_tomorrow_prices():
    status = TariffService(CONFIG).evaluate(STATES, 5, NOW)
    price = status["preis"]
    assert status["aktiv"] and status["grund"] is None and status["stand"] == "12.10.2026 20:05:00"
    assert price["gueltig"] and price["raster_min"] == 15 and price["morgen_vorhanden"] is True
    assert price["aktuell"] == {"tag": "12.10.2026", "von": "20:00", "bis": "20:15",
                                "von_iso": "2026-10-12T20:00:00+02:00", "bis_iso": "2026-10-12T20:15:00+02:00",
                                "preis": 0.38}
    assert price["horizont_bis"] == "14.10.2026 00:00" and price["warnung"] is None
    assert price["guenstigster"]["von"] == "20:00" and price["teuerster"]["tag"] == "13.10.2026"
    assert price["kommend_gesamt"] == 112 and len(price["kommend"]) == 96
    pv = status["pv"]
    assert pv["heute"]["wert_kwh"] == 31.59 and pv["rest_heute"]["gueltig"]
    assert pv["kurve"]["gueltig"] and pv["kurve"]["tage"][0] == {"tag": "12.10.2026", "kwh": 16.0}


def test_service_warns_when_tomorrow_is_missing_after_warning_time():
    only_today = dict(STATES, **{"sensor.preis": price_state(count=96)})
    morning = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)          # 10:00 Berlin
    service = TariffService(CONFIG)
    assert service.evaluate(only_today, 5, morning)["preis"]["warnung"] is None
    late = service.evaluate(only_today, 5, datetime(2026, 10, 12, 13, 30, tzinfo=UTC))   # 15:30 Berlin
    assert late["preis"]["morgen_vorhanden"] is False and late["preis"]["warnung"] == "Preise für morgen fehlen noch"


def test_service_stale_snapshot_and_disabled():
    stale = TariffService(CONFIG).evaluate(STATES, MAX_SNAPSHOT_AGE_S + 1, NOW)
    assert "Zustand von Home Assistant ist" in stale["grund"]
    assert not stale["preis"]["gueltig"] and stale["preis"]["grund"] == stale["grund"]
    assert not stale["pv"]["heute"]["gueltig"]
    assert TariffService(CONFIG).evaluate(STATES, None, NOW)["grund"] == "Noch kein Zustand von Home Assistant"
    off = TariffService(TariffConfig.from_options({}))
    assert off.evaluate(STATES, 5, NOW)["aktiv"] is False and build_states(off.status) == []


def test_publisher_writes_only_changes_or_missing_entities():
    status = TariffService(CONFIG).evaluate(STATES, 5, NOW)
    states = build_states(status)
    assert [entity for entity, _, _ in states] == [PRICE_ENTITY_ID, PV_ENTITY_ID]
    assert states[0][1] == "0.38" and states[0][2]["guenstigster_slot"]["preis"] == 0.38
    assert states[1][1] == "0.0" and states[1][2]["morgen_kwh"] == 35.15

    class FakeHA:
        def __init__(self):
            self.calls = []

        async def set_state(self, entity_id, state, attributes):
            self.calls.append(entity_id)
            return True

    ha, publisher = FakeHA(), TariffPublisher()
    present = {PRICE_ENTITY_ID: {}, PV_ENTITY_ID: {}}
    assert asyncio.run(publisher.publish(ha, status, {})) == 2
    assert asyncio.run(publisher.publish(ha, status, present)) == 0
    # Nach einem HA-Neustart fehlt die Entität im Schnappschuss: erneut schreiben.
    assert asyncio.run(publisher.publish(ha, status, {PV_ENTITY_ID: {}})) == 1

    assert states[1][2]["kurve_gueltig"] is True and states[1][2]["kurve_grund"] is None

    invalid = TariffService(CONFIG).evaluate({}, 5, NOW)
    assert [state for _, state, _ in build_states(invalid)] == ["unavailable", "unavailable"]
    assert build_states(invalid)[1][2]["kurve_grund"] == "Sensor der Prognosekurve nicht gefunden"


# ---------------------------------------------------------------------------
# Add-on-Optionen
# ---------------------------------------------------------------------------

def _validate(**tariff):
    raw = {"residual_power_entity": "sensor.ueberschuss", "devices": [], **tariff}
    return validate_options(normalize_options(raw))


def test_tariff_options_defaults_and_validation():
    defaults = _validate()
    assert defaults.options["tariff_enabled"] is False and defaults.options["tariff_price_interval"] == "auto"
    assert not any(key.startswith(("tariff_", "pv_")) for key in defaults.field_errors)

    result = _validate(tariff_enabled=True, tariff_price_interval="30", tariff_tomorrow_warning_time="25:00",
                       pv_curve_entity="helios", pv_curve_attribute="Forecast!")
    errors = result.field_errors
    assert "Pflichtfeld" in errors["tariff_price_entity"]
    assert "auto, 15 oder 60" in errors["tariff_price_interval"]
    assert "hh:mm" in errors["tariff_tomorrow_warning_time"]
    assert "Sensor-Entity-ID" in errors["pv_curve_entity"]
    assert "Attributname" in errors["pv_curve_attribute"]

    ok = _validate(tariff_enabled=True, tariff_price_entity=" sensor.epex_spot_data_total_price_2 ",
                   pv_curve_entity="sensor.helios_hausdach_power_now")
    assert not any(key.startswith(("tariff_", "pv_")) for key in ok.field_errors)
    assert ok.options["tariff_price_entity"] == "sensor.epex_spot_data_total_price_2"
