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
    return [start + timedelta(minutes=15 * i) for i in range(count)]


def test_grundlast_formula_and_gaps():
    slots = _slots()
    full = 900.0
    values = {
        "hausverbrauch": {slot: RoleValue(12.0, full, "W") for slot in slots},
        "verbraucher_ist:heizstab": {slot: RoleValue(0.0, full, "W") for slot in slots},
        "verbraucher_schaltzustand:heizlufter_2": {slot: RoleValue(0.5, full, None) for slot in slots},
        "speicher_leistung:acspeicher1": {slot: RoleValue(-1101.0, full, "W") for slot in slots},
    }
    values["hausverbrauch"][slots[1]] = RoleValue(12.0, 300.0, "W")            # lückenhaft
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
        self.fail = None

    async def connect(self):
        if self.fail:
            raise InsightError(self.fail)

    async def close(self):
        pass

    async def ensure_sensor(self, entity, attribute, name, category, quantity, unit, source):
        if entity not in self.sensors:
            self.sensors[entity] = [len(self.sensors) + 1, True, True]
        self.sensors[entity][1] = True
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

    async def last_slot(self, role):
        return None

    async def role_values(self, roles, start, end):
        return {role: self.role_data.get(role, {}) for role in roles}

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

    # Grundlast: ohne Werte nichts, mit vollständigen Werten genau die abgeschlossenen Slots.
    assert sync.client.values == []
    slot = datetime(2026, 10, 12, 17, 30, tzinfo=UTC)
    data = {role: {slot: RoleValue(0.0, 900.0, "W")} for role in
            ("verbraucher_ist:heizstab", "verbraucher_ist:wallbox_1", "verbraucher_ist:heizlufter_1",
             "speicher_leistung:acspeicher1")}
    data["hausverbrauch"] = {slot: RoleValue(450.0, 900.0, "W")}
    data["verbraucher_schaltzustand:heizlufter_2"] = {slot: RoleValue(0.0, 900.0, None)}
    sync.client.role_data = data
    asyncio.run(sync.tick(NOW, STATES, None, None, {}))
    sensor_id, times, values = sync.client.values[0]
    assert sensor_id == sync.client.sensors["hems.grundlast_w"][0] and times == [slot] and values == [450.0]
    assert sync.status.grundlast_bis == "12.10.2026 19:45"


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
        status = await sync.tick(now, states, price, None, {})
        assert status["grundlast_grund"] is None
        rows = await (await admin.execute(
            "SELECT zeit, wert FROM skytech.messwert m JOIN skytech.sensor s ON s.id = m.sensor_id "
            "WHERE s.entity_id = 'hems.grundlast_w' ORDER BY zeit")).fetchall()
        assert (slot, 1200.0) in [(row[0], row[1]) for row in rows]   # 900 − 0 − (−300)

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
        await sync.record(slot + timedelta(minutes=15), result)
        rows = await (await admin.execute(
            "SELECT s.entity_id, m.wert FROM skytech.messwert m JOIN skytech.sensor s ON s.id = m.sensor_id "
            "WHERE s.entity_id IN ('hems.nutzbar_kwh', 'hems.netzladen_zulaessig')")).fetchall()
        assert sorted(rows) == [("hems.netzladen_zulaessig", 0.0), ("hems.nutzbar_kwh", 2.5)]
        await sync.close()
        await admin.close()

    asyncio.run(run())


def analyse_for_integration():
    return {"speicher": {"nutzbar_kwh": 2.5}, "kennzahlen": {},
            "netzladen": {"zulaessig": False, "je_speicher": []}}
