"""Vertragstests der Kartendaten für die Skytech Power Flow Card (D-046).

Die Nutzlasten sind in `vertrag_powerflow_card_hems/kontrakt.md` Feld für Feld
festgeschrieben. Geprüft wird deshalb der reine Payload-Builder, nicht der
HTTP-Weg: er ist die Stelle, an der der Vertrag entsteht.

Eingaben laufen erst durch `validate_options()` – gebaut wird ausschließlich aus
gültigen Gerätekonfigurationen, derselben Menge, die der Controller registriert.
"""

import asyncio

import flow_publisher as fp
from configuration import normalize_options, validate_options
from main import _build_device_controls_schema

from test_run_cycle import BIN_FALLBACKS, CTRL_FALLBACKS

NOW = "23.08.2026 18:04:12"

BAT_FIELDS = {
    "soc_entity": "sensor.acspeicher1_soc",
    "charge_power_entity": "sensor.acspeicher1_laden",
    "discharge_power_entity": "sensor.acspeicher1_entladen",
    "available_charge_power_w": 1500,
    "available_discharge_power_w": 1500,
    "capacity_kwh": 12.8,
}

ALL_DEVICES = [
    {
        "name": "heizstab", "label": "Heizstab", "class": "controllable",
        "actual_power_entity": "sensor.elwa_istleistung",
        "allowed_modes": "manuell", "flow_icon": "mdi:radiator",
        **CTRL_FALLBACKS,
    },
    {
        "name": "wallbox_1", "label": "Wallbox", "class": "controllable",
        "entity_prefix": "wallbox", "actual_power_entity": "sensor.wallbox_istleistung",
        "output_unit": "ampere", "phases": "1,3",
        "technical_minimum": 6, "technical_maximum": 16,
        "increase_delay_s": 0, "decrease_delay_s": 0,
        "maximum_step_change": 2, "minimum_step_change": 1,
        "allowed_modes": "manuell",
    },
    {
        "name": "heizlufter_1", "label": "Heizlüfter 1", "class": "binary",
        "switch_entity": "switch.heizlufter", "allowed_modes": "manuell",
        **BIN_FALLBACKS,
    },
    {
        "name": "acspeicher1", "label": "AC-Speicher", "class": "battery",
        "allowed_modes": "manuell", **BAT_FIELDS,
    },
]

STANDARD = {
    "flow_publish": True,
    "flow_pv_power_entities": [{"entity": "sensor.ertrag_hausdach"}],
    "flow_grid_power_entity": "sensor.netz",
    "flow_house_power_entity": "sensor.haus",
    "flow_battery_label": "E3DC",
    "flow_battery_soc_entity": "sensor.e3dc_soc",
    "flow_battery_charge_power_entity": "sensor.e3dc_laden",
    "flow_battery_discharge_power_entity": "sensor.e3dc_entladen",
}


def _options(devices=None, **globals_):
    raw = {"devices": list(devices if devices is not None else ALL_DEVICES)}
    if any(device.get("class") == "battery" for device in raw["devices"]):
        raw["battery_residual_power_entity"] = "sensor.hausleistungsbilanz"
    raw.update(globals_)
    result = validate_options(raw)
    assert not result.field_errors, result.field_errors
    return result


def _config(devices=None, **globals_):
    result = _options(devices, **globals_)
    schema = _build_device_controls_schema(
        result.devices,
        residual_power_entity=result.options["residual_power_entity"],
        interval_s=3,
        battery_residual_power_entity=result.options["battery_residual_power_entity"],
    )
    return fp.build_config_payload(result.options, schema, "2.0.1", NOW)


def _by_id(payload):
    return {device["id"]: device for device in payload["devices"]}


class FakeHA:
    """Merkt sich, was geschrieben wurde. `fail` erzwingt einen Schreibfehler."""

    def __init__(self, fail=False):
        self.writes = []
        self.fail = fail

    async def set_state(self, entity_id, state, attributes=None):
        if self.fail:
            return False
        self.writes.append((entity_id, state, attributes or {}))
        return True


def _publish(publisher, ha, *, options, status=None, states=None, cycle_count=1):
    schema = _build_device_controls_schema(
        validate_options({"devices": []}).devices,
        residual_power_entity="sensor.ueberschuss", interval_s=3,
    )
    return asyncio.run(publisher.publish(
        options=options, controls_schema=schema,
        status=status if status is not None else _status(),
        states=states if states is not None else {},
        cycle_count=cycle_count, addon_version="2.0.1", now=NOW,
    ))


def _status(devices=None):
    return {
        "ems_enabled": True, "global_mode": "manuell", "hard_lockout": False,
        "residual_w": 1840.0, "hems_last_w": 1400.0, "hausdefizit_w": 0.0,
        "pool_w": 3240.0, "devices": devices or [],
    }


# ---------------------------------------------------------------------------
# Konfigurationsnutzlast
# ---------------------------------------------------------------------------

def test_konfigurationsnutzlast_enthaelt_alle_geraeteklassen():
    devices = _by_id(_config(**STANDARD))
    assert set(devices) == {"heizstab", "wallbox_1", "heizlufter_1", "acspeicher1"}
    assert [d["class"] for d in _config(**STANDARD)["devices"]] == [
        "controllable", "controllable", "binary", "battery"]


def test_power_kind_wird_aus_geraeteklasse_und_einheit_abgeleitet():
    devices = _by_id(_config(**STANDARD))
    assert devices["heizstab"]["power_kind"] == "watt"
    assert devices["wallbox_1"]["power_kind"] == "ampere"
    assert devices["heizlufter_1"]["power_kind"] == "binary_static"
    assert devices["acspeicher1"]["power_kind"] == "battery_split"


def test_steuerhelfer_stehen_ausgeschrieben_in_der_nutzlast():
    control = _by_id(_config(**STANDARD))["heizstab"]["control"]
    assert control == {
        "freigabe": "input_boolean.ems_heizstab_freigabe",
        "technische_freigabe": "input_boolean.ems_heizstab_technische_freigabe",
        "modus": "input_select.ems_heizstab_modus",
        "prioritat": "input_number.ems_heizstab_prioritat",
        "anforderung": "input_number.ems_heizstab_anforderung_leistung_w",
    }


def test_phasenhelfer_nur_bei_umschaltbarer_ampere_regelung():
    devices = _by_id(_config(**STANDARD))
    assert devices["wallbox_1"]["phases_entity"] == "input_number.ems_wallbox_anzahl_phase"
    assert devices["wallbox_1"]["phases_fallback"] == 3
    assert devices["heizstab"]["phases_entity"] == ""


def test_revision_bleibt_stabil_bei_unveraendertem_zustand():
    assert _config(**STANDARD)["revision"] == _config(**STANDARD)["revision"]


def test_revision_ignoriert_zeitstempel():
    result = _options(**STANDARD)
    schema = _build_device_controls_schema(
        result.devices, residual_power_entity=result.options["residual_power_entity"],
        interval_s=3,
        battery_residual_power_entity=result.options["battery_residual_power_entity"])
    early = fp.build_config_payload(result.options, schema, "2.0.1", "23.08.2026 18:04:12")
    later = fp.build_config_payload(result.options, schema, "2.0.1", "23.08.2026 19:00:00")
    assert early["revision"] == later["revision"]
    assert early["erzeugt_am"] != later["erzeugt_am"]


def test_geraet_mit_flow_show_false_fehlt_in_der_nutzlast():
    devices = [dict(device) for device in ALL_DEVICES]
    devices[0]["flow_show"] = False
    assert "heizstab" not in _by_id(_config(devices, **STANDARD))


def test_inaktives_geraet_fehlt_in_der_nutzlast():
    # Ein Gerät ohne Pflichtfeld wird beim Start übersprungen. Es steht dann
    # weder in devices[] noch im Steuerschema – die Karte darf es nicht zeigen.
    raw = {"devices": list(ALL_DEVICES) + [{"name": "kaputt", "class": "binary"}]}
    raw["battery_residual_power_entity"] = "sensor.hausleistungsbilanz"
    raw.update(STANDARD)
    result = validate_options(raw)
    assert result.inactive_devices
    schema = _build_device_controls_schema(
        result.devices, residual_power_entity=result.options["residual_power_entity"],
        interval_s=3,
        battery_residual_power_entity=result.options["battery_residual_power_entity"])
    payload = fp.build_config_payload(result.options, schema, "2.0.1", NOW)
    assert "kaputt" not in _by_id(payload)


def test_leere_flow_konfiguration_erzeugt_gueltige_leere_nutzlast():
    payload = _config([])
    assert payload["schema_version"] == 1
    assert payload["devices"] == []
    assert payload["standard"]["pv_power_entities"] == []
    assert payload["standard"]["batterie"] is None
    assert payload["revision"]


def test_reihenfolge_folgt_der_geraeteliste():
    payload = _config(**STANDARD)
    assert [d["reihenfolge"] for d in payload["devices"]] == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Statusnutzlast
# ---------------------------------------------------------------------------

def test_statusnutzlast_liefert_rueckfallleistung_je_geraeteklasse():
    status = _status([
        {"id": "heizstab", "type": "controllable", "actual_w": 1400.0,
         "eligible": True, "runtime_active": True},
        {"id": "heizlufter_1", "type": "binary", "power_w": 1500.0, "final_on": True,
         "eligible": True, "runtime_active": True},
        {"id": "heizlufter_2", "type": "binary", "power_w": 1500.0, "final_on": False,
         "eligible": True, "runtime_active": True},
        {"id": "acspeicher1", "type": "battery", "netto_w": -800.0,
         "eligible": True, "runtime_active": True},
    ])
    devices = fp.build_status_payload(status, 412, NOW)["devices"]
    assert devices["heizstab"]["leistung_w"] == 1400.0
    assert devices["heizlufter_1"]["leistung_w"] == 1500.0
    assert devices["heizlufter_2"]["leistung_w"] == 0.0
    assert devices["acspeicher1"]["leistung_w"] == -800.0


def test_binaeres_geraet_bevorzugt_die_gemessene_leistung():
    status = _status([
        {"id": "heizlufter_1", "type": "binary", "power_w": 1500.0,
         "power_actual_w": 1320.0, "final_on": True,
         "eligible": True, "runtime_active": True},
    ])
    devices = fp.build_status_payload(status, 1, NOW)["devices"]
    assert devices["heizlufter_1"]["leistung_w"] == 1320.0


def test_kennzahlen_des_zyklus_stehen_im_status():
    payload = fp.build_status_payload(_status(), 412, NOW)
    assert payload["pool_w"] == 3240.0
    assert payload["cycle_count"] == 412
    assert payload["last_cycle_at"] == NOW
    assert payload["global_mode"] == "manuell"


def test_geraet_ohne_freigabe_gilt_nicht_als_aktiv():
    # `runtime_active` im Vertrag heißt „regelt gerade mit". Im Code ist das
    # eligible UND runtime_active – ein gesperrtes Gerät ist technisch heil.
    status = _status([
        {"id": "heizstab", "type": "controllable", "actual_w": 0.0,
         "eligible": False, "runtime_active": True, "source": "user",
         "entity_diagnostics": {
             "input_boolean.ems_heizstab_freigabe": {"role": "freigabe", "state": "off"},
             "input_boolean.ems_heizstab_technische_freigabe":
                 {"role": "technische_freigabe", "state": "on"},
         }},
    ])
    entry = fp.build_status_payload(status, 1, NOW)["devices"]["heizstab"]
    assert entry["runtime_active"] is False
    assert entry["inactive_reasons"] == ["Freigabe aus"]


def test_inaktive_gruende_werden_als_deutscher_text_geliefert():
    status = _status([
        {"id": "heizstab", "type": "controllable", "actual_w": 0.0,
         "eligible": True, "runtime_active": False,
         "inactive_reasons": ["schreibziel_fehlt"]},
    ])
    entry = fp.build_status_payload(status, 1, NOW)["devices"]["heizstab"]
    assert entry["inactive_reasons"] == ["Schreibziel fehlt"]


def test_unbekannter_grund_bleibt_unveraendert_sichtbar():
    # Ein neuer Token darf nicht stillschweigend verschwinden – sonst stünde
    # ein inaktives Gerät ohne jede Begründung auf der Karte.
    status = _status([
        {"id": "heizstab", "type": "controllable", "eligible": True,
         "runtime_active": False, "inactive_reasons": ["neuer_grund"]},
    ])
    entry = fp.build_status_payload(status, 1, NOW)["devices"]["heizstab"]
    assert entry["inactive_reasons"] == ["neuer_grund"]


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------

def test_publish_deaktiviert_schreibt_nichts():
    ha = FakeHA()
    _publish(fp.FlowPublisher(ha), ha, options=normalize_options({}))
    assert ha.writes == []


def test_konfiguration_wird_nur_einmal_geschrieben():
    ha = FakeHA()
    publisher = fp.FlowPublisher(ha)
    options = _options(**STANDARD).options
    states = {fp.CONFIG_ENTITY_ID: {"state": "x", "attributes": {}}}
    _publish(publisher, ha, options=options, states=states)
    first = [entity for entity, _, _ in ha.writes]
    _publish(publisher, ha, options=options, states=states)
    written = [entity for entity, _, _ in ha.writes]
    assert first.count(fp.CONFIG_ENTITY_ID) == 1
    assert written.count(fp.CONFIG_ENTITY_ID) == 1
    assert written.count(fp.STATUS_ENTITY_ID) == 2


def test_konfiguration_wird_neu_geschrieben_wenn_entitaet_fehlt():
    # Per POST /api/states erzeugte Entitäten überleben keinen HA-Neustart.
    ha = FakeHA()
    publisher = fp.FlowPublisher(ha)
    options = _options(**STANDARD).options
    _publish(publisher, ha, options=options, states={})
    _publish(publisher, ha, options=options, states={})
    written = [entity for entity, _, _ in ha.writes]
    assert written.count(fp.CONFIG_ENTITY_ID) == 2


def test_schreibfehler_bricht_den_zyklus_nicht_ab():
    ha = FakeHA(fail=True)
    publisher = fp.FlowPublisher(ha)
    _publish(publisher, ha, options=_options(**STANDARD).options)
    assert ha.writes == []
    assert publisher.last_revision == ""


def test_status_traegt_den_pool_als_zustand():
    ha = FakeHA()
    _publish(fp.FlowPublisher(ha), ha, options=_options(**STANDARD).options)
    status = next(write for write in ha.writes if write[0] == fp.STATUS_ENTITY_ID)
    assert status[1] == "3240"
    assert status[2]["unit_of_measurement"] == "W"
    assert status[2]["device_class"] == "power"


def test_warnung_ab_zwoelf_kibibyte_nutzlast():
    payload = _config(**STANDARD)
    assert fp.payload_warnings(payload) == []
    payload["devices"] = payload["devices"] * 400
    assert fp.payload_warnings(payload)


# ---------------------------------------------------------------------------
# Vorschau
# ---------------------------------------------------------------------------

def test_vorschau_meldet_ungueltige_verweise_ohne_nullwert():
    payload = _config(**STANDARD)
    states = {"sensor.netz": {"state": "-1200.0", "attributes": {}},
              "sensor.haus": {"state": "unavailable", "attributes": {}}}
    resolved = {row["pfad"]: row for row in fp.resolve_references(payload, states)}
    assert resolved["standard.grid_power_entity"]["value"] == -1200.0
    assert resolved["standard.grid_power_entity"]["valid"] is True
    assert resolved["standard.house_power_entity"]["value"] is None
    assert resolved["standard.house_power_entity"]["valid"] is False


def test_vorschau_listet_leere_felder_nicht_auf():
    paths = [path for path, _ in fp.collect_references(_config([], **STANDARD))]
    assert "standard.grid_import_entity" not in paths
    assert "standard.grid_power_entity" in paths


def test_regelintervall_steht_in_der_nutzlast():
    # Ohne diesen Wert koennte die Karte "aelter als 5 x Regelintervall"
    # nicht anwenden -- die Regel stand im Vertrag, die Groesse fehlte.
    result = _options(**STANDARD)
    schema = _build_device_controls_schema(
        result.devices, residual_power_entity=result.options["residual_power_entity"],
        interval_s=3,
        battery_residual_power_entity=result.options["battery_residual_power_entity"])
    payload = fp.build_config_payload(result.options, schema, "2.0.1", NOW, 3)
    assert payload["hems"]["interval_s"] == 3
