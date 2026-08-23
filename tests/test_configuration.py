"""Tests für app/configuration.py: Normalisierung, Validierung, Revision, Diff.

Diese Datei ist die Absicherung dafür, dass Oberfläche und Controller dieselbe
Antwort auf „ist dieser Geräteeintrag gültig" bekommen.
"""

import configuration as cfg


# ---------------------------------------------------------------------------
# Gültige Bausteine
# ---------------------------------------------------------------------------

def controllable(**overrides):
    device = {
        "name": "heizstab",
        "class": "controllable",
        "actual_power_entity": "sensor.heizstab_ist",
        "allowed_modes": "manuell",
        "technical_minimum": 500,
        "technical_maximum": 3000,
        "increase_delay_s": 60,
        "decrease_delay_s": 60,
        "maximum_step_change": 1000,
        "minimum_step_change": 0,
    }
    device.update(overrides)
    return device


def binary(**overrides):
    device = {
        "name": "luft",
        "class": "binary",
        "switch_entity": "switch.luft",
        "allowed_modes": "manuell",
        "power_w": 1500,
        "on_reserve_w": 200,
        "min_runtime_s": 600,
        "min_offtime_s": 300,
        "off_delay_s": 120,
    }
    device.update(overrides)
    return device


def battery(**overrides):
    device = {
        "name": "acspeicher1",
        "class": "battery",
        "allowed_modes": "manuell",
        "soc_entity": "sensor.acspeicher1_soc",
        "charge_power_entity": "sensor.acspeicher1_ladeleistung",
        "discharge_power_entity": "sensor.acspeicher1_entladeleistung",
        "available_charge_power_w": 1500,
        "available_discharge_power_w": 1500,
    }
    device.update(overrides)
    return device


def options(*devices, **globals_):
    raw = {"devices": list(devices)}
    raw.update(globals_)
    if any(device.get("class") == "battery" for device in raw["devices"]):
        raw.setdefault("battery_residual_power_entity", "sensor.hausleistungsbilanz")
    return raw


# ---------------------------------------------------------------------------
# Modus-Normalisierung
# ---------------------------------------------------------------------------

def test_alter_modus_auto_wird_auf_manuell_abgebildet():
    assert cfg.parse_modes("auto,nur_heizen") == ["manuell", "nur_heizen"]


def test_duplikate_werden_entfernt_und_reihenfolge_ist_stabil():
    assert cfg.serialize_modes(cfg.parse_modes("nur_laden,manuell,manuell,auto")) == \
        "manuell,nur_laden"


def test_fehlendes_allowed_modes_wird_zu_manuell():
    result = cfg.normalize_options(options({"name": "x", "class": "binary"}))
    assert result["devices"][0]["allowed_modes"] == "manuell"


def test_leerer_allowed_modes_string_bleibt_leer():
    """Ausdrücklich leer heißt Nur-Energy-Pilot und darf nicht überschrieben werden."""
    result = cfg.normalize_options(options({"name": "x", "class": "binary",
                                            "allowed_modes": ""}))
    assert result["devices"][0]["allowed_modes"] == ""


def test_leere_geraeteauswahl_ist_gueltig():
    result = cfg.validate_options(options(binary(allowed_modes="")))
    assert result.valid
    assert result.devices[0]["allowed_modes"] == ""


def test_fehlendes_available_modes_ergibt_alle_normalen_modi():
    assert cfg.normalize_options({})["available_modes"] == "manuell,nur_heizen,nur_laden"


def test_geraetemodus_ausserhalb_der_globalen_auswahl_ist_ein_fehler():
    result = cfg.validate_options(options(binary(allowed_modes="nur_heizen"),
                                          available_modes="manuell"))
    assert "devices[0].allowed_modes" in result.field_errors
    assert "global nicht aktiviert" in result.field_errors["devices[0].allowed_modes"]


def test_unbekannter_globaler_modus_wird_benannt():
    result = cfg.validate_options(options(available_modes="manuell,turbo"))
    assert "turbo" in result.field_errors["available_modes"]


# ---------------------------------------------------------------------------
# Globale Felder
# ---------------------------------------------------------------------------

def test_globale_defaults_werden_gesetzt():
    result = cfg.normalize_options({})
    assert result["interval_s"] == 30
    assert result["log_level"] == "info"
    assert result["residual_power_entity"] == cfg.DEFAULT_RESIDUAL_ENTITY
    assert result["battery_residual_power_entity"] == ""
    assert result["speicher_in_residual_enthalten"] is True


def test_intervall_ausserhalb_des_bereichs_ist_ein_fehler():
    assert "interval_s" in cfg.validate_options(options(interval_s=0)).field_errors
    assert "interval_s" in cfg.validate_options(options(interval_s=301)).field_errors
    assert cfg.validate_options(options(interval_s=300)).valid


def test_post_cycle_script_muss_ein_skript_sein():
    assert cfg.validate_options(options(post_cycle_script="")).valid
    assert cfg.validate_options(options(post_cycle_script="script.hems")).valid
    assert "post_cycle_script" in cfg.validate_options(
        options(post_cycle_script="switch.hems")).field_errors


def test_leerer_ueberschuss_sensor_ist_ein_fehler():
    result = cfg.validate_options(options(residual_power_entity=""))
    assert "residual_power_entity" in result.field_errors


def test_hausleistungsbilanz_ist_ohne_ac_speicher_optional():
    result = cfg.validate_options(options(battery_residual_power_entity=""))
    assert result.valid, result.field_errors


def test_hausleistungsbilanz_ist_mit_ac_speicher_ein_pflichtfeld():
    result = cfg.validate_options(options(battery(), battery_residual_power_entity=""))
    assert "battery_residual_power_entity" in result.field_errors


def test_hausleistungsbilanz_muss_eine_sensor_entity_sein():
    result = cfg.validate_options(options(
        battery(), battery_residual_power_entity="switch.hausleistungsbilanz"))
    assert "battery_residual_power_entity" in result.field_errors


# ---------------------------------------------------------------------------
# Formel-basierte Sensorwerte (D-045)
# ---------------------------------------------------------------------------

def test_formel_defaults_sind_leer():
    result = cfg.normalize_options({})
    assert result["residual_formula_variables"] == []
    assert result["residual_formula_code"] == ""
    assert result["battery_residual_formula_variables"] == []
    assert result["battery_residual_formula_code"] == ""


def test_leere_formel_ist_gueltig_ohne_geraete():
    assert cfg.validate_options(options()).valid


def test_gueltige_formel_ist_gueltig():
    result = cfg.validate_options(options(
        residual_formula_variables=[{"name": "pv", "entity": "sensor.pv"}],
        residual_formula_code="ueberschuss = pv",
    ))
    assert result.valid, result.field_errors


def test_formel_zeilenname_muss_gueltiger_bezeichner_sein():
    result = cfg.validate_options(options(
        residual_formula_variables=[{"name": "123", "entity": "sensor.pv"}]))
    assert "residual_formula_variables[0].name" in result.field_errors


def test_formel_zeilenname_darf_kein_python_schluesselwort_sein():
    result = cfg.validate_options(options(
        residual_formula_variables=[{"name": "for", "entity": "sensor.pv"}]))
    assert "residual_formula_variables[0].name" in result.field_errors


def test_formel_zeilenname_darf_nicht_die_ausgabevariable_sein():
    result = cfg.validate_options(options(
        residual_formula_variables=[{"name": "ueberschuss", "entity": "sensor.pv"}]))
    assert "residual_formula_variables[0].name" in result.field_errors


def test_formel_zeilenname_darf_keine_whitelist_funktion_sein():
    result = cfg.validate_options(options(
        residual_formula_variables=[{"name": "abs", "entity": "sensor.pv"}]))
    assert "residual_formula_variables[0].name" in result.field_errors


def test_doppelter_formel_zeilenname_wird_erkannt():
    result = cfg.validate_options(options(residual_formula_variables=[
        {"name": "pv", "entity": "sensor.a"},
        {"name": "pv", "entity": "sensor.b"},
    ]))
    assert "residual_formula_variables[1].name" in result.field_errors


def test_formel_zeile_ohne_entity_ist_ein_fehler():
    result = cfg.validate_options(options(
        residual_formula_variables=[{"name": "pv", "entity": ""}]))
    assert "residual_formula_variables[0].entity" in result.field_errors


def test_formel_code_mit_syntaxfehler_wird_abgelehnt():
    result = cfg.validate_options(options(
        residual_formula_variables=[{"name": "pv", "entity": "sensor.pv"}],
        residual_formula_code="ueberschuss = (",
    ))
    assert "residual_formula_code" in result.field_errors


def test_formel_code_ohne_zuweisung_an_ueberschuss_wird_abgelehnt():
    result = cfg.validate_options(options(
        residual_formula_variables=[{"name": "pv", "entity": "sensor.pv"}],
        residual_formula_code="x = pv",
    ))
    assert "residual_formula_code" in result.field_errors


def test_hausbilanz_formel_muss_hausbilanz_zuweisen_nicht_ueberschuss():
    result = cfg.validate_options(options(
        battery_residual_formula_variables=[{"name": "netz", "entity": "sensor.netz"}],
        battery_residual_formula_code="ueberschuss = netz",  # falsche Ausgabevariable
    ))
    assert "battery_residual_formula_code" in result.field_errors


def test_formel_zwei_taps_haben_getrennte_namensraeume():
    """Derselbe Zeilenname ist in Überschuss und Hausbilanz unabhängig gültig."""
    result = cfg.validate_options(options(
        residual_formula_variables=[{"name": "x", "entity": "sensor.a"}],
        residual_formula_code="ueberschuss = x",
        battery_residual_formula_variables=[{"name": "x", "entity": "sensor.b"}],
        battery_residual_formula_code="hausbilanz = x",
    ))
    assert result.valid, result.field_errors


def test_formel_aenderung_deaktiviert_vorsorglich_alle_altgeraete():
    for key, value in (
        ("residual_formula_variables", [{"name": "pv", "entity": "sensor.pv"}]),
        ("residual_formula_code", "ueberschuss = pv"),
        ("battery_residual_formula_variables", [{"name": "netz", "entity": "sensor.netz"}]),
        ("battery_residual_formula_code", "hausbilanz = netz"),
    ):
        old = options(binary())
        new = dict(old)
        new[key] = value
        assert cfg.devices_needing_shutdown(old, new) == cfg.normalize_options(old)["devices"], key


# ---------------------------------------------------------------------------
# Identität und Eindeutigkeit
# ---------------------------------------------------------------------------

def test_name_muss_slug_sein():
    result = cfg.validate_options(options(binary(name="Heiz Lüfter")))
    assert "devices[0].name" in result.field_errors


def test_doppelter_name_wird_erkannt():
    result = cfg.validate_options(options(binary(), binary(switch_entity="switch.b")))
    assert "devices[1].name" in result.field_errors


def test_doppelter_prefix_wird_erkannt():
    result = cfg.validate_options(options(
        binary(name="a", entity_prefix="gleich"),
        binary(name="b", entity_prefix="gleich", switch_entity="switch.b"),
    ))
    assert "devices[1].entity_prefix" in result.field_errors


def test_prefix_faellt_auf_den_namen_zurueck():
    result = cfg.normalize_options(options(binary()))
    assert result["devices"][0]["entity_prefix"] == "luft"


def test_label_bleibt_leer_wenn_nichts_eingetragen_ist():
    """Den Anzeige-Fallback wählt der Konsument – Status und Steuerschema anders."""
    result = cfg.normalize_options(options(binary()))
    assert result["devices"][0]["label"] == ""


def test_unbekannte_klasse_wird_benannt():
    result = cfg.validate_options(options({"name": "x", "class": "toaster"}))
    assert "devices[0].class" in result.field_errors


# ---------------------------------------------------------------------------
# Bedingte Pflichtfelder je Klasse
# ---------------------------------------------------------------------------

def test_gueltiges_geraet_jeder_klasse_kommt_durch():
    result = cfg.validate_options(options(controllable(), binary(), battery()))
    assert result.valid, result.field_errors
    assert [d["name"] for d in result.devices] == ["heizstab", "luft", "acspeicher1"]


def test_controllable_ohne_fallbackfelder_wird_inaktiv():
    result = cfg.validate_options(options({
        "name": "heizstab", "class": "controllable",
        "actual_power_entity": "sensor.heizstab_ist",
    }))
    assert result.devices == []
    assert len(result.inactive_devices) == 1
    issue = result.inactive_devices[0]
    assert issue.name == "heizstab"
    assert set(issue.errors) == set(cfg.CONTROLLABLE_FALLBACK_DEFAULTS)


def test_technisches_maximum_null_ist_ungueltig():
    """Der Formular-Startwert 0 macht ein neues Gerät absichtlich nicht speicherfähig."""
    result = cfg.validate_options(options(controllable(technical_maximum=0)))
    assert "devices[0].technical_maximum" in result.field_errors


def test_technisches_maximum_unter_minimum_ist_ungueltig():
    result = cfg.validate_options(options(controllable(technical_minimum=3000,
                                                       technical_maximum=1000)))
    assert "devices[0].technical_maximum" in result.field_errors


def test_totband_darf_die_maximale_schrittweite_nicht_uebersteigen():
    result = cfg.validate_options(options(controllable(maximum_step_change=100,
                                                       minimum_step_change=200)))
    assert "devices[0].minimum_step_change" in result.field_errors


def test_controllable_null_werte_sind_gueltig_wo_erlaubt():
    result = cfg.validate_options(options(controllable(technical_minimum=0,
                                                       increase_delay_s=0,
                                                       decrease_delay_s=0,
                                                       minimum_step_change=0)))
    assert result.valid, result.field_errors


def test_binary_ohne_fallbackfelder_wird_inaktiv():
    result = cfg.validate_options(options({
        "name": "luft", "class": "binary", "switch_entity": "switch.luft",
    }))
    assert result.devices == []
    assert set(result.inactive_devices[0].errors) == set(cfg.BINARY_FALLBACK_DEFAULTS)


def test_binary_leistung_null_ist_ungueltig():
    result = cfg.validate_options(options(binary(power_w=0)))
    assert "devices[0].power_w" in result.field_errors


def test_fehlende_pflichtentitaet_wird_benannt():
    assert "devices[0].switch_entity" in cfg.validate_options(
        options(binary(switch_entity=""))).field_errors
    assert "devices[0].actual_power_entity" in cfg.validate_options(
        options(controllable(actual_power_entity=""))).field_errors


def test_unvollstaendige_entity_id_wird_abgelehnt():
    result = cfg.validate_options(options(binary(switch_entity="heizluefter")))
    assert "devices[0].switch_entity" in result.field_errors


def test_power_actual_entity_ist_optional():
    result = cfg.validate_options(options(binary()))
    assert result.valid, result.field_errors
    assert "devices[0].power_actual_entity" not in result.field_errors


def test_power_actual_entity_mit_falschem_format_wird_abgelehnt():
    result = cfg.validate_options(options(binary(power_actual_entity="heizluefter_leistung")))
    assert "devices[0].power_actual_entity" in result.field_errors


# ---------------------------------------------------------------------------
# Speicher
# ---------------------------------------------------------------------------

def test_speicher_braucht_beide_available_leistungswerte():
    for key in ("available_charge_power_w", "available_discharge_power_w"):
        result = cfg.validate_options(options(battery(**{key: None})))
        assert f"devices[0].{key}" in result.field_errors


def test_speicher_available_leistung_null_ist_gueltig():
    result = cfg.validate_options(options(battery(
        available_charge_power_w=0,
        available_discharge_power_w=0,
    )))
    assert result.valid, result.field_errors


def test_speicher_available_leistung_muss_endlich_und_nicht_negativ_sein():
    for value in (-1, float("inf"), "sensor.acspeicher1_lade_limit"):
        result = cfg.validate_options(options(battery(available_charge_power_w=value)))
        assert "devices[0].available_charge_power_w" in result.field_errors


def test_alte_available_entity_felder_werden_nicht_als_wattwerte_gedeutet():
    old = battery()
    old.pop("available_charge_power_w")
    old.pop("available_discharge_power_w")
    old["available_charge_power_entity"] = "sensor.acspeicher1_lade_limit"
    old["available_discharge_power_entity"] = "sensor.acspeicher1_entlade_limit"
    result = cfg.validate_options(options(old))
    assert "devices[0].available_charge_power_w" in result.field_errors
    assert "devices[0].available_discharge_power_w" in result.field_errors


def test_speicher_variante_signiert_ist_gueltig():
    result = cfg.validate_options(options(battery(
        charge_power_entity="", discharge_power_entity="",
        power_entity="sensor.acspeicher1_leistung", power_sign="positiv_entladen",
    )))
    assert result.valid, result.field_errors


def test_speicher_mit_beiden_varianten_ist_ungueltig():
    """Genau eine vollständige Variante – doppelt konfiguriert ist mehrdeutig."""
    result = cfg.validate_options(options(battery(power_entity="sensor.acspeicher1_leistung")))
    assert "devices[0].power_entity" in result.field_errors


def test_speicher_mit_halber_variante_a_ist_ungueltig():
    result = cfg.validate_options(options(battery(discharge_power_entity="")))
    assert "devices[0].power_entity" in result.field_errors


def test_speicher_ohne_leistungssensor_ist_ungueltig():
    result = cfg.validate_options(options(battery(charge_power_entity="",
                                                  discharge_power_entity="")))
    assert "devices[0].power_entity" in result.field_errors


def test_speicher_defaults_fuer_hysterese_und_umschaltzeit():
    """Fehlende Werte machen den Speicher NICHT inaktiv – sie fallen auf 2 % und 5 s."""
    result = cfg.validate_options(options(battery()))
    assert result.valid
    assert result.devices[0]["soc_max_hysteresis_percent"] == 2.0
    assert result.devices[0]["direction_switch_delay_s"] == 5.0


def test_speicher_hysterese_ausserhalb_des_bereichs_ist_ungueltig():
    result = cfg.validate_options(options(battery(soc_max_hysteresis_percent=120)))
    assert "devices[0].soc_max_hysteresis_percent" in result.field_errors


def test_unbekanntes_power_sign_ist_ungueltig():
    result = cfg.validate_options(options(battery(
        charge_power_entity="", discharge_power_entity="",
        power_entity="sensor.p", power_sign="irgendwas",
    )))
    assert "devices[0].power_sign" in result.field_errors


# ---------------------------------------------------------------------------
# Ein defektes Gerät legt die übrigen nicht still
# ---------------------------------------------------------------------------

def test_defektes_geraet_beeinflusst_die_uebrigen_nicht():
    result = cfg.validate_options(options(binary(), {"name": "kaputt", "class": "binary"}))
    assert [d["name"] for d in result.devices] == ["luft"]
    assert [i.name for i in result.inactive_devices] == ["kaputt"]


def test_fehlermeldungen_sind_deutsch_und_am_feldpfad():
    result = cfg.validate_options(options(binary(power_w=0)))
    text = result.field_errors["devices[0].power_w"]
    assert text.startswith("Pflichtfeld")
    assert result.inactive_devices[0].errors["power_w"] == text


# ---------------------------------------------------------------------------
# Revision
# ---------------------------------------------------------------------------

def test_revision_ist_stabil_gegen_schluesselreihenfolge():
    a = {"interval_s": 30, "log_level": "info"}
    b = {"log_level": "info", "interval_s": 30}
    assert cfg.revision(a) == cfg.revision(b)


def test_revision_aendert_sich_bei_jeder_aenderung():
    a = {"interval_s": 30}
    assert cfg.revision(a) != cfg.revision({"interval_s": 31})


def test_revision_erkennt_auch_unbekannte_felder():
    """Eine Änderung über die native Add-on-Seite darf nicht unbemerkt bleiben."""
    a = {"interval_s": 30}
    assert cfg.revision(a) != cfg.revision({"interval_s": 30, "zukunftsfeld": 1})


# ---------------------------------------------------------------------------
# Diff für die sichere Deaktivierung
# ---------------------------------------------------------------------------

def test_reine_log_und_intervall_aenderung_erfordert_keine_deaktivierung():
    old = options(binary(), interval_s=30, log_level="info")
    new = options(binary(), interval_s=10, log_level="debug")
    assert cfg.devices_needing_shutdown(old, new) == []


def test_geloeschtes_geraet_wird_deaktiviert():
    old = options(binary(), controllable())
    new = options(binary())
    assert [d["name"] for d in cfg.devices_needing_shutdown(old, new)] == ["heizstab"]


def test_geaendertes_geraet_wird_deaktiviert():
    old = options(binary())
    new = options(binary(power_w=2000))
    assert [d["name"] for d in cfg.devices_needing_shutdown(old, new)] == ["luft"]


def test_neues_geraet_erfordert_keine_deaktivierung():
    assert cfg.devices_needing_shutdown(options(binary()),
                                        options(binary(), controllable())) == []


def test_globale_aenderung_deaktiviert_vorsorglich_alle_altgeraete():
    for key, value in (("residual_power_entity", "sensor.anders"),
                       ("battery_residual_power_entity", "sensor.hausbilanz_anders"),
                       ("speicher_in_residual_enthalten", False),
                       ("available_modes", "manuell")):
        old = options(binary(), controllable())
        new = options(binary(), controllable(), **{key: value})
        assert len(cfg.devices_needing_shutdown(old, new)) == 2, key


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def test_merge_behaelt_unbekannte_top_level_felder():
    stored = {"interval_s": 30, "zukunftsfeld": {"a": 1}}
    merged = cfg.merge_known_fields(stored, {"interval_s": 10, "devices": []})
    assert merged["zukunftsfeld"] == {"a": 1}
    assert merged["interval_s"] == 10


def test_merge_schreibt_alle_bekannten_felder():
    merged = cfg.merge_known_fields({}, options(binary(), log_level="debug"))
    assert merged["log_level"] == "debug"
    assert merged["devices"][0]["name"] == "luft"
    assert merged["available_modes"] == "manuell,nur_heizen,nur_laden"
