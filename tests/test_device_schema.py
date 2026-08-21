"""Contract-Tests für das additive HEMS-Geräteschema des Energy Pilot."""

from main import _build_device_controls_schema


def _schema():
    return _build_device_controls_schema(
        [
            {
                "name": "heizstab",
                "label": "Heizstab",
                "class": "controllable",
                "actual_power_entity": "sensor.elwa_istleistung",
                "allowed_modes": "auto,nur_heizen",
            },
            {
                "name": "heizlufter_1",
                "class": "binary",
                "switch_entity": "switch.heizlufter",
                "allowed_modes": "nur_heizen",
            },
        ],
        residual_power_entity="sensor.ueberschuss",
        interval_s=3,
    )


def test_schema_keeps_legacy_shape_and_adds_explicit_metadata():
    schema = _schema()
    assert isinstance(schema, list)
    global_group, heater, fan = schema
    assert global_group["label"] == "Global"
    assert global_group["schema_version"] == 2
    assert global_group["control_policy"] == "pv_surplus_only"
    assert global_group["residual_power_entity"] == "sensor.ueberschuss"
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
    }
    assert by_key["hoch_regelzeit_s"]["planning_relevant"] is False


def test_schema_ignores_unknown_device_classes():
    schema = _build_device_controls_schema(
        [{"name": "x", "class": "future"}],
        residual_power_entity="sensor.ueberschuss",
        interval_s=3,
    )
    assert [group["name"] for group in schema] == ["global"]


def test_schema_kennt_battery_zweig():
    """Ohne battery-Zweig fehlte der Speicher im Steuerung-Tab und im
    Energy-Pilot-Vertrag."""
    schema = _build_device_controls_schema(
        [{
            "name": "acspeicher1",
            "label": "AC-Speicher",
            "class": "battery",
            "soc_entity": "sensor.acspeicher1_soc",
            "charge_power_entity": "sensor.acspeicher1_lade_w",
            "discharge_power_entity": "sensor.acspeicher1_entlade_w",
            "capacity_kwh": 10.0,
            "allowed_modes": "manuell,nur_laden",
        }],
        residual_power_entity="sensor.ueberschuss",
        interval_s=3,
    )
    battery = schema[1]
    assert battery["class"] == "battery"
    assert battery["output_unit"] == "watt"
    assert battery["soc_entity"] == "sensor.acspeicher1_soc"
    assert battery["capacity_kwh"] == 10.0
    # Ein signierter Sollwert plus Betriebsart (D-B20)
    assert battery["request_entity"] == "input_number.ems_acspeicher1_anforderung_leistung_w"
    assert battery["request_sign"] == "positiv_laden"
    assert battery["mode_entity"] == "input_select.ems_acspeicher1_anforderung_betriebsart"

    by_key = {item["key"]: item for item in battery["items"]}
    assert by_key["entlade_prioritat"]["entity"] == "input_number.ems_acspeicher1_entlade_prioritat"
    assert by_key["entlade_prioritat"]["planning_relevant"] is True
    assert by_key["soc_min_prozent"]["unit"] == "%"
    assert by_key["max_entladeleistung_w"]["role"] == "technical_constraint"


def test_globales_schema_kennt_entlade_abschlag():
    """Der Abschlag ist eine Systemgrösse und liegt deshalb global – im
    Namensraum ems_ac_speicher_*, nicht ems_speicher_*."""
    global_group = _schema()[0]
    by_key = {item["key"]: item for item in global_group["items"]}
    assert by_key["ac_speicher_entlade_abschlag_w"]["entity"] == (
        "input_number.ems_ac_speicher_entlade_abschlag_w"
    )
