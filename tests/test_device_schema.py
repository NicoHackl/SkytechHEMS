"""Contract-Tests für das additive HEMS-Geräteschema des Energy Pilot.

Das Schema wird aus BEREITS VALIDIERTEN Gerätekonfigurationen gebaut – derselben
Menge, die der Controller registriert. Die Tests gehen deshalb durch
configuration.validate_options(), statt rohe Dicts zu stellen.
"""

from configuration import validate_options
from main import _build_device_controls_schema

from test_run_cycle import BIN_FALLBACKS, CTRL_FALLBACKS


def _valid(devices):
    options = {"devices": devices}
    if any(device.get("class") == "battery" for device in devices):
        options["battery_residual_power_entity"] = "sensor.hausleistungsbilanz"
    result = validate_options(options)
    assert not result.field_errors, result.field_errors
    return result.devices


def _schema():
    return _build_device_controls_schema(
        _valid([
            {
                "name": "heizstab",
                "label": "Heizstab",
                "class": "controllable",
                "actual_power_entity": "sensor.elwa_istleistung",
                "allowed_modes": "auto,nur_heizen",
                **CTRL_FALLBACKS,
            },
            {
                "name": "heizlufter_1",
                "class": "binary",
                "switch_entity": "switch.heizlufter",
                "allowed_modes": "nur_heizen",
                **BIN_FALLBACKS,
            },
        ]),
        residual_power_entity="sensor.ueberschuss",
        interval_s=3,
        battery_residual_power_entity="sensor.hausleistungsbilanz",
    )


def test_schema_keeps_legacy_shape_and_adds_explicit_metadata():
    schema = _schema()
    assert isinstance(schema, list)
    global_group, heater, fan = schema
    assert global_group["label"] == "Global"
    assert global_group["schema_version"] == 2
    assert global_group["control_policy"] == "pv_surplus_only"
    assert global_group["residual_power_entity"] == "sensor.ueberschuss"
    assert global_group["battery_residual_power_entity"] == "sensor.hausleistungsbilanz"
    debug = next(item for item in global_group["items"] if item["key"] == "debug_output")
    assert debug["planning_relevant"] is False

    assert heater["name"] == "heizstab"
    assert heater["class"] == "controllable"
    assert heater["entity_prefix"] == "heizstab"
    assert heater["actual_power_entity"] == "sensor.elwa_istleistung"
    assert heater["request_entity"] == "input_number.ems_heizstab_anforderung_leistung_w"
    assert heater["allowed_modes"] == ["manuell", "nur_heizen"]
    assert fan["switch_entity"] == "switch.heizlufter"


def test_schema_items_have_stable_semantics_without_suffix_inference():
    heater = _schema()[1]
    by_key = {item["key"]: item for item in heater["items"]}
    assert by_key["max_technisch"] == {
        "entity": "input_number.ems_heizstab_max_technisch_w",
        "label": "Max. Leistung",
        "key": "max_technisch",
        "kind": "number",
        "role": "technical_constraint",
        "planning_relevant": True,
        "unit": "W",
        # Additiv seit D-061: Eingabegrenzen für den HEMS-internen Ersatzwert.
        "internal_editable": True,
        "min": 0,
        "integer": False,
        "step": 1,
    }
    assert by_key["hoch_regelzeit_s"]["planning_relevant"] is False


def test_schema_kennt_zwang_helfer():
    """D-053: beide Zwang-Helfer sind Nutzersteuerung; die Leistung ist immer Watt."""
    heater, fan = _schema()[1:]
    heater_keys = {item["key"]: item for item in heater["items"]}
    assert heater_keys["force"] == {
        "entity": "input_boolean.ems_heizstab_force", "label": "Zwang", "key": "force",
        "kind": "bool", "role": "user_control", "planning_relevant": True,
        "internal_editable": False,
    }
    assert heater_keys["force_leistung_w"] == {
        "entity": "input_number.ems_heizstab_force_leistung_w", "label": "Zwangsleistung",
        "key": "force_leistung_w", "kind": "number", "role": "user_control",
        "planning_relevant": True, "unit": "W",
        "internal_editable": False, "min": 0, "integer": False, "step": 1,
    }
    fan_keys = {item["key"] for item in fan["items"]}
    assert "force" in fan_keys and "force_leistung_w" not in fan_keys


def test_schema_kennt_speicherdeckung_je_verbraucher():
    """D-060: Opt-in am Verbraucher, für regelbare und binäre Geräte gleich."""
    heater, fan = _schema()[1:]
    for group, prefix in ((heater, "heizstab"), (fan, "heizlufter_1")):
        by_key = {item["key"]: item for item in group["items"]}
        assert by_key["aus_speicher_decken"] == {
            "entity": f"input_boolean.ems_{prefix}_aus_speicher_decken",
            "label": "Aus Speicher decken", "key": "aus_speicher_decken",
            "kind": "bool", "role": "user_preference", "planning_relevant": True,
            "internal_editable": True,
        }


def test_zwangsleistung_bleibt_im_ampere_modus_watt():
    wallbox = _build_device_controls_schema(
        _valid([{
            "name": "wallbox_1", "class": "controllable", "entity_prefix": "wallbox",
            "actual_power_entity": "sensor.wb", "allowed_modes": "auto",
            "output_unit": "ampere", "phases": "1,3", **CTRL_FALLBACKS,
        }]),
        residual_power_entity="sensor.ueberschuss", interval_s=3,
    )[1]
    entities = {item["entity"] for item in wallbox["items"]}
    assert "input_number.ems_wallbox_force_leistung_w" in entities
    assert "input_number.ems_wallbox_force_leistung_a" not in entities
    assert "input_number.ems_wallbox_max_technisch_a" in entities


def test_speicher_hat_keinen_zwang_helfer():
    battery = _build_device_controls_schema(
        _valid([{
            "name": "acspeicher1", "class": "battery",
            "soc_entity": "sensor.acspeicher1_soc",
            "charge_power_entity": "sensor.acspeicher1_lade_w",
            "discharge_power_entity": "sensor.acspeicher1_entlade_w",
            "available_charge_power_w": 1500, "available_discharge_power_w": 2000,
            "capacity_kwh": 10.0, "allowed_modes": "manuell,nur_laden",
        }]),
        residual_power_entity="sensor.ueberschuss", interval_s=3,
        battery_residual_power_entity="sensor.hausleistungsbilanz",
    )[1]
    assert not any(item["key"].startswith("force") for item in battery["items"])
    by_key = {item["key"]: item for item in battery["items"]}
    assert "aus_speicher_decken" not in by_key
    assert by_key["uberschussverbraucher_versorgen"]["entity"] == \
        "input_boolean.ems_acspeicher1_uberschussverbraucher_versorgen"
    assert by_key["uberschussverbraucher_versorgen"]["kind"] == "bool"


def test_unbekannte_klasse_erreicht_das_schema_nicht():
    """Die Validierung sortiert sie vorher aus – der Builder sieht sie nie."""
    result = validate_options({"devices": [{"name": "x", "class": "future"}]})
    assert result.devices == []
    assert result.inactive_devices[0].name == "x"
    schema = _build_device_controls_schema(
        result.devices, residual_power_entity="sensor.ueberschuss", interval_s=3)
    assert [group["name"] for group in schema] == ["global"]


def test_schema_kennt_battery_zweig():
    """Ohne battery-Zweig fehlte der Speicher im Steuerung-Tab und im
    Energy-Pilot-Vertrag."""
    schema = _build_device_controls_schema(
        _valid([{
            "name": "acspeicher1",
            "label": "AC-Speicher",
            "class": "battery",
            "soc_entity": "sensor.acspeicher1_soc",
            "charge_power_entity": "sensor.acspeicher1_lade_w",
            "discharge_power_entity": "sensor.acspeicher1_entlade_w",
            "available_charge_power_w": 1500,
            "available_discharge_power_w": 2000,
            "capacity_kwh": 10.0,
            "allowed_modes": "manuell,nur_laden",
        }]),
        residual_power_entity="sensor.ueberschuss",
        interval_s=3,
        battery_residual_power_entity="sensor.hausleistungsbilanz",
    )
    battery = schema[1]
    assert battery["class"] == "battery"
    assert battery["output_unit"] == "watt"
    assert battery["soc_entity"] == "sensor.acspeicher1_soc"
    assert battery["available_charge_power_w"] == 1500.0
    assert battery["available_discharge_power_w"] == 2000.0
    assert battery["capacity_kwh"] == 10.0
    # Ein signierter Sollwert plus Betriebsart (D-B20)
    assert battery["request_entity"] == "input_number.ems_acspeicher1_anforderung_leistung_w"
    assert battery["request_sign"] == "positiv_laden"
    assert battery["mode_entity"] == "input_select.ems_acspeicher1_anforderung_betriebsart"

    by_key = {item["key"]: item for item in battery["items"]}
    assert by_key["entlade_prioritat"]["entity"] == "input_number.ems_acspeicher1_entlade_prioritat"
    assert by_key["entlade_prioritat"]["planning_relevant"] is True
    assert by_key["soc_min_prozent"]["unit"] == "%"
    assert by_key["min_entladeleistung_w"]["role"] == "technical_constraint"

    # Entfallene Helfer dürfen im Steuerschema nicht mehr auftauchen: die
    # physische Grenze kommt aus den statischen available_*_w-Werten, Notstromreserve,
    # Drosselband und Entlade-Sofort-Schwelle gibt es nicht mehr, Hysterese und
    # Umschaltsperre sind statische Add-on-Felder.
    assert not {
        "max_ladeleistung_w", "max_entladeleistung_w", "soc_reserve_prozent",
        "soc_taper_band_prozent", "soc_max_hysterese_prozent",
        "entlade_sofort_schwelle_w", "min_umschaltzeit_s",
    } & set(by_key)


def test_globales_schema_kennt_entlade_abschlag():
    """Der Abschlag ist eine Systemgrösse und liegt deshalb global – im
    Namensraum ems_ac_speicher_*, nicht ems_speicher_*."""
    global_group = _schema()[0]
    by_key = {item["key"]: item for item in global_group["items"]}
    assert by_key["ac_speicher_entlade_abschlag_w"]["entity"] == (
        "input_number.ems_ac_speicher_entlade_abschlag_w"
    )


# ---------------------------------------------------------------------------
# D-061: HEMS-interne Ersatzwerte
# ---------------------------------------------------------------------------

GATE_KEYS = {"pv_regelung_aktiv", "freigabe", "technische_freigabe", "force", "force_leistung_w"}


def _battery_schema():
    return _build_device_controls_schema(
        _valid([{
            "name": "acspeicher1", "class": "battery", "soc_entity": "sensor.soc",
            "power_entity": "sensor.leistung", "power_sign": "positiv_laden",
            "available_charge_power_w": 3000, "available_discharge_power_w": 3000,
            "soc_max_hysteresis_percent": 2, "direction_switch_delay_s": 5,
        }]),
        residual_power_entity="sensor.ueberschuss",
        interval_s=3,
        battery_residual_power_entity="sensor.hausleistungsbilanz",
        available_modes=["manuell", "nur_laden"],
    )


def test_nur_freigaben_und_zwang_sind_nicht_intern_einstellbar():
    for group in [*_schema(), *_battery_schema()]:
        for item in group["items"]:
            assert item["internal_editable"] is (item["key"] not in GATE_KEYS), item["entity"]


def test_interne_eingabe_kennt_grenzen_und_optionen():
    global_group, battery = _battery_schema()
    regelmodus = next(item for item in global_group["items"] if item["key"] == "regelmodus")
    # Nur global aktivierte normale Modi plus die beiden Sondermodi.
    assert regelmodus["options"] == ["auto", "manuell", "nur_laden", "aus"]
    by_key = {item["key"]: item for item in battery["items"]}
    assert by_key["modus"]["options"] == ["auto", "manuell", "aus"]
    assert by_key["betriebsart"]["options"] == ["auto", "nur_laden", "nur_entladen", "standby"]
    assert by_key["soc_min_prozent"]["min"] == 0 and by_key["soc_min_prozent"]["max"] == 100
    assert by_key["prioritat"]["integer"] is True
    assert by_key["entlade_prioritat"]["integer"] is True
    assert by_key["reserve_w"]["integer"] is False and "max" not in by_key["reserve_w"]
