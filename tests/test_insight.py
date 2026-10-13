"""Anbindung an Skytech Data Insight (D-065, Phase P4; Vertrag contract_hems_data_insight 0.2).

Unit-Tests für Rollen, Grundlast, Secrets und den Abgleich mit einer Attrappe
des Clients. Der Integrationstest am Ende läuft gegen eine echte, von Data
Insight migrierte Datenbank – nur wenn `HEMS_INSIGHT_TEST_DSN` gesetzt ist
(Superuser-DSN auf die Datenbank `skytech_test`, die die Integrationstests von
Skytech-Data-Insight anlegen).
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

import insight_client
from configuration import (
    devices_needing_shutdown, mask_secrets, normalize_options, restore_secrets, validate_options,
)
from insight_client import InsightError, RoleValue
from tariff import insight_sync
from tariff.insight_sync import GrundlastTerm, InsightSync, build_roles, compute_grundlast
from tariff.price_source import parse_price_curve
from tariff.pv_source import parse_pv_curve

from test_tariff import NOW, price_state, pv_curve_state

UTC = timezone.utc

# Geräte wie in der Referenzanlage (12.10.2026).
DEVICES = [
    {"name": "heizstab", "label": "Heizstab", "class": "controllable", "actual_power_entity": "sensor.elwa_ist"},
    {"name": "wallbox_1", "label": "Wallbox", "class": "controllable", "actual_power_entity": "sensor.wb_ist"},
    {"name": "heizlufter_1", "label": "Heizlüfter 1", "class": "binary", "switch_entity": "switch.uv_1",
     "power_actual_entity": "sensor.uv_1_leistung", "power_w": 1500},
    {"name": "heizlufter_2", "label": "Heizlüfter 2", "class": "binary", "switch_entity": "switch.uv_2",
     "power_actual_entity": "", "power_w": 1500},
    {"name": "acspeicher1", "label": "AC Speicher 1", "class": "battery", "soc_entity": "sensor.ac_soc",
     "power_entity": "sensor.ac_leistung", "power_sign": "positiv_laden", "tariff_in_house_load": True},
    {"name": "e3dc_speicher", "label": "E3DC", "class": "battery", "soc_entity": "sensor.e3dc_soc",
     "power_entity": "sensor.e3dc_leistung", "power_sign": "positiv_laden", "tariff_in_house_load": False},
]
OPTIONS = {
    "tariff_price_entity": "sensor.preis", "pv_today_entity": "sensor.pv_heute", "pv_tomorrow_entity": "",
    "pv_today_remaining_entity": "", "pv_curve_entity": "sensor.pv_kurve",
    "tariff_house_load_entity": "sensor.haus", "pv_actual_entity": "sensor.pv_ist",
    "insight_host": "auto", "insight_port": 5432, "insight_password": "geheim-123",
}
STATES = {"sensor.haus": {"state": "500", "attributes": {"unit_of_measurement": "W"}}}


# ---------------------------------------------------------------------------
# Rollen und Grundlast
# ---------------------------------------------------------------------------

def test_roles_for_reference_installation():
    specs, terms, notes = build_roles(OPTIONS, DEVICES, STATES)
    roles = {spec.role: spec for spec in specs}
    assert set(roles) == {
        "hausverbrauch", "pv_ist", "preis", "pv_prognose_heute",
        "verbraucher_ist:heizstab", "verbraucher_ist:wallbox_1", "verbraucher_ist:heizlufter_1",
        "verbraucher_schaltzustand:heizlufter_2",
        "speicher_soc:acspeicher1", "speicher_leistung:acspeicher1",
        "speicher_soc:e3dc_speicher", "speicher_leistung:e3dc_speicher", "grundlast",
        "nutzbar", "reichweite", "netzladen_zulaessig",
        "netzladen_zulaessig:acspeicher1", "netzladen_zulaessig:e3dc_speicher",
    }
    assert roles["hausverbrauch"].unit == "W" and roles["pv_ist"].unit is None
    assert roles["grundlast"].entity_id == "hems.grundlast_w" and roles["grundlast"].source == "hems"
    assert roles["speicher_soc:e3dc_speicher"].quantity == "ladezustand"
    # Der E3DC steckt nicht im Hausverbrauch: kein Summand. Der Marstek schon.
    by_role = {term.role: term for term in terms}
    assert "speicher_leistung:e3dc_speicher" not in by_role
    assert by_role["speicher_leistung:acspeicher1"].sign == -1.0
    assert by_role["verbraucher_schaltzustand:heizlufter_2"].factor == 1500 and notes == []


def test_roles_without_house_load_or_with_split_battery_sensors():
    specs, terms, notes = build_roles({**OPTIONS, "tariff_house_load_entity": ""}, DEVICES, STATES)
    assert "grundlast" not in {spec.role for spec in specs} and terms == []
    assert "Ohne Hausverbrauch-Sensor keine Grundlast" in notes
    split = [*DEVICES[:4], {**DEVICES[4], "power_entity": "", "charge_power_entity": "sensor.l",
                             "discharge_power_entity": "sensor.e"}]
    specs, terms, notes = build_roles(OPTIONS, split, STATES)
    assert "grundlast" not in {spec.role for spec in specs}
    assert any("getrennte Lade-/Entladesensoren" in note for note in notes)


def _slots(count=3):
    start = datetime(2026, 10, 12, 18, 0, tzinfo=UTC)
    return [start + timedelta(minutes=i) for i in range(count)]


def test_grundlast_formula_and_gaps():
    # Je Minute (Vertrag 0.3): volle Abdeckung 60 s, Minimum 48 s.
    slots = _slots()
    full = 60.0
    values = {
        "hausverbrauch": {slot: RoleValue(12.0, full, "W") for slot in slots},
        "verbraucher_ist:heizstab": {slot: RoleValue(0.0, full, "W") for slot in slots},
        "verbraucher_schaltzustand:heizlufter_2": {slot: RoleValue(0.5, full, None) for slot in slots},
        "speicher_leistung:acspeicher1": {slot: RoleValue(-1101.0, full, "W") for slot in slots},
    }
    values["hausverbrauch"][slots[1]] = RoleValue(12.0, 30.0, "W")             # lückenhaft
    del values["verbraucher_ist:heizstab"][slots[2]]                            # fehlt
    terms = [GrundlastTerm("verbraucher_ist:heizstab", -1.0),
             GrundlastTerm("verbraucher_schaltzustand:heizlufter_2", -1.0, 1500, needs_watt=False),
             GrundlastTerm("speicher_leistung:acspeicher1", -1.0)]
    times, results, reason = compute_grundlast(values, terms, slots)
    # Beispiel vom 12.10.2026: Haus 12 W, Marstek entlädt 1101 W → 1113 W, minus 750 W Heizlüfter.
    assert reason is None and times == [slots[0]] and results == [363.0]

    values["verbraucher_ist:heizstab"] = {slot: RoleValue(1.0, full, "kW") for slot in slots}
    assert "erwartet W" in compute_grundlast(values, terms, slots)[2]


# ---------------------------------------------------------------------------
# Optionen und Secrets
# ---------------------------------------------------------------------------

def test_secret_is_masked_and_restored():
    options = normalize_options({"insight_password": "geheim-123"})
    masked, is_set = mask_secrets(options)
    assert masked["insight_password"] == "" and is_set == {"insight_password": True}
    stored = {"insight_password": "geheim-123"}
    assert restore_secrets({"insight_password": ""}, stored)["insight_password"] == "geheim-123"
    assert restore_secrets({"insight_password": None}, stored)["insight_password"] == ""
    assert restore_secrets({"insight_password": "neu-456"}, stored)["insight_password"] == "neu-456"


def test_insight_options_validation_and_display_only_battery_flag():
    base = {"residual_power_entity": "sensor.ueberschuss", "devices": []}
    ok = validate_options(normalize_options(base))
    assert ok.options["insight_host"] == "auto" and ok.options["insight_port"] == 5432
    bad = validate_options(normalize_options({**base, "insight_host": "kein host!", "insight_port": 70000,
                                              "tariff_house_load_entity": "haus"}))
    assert {"insight_host", "insight_port", "tariff_house_load_entity"} <= set(bad.field_errors)

    battery = {"name": "sp", "class": "battery", "soc_entity": "sensor.soc", "power_entity": "sensor.p",
               "available_charge_power_w": 1000, "available_discharge_power_w": 1000}
    old = normalize_options({**base, "devices": [battery]})
    new = normalize_options({**base, "devices": [{**battery, "tariff_in_house_load": True}]})
    assert old["devices"][0]["tariff_in_house_load"] is False and new["devices"][0]["tariff_in_house_load"]
    assert devices_needing_shutdown(old, new) == []


# ---------------------------------------------------------------------------
# Abgleich mit einer Attrappe des Clients
# ---------------------------------------------------------------------------

class FakeClient:
    def __init__(self):
        self.sensors = {}            # entity -> (id, aktiv, managed)
        self.assignments = {}
        self.runs = []
        self.values = []
        self.prices = {}
        self.role_data = {}
        self.minute_data = {}
        self.counters = {}
        self.last = None
        self.fail = None

    async def connect(self):
        if self.fail:
            raise InsightError(self.fail)

    async def close(self):
        pass

    async def ensure_sensor(self, entity, attribute, name, category, quantity, unit, source, counter=False):
        if entity not in self.sensors:
            self.sensors[entity] = [len(self.sensors) + 1, True, True]
        self.sensors[entity][1] = True
        self.counters[entity] = counter
        return self.sensors[entity][0]

    async def deactivate_sensor(self, sensor_id):
        for entry in self.sensors.values():
            if entry[0] == sensor_id:
                entry[1] = False

    async def assign(self, role, sensor_id):
        entity = next(e for e, entry in self.sensors.items() if entry[0] == sensor_id)
        self.assignments[role] = (sensor_id, entity)

    async def current_assignments(self):
        return dict(self.assignments)

    async def managed_sensor_ids(self):
        return {entry[0]: entry[1] for entry in self.sensors.values() if entry[2]}

    async def price_values(self, start, end):
        return dict(self.prices)

    async def write_run(self, **kwargs):
        self.runs.append(kwargs)
        return len(self.runs)

    async def last_minute(self, role):
        return self.last

    async def role_values(self, roles, start, end, minutes=False):
        data = self.minute_data if minutes else self.role_data
        return {role: {t: v for t, v in data.get(role, {}).items() if start <= t < end} for role in roles}

    async def write_values(self, sensor_id, times, values):
        self.values.append((sensor_id, times, values))
        return len(times)


def _sync(options=OPTIONS, devices=DEVICES, clock=None):
    ticks = {"t": 0.0}

    async def host():
        return "e778e1d3-skytech-data-insight"

    sync = InsightSync(options, devices, resolve_host=host, clock=clock or (lambda: ticks["t"]))
    sync.client = FakeClient()
    return sync, ticks


def test_sync_reconciles_roles_and_swaps_sensors():
    sync, ticks = _sync()
    price = parse_price_curve(price_state(), "auto", NOW)
    status = asyncio.run(sync.tick(NOW, STATES, price, None, {}))
    client = sync.client
    assert status["verbunden"] and status["grund"] is None and len(status["rollen"]) == 18
    assert client.assignments["hausverbrauch"][1] == "sensor.haus"
    assert [run["kind"] for run in client.runs] == ["preis"]
    # Gleiche Kurve: kein zweiter Lauf.
    asyncio.run(sync.tick(NOW, STATES, price, None, {}))
    assert len(client.runs) == 1

    # Hausverbrauch-Sensor im HEMS getauscht: neue Zuordnung, alter Sensor stillgelegt.
    sync.options = {**OPTIONS, "tariff_house_load_entity": "sensor.haus_neu"}
    ticks["t"] = insight_sync.RECONCILE_INTERVAL_S + 1
    asyncio.run(sync.tick(NOW, STATES, price, None, {}))
    assert client.assignments["hausverbrauch"][1] == "sensor.haus_neu"
    assert client.sensors["sensor.haus"][1] is False


def test_sync_skips_price_run_already_stored_after_restart():
    sync, _ = _sync()
    price = parse_price_curve(price_state(), "auto", NOW)
    sync.client.prices = {slot.start: slot.price for slot in price.slots}
    asyncio.run(sync.tick(NOW, STATES, price, None, {}))
    assert sync.client.runs == []


def test_sync_pv_run_throttling_and_grundlast():
    sync, ticks = _sync()
    curve = parse_pv_curve(pv_curve_state(), "forecast", NOW)
    details = {"heute": 31.6, "morgen": 35.2, "rest_heute": 0.0}
    asyncio.run(sync.tick(NOW, STATES, None, curve, details))
    run = sync.client.runs[0]
    assert run["kind"] == "pv" and run["raster_min"] == 15 and len(run["times"]) == 192
    assert run["times"][0] == datetime(2026, 10, 12, 18, 0, tzinfo=UTC)
    assert run["details"] == {"entity": "sensor.pv_kurve", "ist_rolle": "pv_ist", "heute_kwh": 31.6,
                              "morgen_kwh": 35.2, "rest_heute_kwh": 0.0}
    ticks["t"] = 600
    asyncio.run(sync.tick(NOW, STATES, None, curve, details))
    assert len(sync.client.runs) == 1                      # unverändert, keine Stunde vergangen
    ticks["t"] = 3601
    asyncio.run(sync.tick(NOW, STATES, None, curve, details))
    assert len(sync.client.runs) == 2

    # Grundlast je Minute: ohne Werte nichts, mit vollständigen Werten genau die abgeschlossenen Minuten.
    assert sync.client.values == []
    minute = datetime(2026, 10, 12, 17, 58, tzinfo=UTC)
    data = {role: {minute: RoleValue(0.0, 60.0, "W")} for role in
            ("verbraucher_ist:heizstab", "verbraucher_ist:wallbox_1", "verbraucher_ist:heizlufter_1",
             "speicher_leistung:acspeicher1")}
    data["hausverbrauch"] = {minute: RoleValue(450.0, 60.0, "W")}
    data["verbraucher_schaltzustand:heizlufter_2"] = {minute: RoleValue(0.0, 60.0, None)}
    # Zu spät für diese Minute: noch nicht abgeschlossen (NOW 18:05, Verzögerung 2 min → bis 18:03).
    data["hausverbrauch"][datetime(2026, 10, 12, 18, 3, tzinfo=UTC)] = RoleValue(1.0, 60.0, "W")
    sync.client.minute_data = data
    sync.client.last = datetime(2026, 10, 12, 17, 55, tzinfo=UTC)
    sync._grundlast_from = None
    asyncio.run(sync.tick(NOW, STATES, None, None, {}))
    sensor_id, times, values = sync.client.values[0]
    assert sensor_id == sync.client.sensors["hems.grundlast_w"][0] and times == [minute] and values == [450.0]
    assert sync.status.grundlast_bis == "12.10.2026 19:59"


def test_sync_reports_errors_and_missing_password():
    sync, _ = _sync()
    sync.client.fail = "Anmeldung abgelehnt: Passwort für skytech_hems falsch"
    status = asyncio.run(sync.tick(NOW, STATES, None, None, {}))
    assert status["verbunden"] is False and "Passwort" in status["grund"]
    off = InsightSync({**OPTIONS, "insight_password": ""}, DEVICES, resolve_host=None)
    assert asyncio.run(off.tick(NOW, STATES, None, None, {}))["grund"] == "Kein Passwort für Data Insight eingetragen"

    async def no_host():
        return ""

    missing = InsightSync(OPTIONS, DEVICES, resolve_host=no_host)
    assert "nicht installiert" in asyncio.run(missing.tick(NOW, STATES, None, None, {}))["grund"]


def test_client_error_texts_never_contain_the_password():

    reason = insight_client._connect_reason(
        insight_client.psycopg.OperationalError('password authentication failed for user "skytech_hems"'))
    assert reason == "Anmeldung abgelehnt: Passwort für skytech_hems falsch"
    assert "geheim" not in reason


# ---------------------------------------------------------------------------
# Integration gegen eine von Data Insight migrierte Datenbank
# ---------------------------------------------------------------------------

def test_roles_for_grid_and_energy_meters_with_unit_check():
    options = {**OPTIONS, "tariff_grid_power_entity": "sensor.netz", "tariff_grid_import_energy_entity": "sensor.bezug",
               "tariff_grid_export_energy_entity": "sensor.einspeisung", "pv_actual_energy_entity": "sensor.pv_zaehler",
               "tariff_house_load_energy_entity": "sensor.haus_zaehler"}
    devices = [*DEVICES[:5], {**DEVICES[5], "tariff_charge_energy_entity": "sensor.e3dc_laden",
                              "tariff_discharge_energy_entity": "sensor.e3dc_entladen"}]
    unit = lambda u: {"state": "1", "attributes": {"unit_of_measurement": u}}  # noqa: E731
    states = {**STATES, "sensor.netz": unit("W"), "sensor.bezug": unit("kWh"), "sensor.einspeisung": unit("Wh"),
              "sensor.pv_zaehler": unit("kWh"), "sensor.haus_zaehler": unit("kWh"),
              "sensor.e3dc_laden": unit("kWh"), "sensor.e3dc_entladen": unit("kWh")}
    specs, _, notes = build_roles(options, devices, states)
    roles = {spec.role: spec for spec in specs}
    assert notes == []
    assert roles["netz_leistung"].category == "netz" and not roles["netz_leistung"].counter
    for role in ("netz_bezug_energie", "netz_einspeisung_energie", "pv_ist_energie", "hausverbrauch_energie",
                 "speicher_laden_energie:e3dc_speicher", "speicher_entladen_energie:e3dc_speicher"):
        assert roles[role].counter and roles[role].quantity == "energie", role
    assert "speicher_laden_energie:acspeicher1" not in roles

    # Falsche Einheiten: Rolle wird nicht zugeordnet, Hinweis statt Datenmüll (Fall 13.10.2026).
    wrong = {**states, "sensor.pv_ist": unit("kWh"), "sensor.bezug": unit("W"), "sensor.haus": unit("kW")}
    specs, terms, notes = build_roles(options, devices, wrong)
    roles = {spec.role for spec in specs}
    assert "pv_ist" not in roles and "netz_bezug_energie" not in roles and "hausverbrauch" not in roles
    assert "grundlast" not in roles and terms == []
    assert any(note.startswith("pv_ist: sensor.pv_ist hat die Einheit kWh, erwartet W") for note in notes)
    assert any("erwartet kWh oder Wh" in note for note in notes)


def test_sync_marks_counters_and_grundlast_progress_skips_gaps():
    sync, ticks = _sync(options={**OPTIONS, "pv_actual_energy_entity": "sensor.pv_zaehler"})
    states = {**STATES, "sensor.pv_zaehler": {"state": "1", "attributes": {"unit_of_measurement": "kWh"}}}
    asyncio.run(sync.tick(NOW, states, None, None, {}))
    assert sync.client.counters["sensor.pv_zaehler"] is True and sync.client.counters["sensor.haus"] is False
    # Ohne echte Grundlast in Data Insight: Start 10 Tage zurück, je Takt höchstens 2 Tage in Tagesblöcken.
    assert sync._grundlast_from == NOW.replace(second=0) - insight_sync.MAX_BACKFILL \
        + insight_sync.BACKFILL_PER_TICK - insight_sync.MINUTE_DELAY
    # Eine Lücke ohne Werte hält den Fortschritt nicht auf.
    for _ in range(5):
        asyncio.run(sync.tick(NOW, states, None, None, {}))
    assert sync._grundlast_from == NOW.replace(second=0) - 2 * insight_sync.MINUTE_DELAY


def test_grundlast_skips_minutes_without_house_raw_values():
    minute = _slots(1)[0]
    values = {"hausverbrauch": {minute: RoleValue(5935.0, 60.0, "W", 0)}}  # nur fortgeführt (DI-Ausfall)
    assert compute_grundlast(values, [], [minute])[0] == []
    values["hausverbrauch"][minute] = RoleValue(5935.0, 60.0, "W", 17)
    assert compute_grundlast(values, [], [minute])[1] == [5935.0]


def test_sync_heals_missing_grundlast_minutes_later():
    sync, ticks = _sync()
    asyncio.run(sync.tick(NOW, STATES, None, None, {}))       # Abgleich, Grundlast-Fortschritt gesetzt
    gap = datetime(2026, 10, 12, 12, 30, tzinfo=UTC)          # vor 5,5 h: damals fehlten die Quellen
    sync._grundlast_from = datetime(2026, 10, 12, 18, 0, tzinfo=UTC)
    full = {role: {gap: RoleValue(0.0, 60.0, "W", 3)} for role in
            ("verbraucher_ist:heizstab", "verbraucher_ist:wallbox_1", "verbraucher_ist:heizlufter_1",
             "speicher_leistung:acspeicher1")}
    full["hausverbrauch"] = {gap: RoleValue(640.0, 60.0, "W", 30)}
    full["verbraucher_schaltzustand:heizlufter_2"] = {gap: RoleValue(0.0, 60.0, None, 0)}
    sync.client.minute_data = full
    sync.client.values.clear()
    ticks["t"] = insight_sync.HEAL_INTERVAL_S + 1
    asyncio.run(sync._heal_grundlast(NOW))
    sensor_id = sync.client.sensors["hems.grundlast_w"][0]
    assert (sensor_id, [gap], [640.0]) in sync.client.values
    # Steht die Minute schon in Data Insight, wird sie nicht erneut geschrieben.
    full["grundlast"] = {gap: RoleValue(640.0, 60.0, "W", 1)}
    sync.client.values.clear()
    ticks["t"] = 2 * insight_sync.HEAL_INTERVAL_S + 2
    asyncio.run(sync._heal_grundlast(NOW))
    assert sync.client.values == []


def test_client_resolves_ipv4_only():
    assert asyncio.run(insight_client._ipv4("localhost", 5432)) == "127.0.0.1"
    assert asyncio.run(insight_client._ipv4("gibt-es-nicht.invalid", 5432)) is None


DSN = os.environ.get("HEMS_INSIGHT_TEST_DSN")


@pytest.mark.skipif(not DSN, reason="HEMS_INSIGHT_TEST_DSN nicht gesetzt – keine Data-Insight-Datenbank")
def test_integration_against_data_insight_database():
    import psycopg
    from urllib.parse import urlparse

    url = urlparse(DSN)
    password = "hems-integration-123"

    async def run():
        admin = await psycopg.AsyncConnection.connect(DSN, autocommit=True)
        await admin.execute("TRUNCATE skytech.sensor RESTART IDENTITY CASCADE")
        await admin.execute("TRUNCATE skytech.prognose_lauf RESTART IDENTITY CASCADE")
        await admin.execute(f"ALTER ROLE skytech_hems LOGIN PASSWORD '{password}'")
        # Eine Rolle, die Data Insight schon aufgezeichnet hat: Übernahme samt Historie.
        await admin.execute(
            "INSERT INTO skytech.sensor (entity_id, name, kategorie, groesse, einheit) "
            "VALUES ('sensor.haus', 'Haus von Hand', 'verbraucher', 'leistung', 'W')")

        async def host():
            return url.hostname

        options = {**OPTIONS, "insight_port": url.port, "insight_password": password}
        states = {entity: {"state": "0", "attributes": {"unit_of_measurement": "W"}}
                  for entity in ("sensor.haus", "sensor.elwa_ist", "sensor.ac_leistung")}
        devices = [DEVICES[0], DEVICES[4]]
        sync = InsightSync(options, devices, resolve_host=host, database=url.path.lstrip("/"))
        now = datetime.now(UTC)
        price = parse_price_curve(price_state(start=now.replace(minute=0, second=0, microsecond=0)
                                              - timedelta(hours=1), count=96), "auto", now)
        status = await sync.tick(now, states, price, None, {})
        assert status["verbunden"], status["grund"]
        managed = {row[0]: row[1] for row in await (await admin.execute(
            "SELECT entity_id, verwaltet_von FROM skytech.sensor")).fetchall()}
        assert managed["sensor.haus"] == "hems" and managed["hems.grundlast_w"] == "hems"
        assert (await (await admin.execute("SELECT count(*) FROM skytech.prognose_lauf")).fetchone())[0] == 1

        # Minutenwerte direkt anlegen (die rechnet sonst der Collector von Data Insight).
        slot = (now - timedelta(minutes=45)).replace(second=0, microsecond=0)
        slot = slot.replace(minute=slot.minute - slot.minute % 15)
        ids = {row[0]: row[1] for row in await (await admin.execute(
            "SELECT entity_id, id FROM skytech.sensor")).fetchall()}
        for entity, value in (("sensor.haus", 900.0), ("sensor.elwa_ist", 0.0), ("sensor.ac_leistung", -300.0)):
            for minute in range(15):
                await admin.execute(
                    "INSERT INTO skytech.messwert_1min (zeit, sensor_id, mittel, minimum, maximum, letzter, anzahl, "
                    "abdeckung_s) VALUES (%s, %s, %s, %s, %s, %s, 1, 60)",
                    (slot + timedelta(minutes=minute), ids[entity], value, value, value, value))
        sync._last_reconcile = None
        sync._grundlast_from = slot              # sonst begänne das Nachrechnen 10 Tage zurück
        status = await sync.tick(now, states, price, None, {})
        assert status["grundlast_grund"] is None
        rows = await (await admin.execute(
            "SELECT zeit, wert FROM skytech.messwert m JOIN skytech.sensor s ON s.id = m.sensor_id "
            "WHERE s.entity_id = 'hems.grundlast_w' ORDER BY zeit")).fetchall()
        # Je Minute: 900 − 0 − (−300), für alle 15 Minuten des Slots.
        assert [(row[0], row[1]) for row in rows if slot <= row[0] < slot + timedelta(minutes=15)] == [
            (slot + timedelta(minutes=i), 1200.0) for i in range(15)]
        # Fortschritt nur aus echten Rohwerten: eine Minute mit anzahl = 0 zählt nicht.
        for minute, count in ((slot, 1), (slot + timedelta(minutes=1), 0)):
            await admin.execute(
                "INSERT INTO skytech.messwert_1min (zeit, sensor_id, mittel, minimum, maximum, letzter, anzahl, "
                "abdeckung_s) VALUES (%s, %s, 1200, 1200, 1200, 1200, %s, 60) ON CONFLICT DO NOTHING",
                (minute, ids["hems.grundlast_w"], count))
        assert await sync.client.last_minute("grundlast") == slot

        # Phase P5: Verbrauchsprognose mit Band, Auswertung ohne Werte, eigene Reihen als 1/0.
        start = slot + timedelta(minutes=60)
        await sync.client.write_run(
            kind="verbrauch", source="hems:profil_v1", created=now, raster_min=15, valid_from=start,
            valid_until=start + timedelta(hours=1), unit="W", method="profil_v1",
            details={"ist_rolle": "grundlast", "historie_tage": 14, "parameter": {}},
            times=[start + timedelta(minutes=15 * i) for i in range(4)], values=[400.0] * 4,
            p10=[300.0] * 4, p90=[500.0] * 4)
        await sync.client.write_run(
            kind="auswertung", source="hems:kennzahlen", created=now, raster_min=15, valid_from=start,
            valid_until=start + timedelta(hours=1), unit="kWh", method="kennzahlen_v1",
            details={"reichweite_h": 3.5}, times=[], values=[])
        kinds = sorted(row[0] for row in await (await admin.execute(
            "SELECT art FROM skytech.prognose_lauf")).fetchall())
        assert kinds == ["auswertung", "preis", "verbrauch"]
        result = analyse_for_integration()
        await sync.record(slot, result)
        await sync.record(slot + timedelta(minutes=1), result)
        rows = await (await admin.execute(
            "SELECT s.entity_id, m.wert FROM skytech.messwert m JOIN skytech.sensor s ON s.id = m.sensor_id "
            "WHERE s.entity_id IN ('hems.nutzbar_kwh', 'hems.netzladen_zulaessig')")).fetchall()
        assert sorted(rows) == [("hems.netzladen_zulaessig", 0.0)] * 2 + [("hems.nutzbar_kwh", 2.5)] * 2
        # Zählerrolle: Data Insight kennzeichnet den Sensor als Zähler.
        sync.options = {**sync.options, "pv_actual_energy_entity": "sensor.pv_zaehler"}
        sync._last_reconcile = None
        await sync.tick(now, {**states, "sensor.pv_zaehler": {"state": "1", "attributes": {"unit_of_measurement": "kWh"}}},
                        price, None, {})
        assert (await (await admin.execute(
            "SELECT energie_zaehler FROM skytech.sensor WHERE entity_id = 'sensor.pv_zaehler'")).fetchone())[0] is True
        await sync.close()
        await admin.close()

    asyncio.run(run())


def analyse_for_integration():
    return {"speicher": {"nutzbar_kwh": 2.5}, "kennzahlen": {},
            "netzladen": {"zulaessig": False, "je_speicher": []}}
