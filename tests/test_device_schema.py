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
