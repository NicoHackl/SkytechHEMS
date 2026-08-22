"""Tests für EMSController: Pool, Lockout, konfigurierbarer Sensor, Kaskade, One-Change."""

from ems.controller import EMSController, DEFAULT_RESIDUAL_ENTITY
from ems.devices import BinaryDevice

from conftest import make_states
from test_run_cycle import BIN_FALLBACKS


def make_binary(prio, actual_on, final_on):
    b = BinaryDevice("d%d" % prio, ["auto"], "switch.x", "input_boolean.x")
    b.priority = prio
    b._actual_on = actual_on
    b._final_on = final_on
    return b


# ---- Konfiguration des Überschuss-Sensors ----

def test_default_residual_entity():
    ctrl = EMSController([])
    assert ctrl._residual_entity == DEFAULT_RESIDUAL_ENTITY


def test_custom_residual_entity_used():
    ctrl = EMSController([], residual_power_entity="sensor.mein_ueberschuss")
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.mein_ueberschuss": "3000",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["residual_w"] == 3000.0
    assert res["status"]["pool_w"] == 3000.0


def test_empty_residual_entity_falls_back_to_default():
    ctrl = EMSController([], residual_power_entity="   ")
    assert ctrl._residual_entity == DEFAULT_RESIDUAL_ENTITY


# ---- Formel-basierte Sensorwerte (D-045) ----

def test_ohne_formel_bleibt_verhalten_unveraendert():
    """Regressionsanker zuerst: leere Formel-Felder – der Standardfall jeder
    Bestandsanlage – dürfen das Verhalten in keinem Byte verändern."""
    ctrl = EMSController([], residual_power_entity="sensor.s")
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.s": "3000",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["residual_w"] == 3000.0
    assert res["status"]["residual_source"] == "ha"


def test_gueltige_formel_ersetzt_ueberschuss_entitaet():
    ctrl = EMSController(
        [], residual_power_entity="sensor.s",
        residual_formula_variables=[{"name": "pv", "entity": "sensor.pv"}],
        residual_formula_code="ueberschuss = pv * 2",
    )
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.s": "1",  # würde ohne Formel einen ganz anderen Wert liefern
        "sensor.pv": "1500",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["residual_w"] == 3000.0
    assert res["status"]["residual_source"] == "formula"
    assert res["status"]["pool_w"] == 3000.0


def test_ungueltige_formel_faellt_auf_ueberschuss_entitaet_zurueck():
    """Ein Zyklus bricht an einer kaputten Formel nie ab (Invariante 5)."""
    ctrl = EMSController(
        [], residual_power_entity="sensor.s",
        residual_formula_variables=[{"name": "pv", "entity": "sensor.pv"}],
        residual_formula_code="ueberschuss = pv / 0",
    )
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.s": "3000",
        "sensor.pv": "1500",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["residual_w"] == 3000.0
    assert res["status"]["residual_source"] == "ha"


def test_hard_lockout_greift_auch_bei_formelwert():
    ctrl = EMSController(
        [], residual_power_entity="sensor.s",
        residual_formula_variables=[{"name": "pv", "entity": "sensor.pv"}],
        residual_formula_code="ueberschuss = pv",
    )
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.s": "3000",
        "sensor.pv": "-60000",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["residual_source"] == "formula"
    assert res["status"]["hard_lockout"] is True
    assert res["status"]["pool_w"] == 0.0


def test_gueltige_formel_ersetzt_hausleistungsbilanz():
    ctrl = EMSController(
        [], residual_power_entity="sensor.s",
        battery_residual_power_entity="sensor.hb",
        battery_residual_formula_variables=[{"name": "netz", "entity": "sensor.netz"}],
        battery_residual_formula_code="hausbilanz = netz",
    )
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.s": "3000",
        "sensor.hb": "0",  # würde ohne Formel gelten
        "sensor.netz": "-700",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["battery_residual_w"] == -700.0
    assert res["status"]["battery_residual_source"] == "formula"


def test_ungueltige_hausbilanz_formel_faellt_auf_entitaet_zurueck():
    ctrl = EMSController(
        [], residual_power_entity="sensor.s",
        battery_residual_power_entity="sensor.hb",
        battery_residual_formula_variables=[{"name": "netz", "entity": "sensor.netz"}],
        battery_residual_formula_code="hausbilanz = netz / 0",
    )
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.s": "3000",
        "sensor.hb": "-500",
        "sensor.netz": "-700",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["battery_residual_w"] == -500.0
    assert res["status"]["battery_residual_source"] == "ha"


# ---- Globalzustände ----

def test_ems_disabled_yields_empty_pool():
    ctrl = EMSController([], residual_power_entity="sensor.s")
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "off",
        "sensor.s": "5000",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["ems_enabled"] is False
    assert res["status"]["pool_w"] == 0.0


def test_hard_lockout_on_invalid_sensor():
    ctrl = EMSController([], residual_power_entity="sensor.s")
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.s": "unavailable",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["residual_sensor_valid"] is False
    assert res["status"]["hard_lockout"] is True
    assert res["status"]["pool_w"] == 0.0


def test_hard_lockout_on_extreme_negative():
    ctrl = EMSController([], residual_power_entity="sensor.s")
    st = make_states({
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "sensor.s": "-60000",
    })
    res = ctrl.run_cycle(st)
    assert res["status"]["hard_lockout"] is True


# ---- One-Change-Limit ----

def test_limit_one_change_only_one_turn_on():
    ctrl = EMSController([])
    a = make_binary(1, actual_on=False, final_on=True)
    b = make_binary(2, actual_on=False, final_on=True)
    ctrl._limit_one_change([a, b], binary_immediate_off=False)
    # Höchste Priorität (kleinste Zahl) gewinnt
    assert a.final_on is True
    assert b.final_on is False


def test_limit_one_change_skipped_on_emergency():
    ctrl = EMSController([])
    a = make_binary(1, actual_on=True, final_on=False)
    b = make_binary(2, actual_on=True, final_on=False)
    ctrl._limit_one_change([a, b], binary_immediate_off=True)
    # Notabschaltung: beide dürfen gleichzeitig abschalten
    assert a.final_on is False
    assert b.final_on is False


def test_limit_one_change_turn_off_keeps_higher_on():
    ctrl = EMSController([])
    a = make_binary(1, actual_on=True, final_on=False)   # wichtig
    b = make_binary(2, actual_on=True, final_on=False)   # unwichtig
    ctrl._limit_one_change([a, b], binary_immediate_off=False)
    # Nur das unwichtigste (höchste Prio-Zahl) schaltet ab
    assert b.final_on is False
    assert a.final_on is True


# ---- Prioritätskaskade (Promotion) ----

def test_cascade_promotes_higher_priority_on():
    ctrl = EMSController([])
    high = make_binary(1, actual_on=False, final_on=False)
    high.eligible = True
    high._candidate_on = True
    low = make_binary(2, actual_on=False, final_on=True)
    ctrl._apply_priority_cascade([high, low])
    # Höher-priores Gerät darf nicht aus sein, während niedriger-priores an ist
    assert high.final_on is True


# ---- Charakterisierung: Modus-Migration der Geräte-Registry ----

def test_allowed_modes_auto_wird_auf_manuell_abgebildet():
    """`auto` ist kein Nutzer-Gate mehr – Alt-Konfigurationen werden umgeschrieben."""
    ctrl = EMSController([{
        "name": "luft", "class": "binary",
        "switch_entity": "switch.luft", "allowed_modes": "auto,nur_heizen",
        **BIN_FALLBACKS,
    }])
    assert ctrl._devices[0]._allowed_modes == ["manuell", "nur_heizen"]


def test_allowed_modes_fehlt_ergibt_manuell():
    ctrl = EMSController([{
        "name": "luft", "class": "binary", "switch_entity": "switch.luft",
        **BIN_FALLBACKS,
    }])
    assert ctrl._devices[0]._allowed_modes == ["manuell"]


def test_geraet_ohne_pflichtentitaet_wird_uebersprungen():
    """Der Rest der Anlage läuft weiter – ein kaputter Eintrag legt nichts still."""
    ctrl = EMSController([
        {"name": "kaputt", "class": "binary"},
        {"name": "luft", "class": "binary", "switch_entity": "switch.luft", **BIN_FALLBACKS},
    ])
    assert [d.id for d in ctrl._devices] == ["luft"]


# ---- Global deaktivierter Regelmodus ----

def _aktiv(mode="manuell", **over):
    states = {
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": mode,
        "sensor.s": 3000,
    }
    states.update(over)
    return make_states(states)


def test_nicht_konfigurierter_modus_macht_den_zyklus_sicher_inaktiv():
    """Hinter einem global deaktivierten Modus steht keine Regellogik."""
    ctrl = EMSController([], residual_power_entity="sensor.s",
                         available_modes="manuell")
    status = ctrl.run_cycle(_aktiv("nur_heizen"))["status"]
    assert status["global_mode"] == "nur_heizen"      # roher HA-State bleibt sichtbar
    assert status["global_mode_configured"] is False
    assert status["pool_w"] == 0.0
    assert status["hausdefizit_w"] == 0.0


def test_konfigurierter_modus_regelt_normal():
    ctrl = EMSController([], residual_power_entity="sensor.s",
                         available_modes="manuell,nur_heizen")
    status = ctrl.run_cycle(_aktiv("nur_heizen"))["status"]
    assert status["global_mode_configured"] is True
    assert status["pool_w"] == 3000.0


def test_sondermodi_bleiben_immer_unterstuetzt():
    ctrl = EMSController([], residual_power_entity="sensor.s", available_modes="manuell")
    for mode in ("auto", "aus"):
        status = ctrl.run_cycle(_aktiv(mode))["status"]
        assert status["global_mode_configured"] is True, mode


def test_available_modes_default_sind_alle_drei():
    assert EMSController([]).available_modes == ["manuell", "nur_heizen", "nur_laden"]


# ---- Nur-Energy-Pilot-Gerät ----

def test_leeres_allowed_modes_wird_von_normalen_regeln_nicht_aktiviert():
    ctrl = EMSController([{
        "name": "luft", "class": "binary", "switch_entity": "switch.luft",
        "allowed_modes": "", **BIN_FALLBACKS,
    }], residual_power_entity="sensor.s")
    device = ctrl._devices[0]
    assert device._allowed_modes == []
    status = ctrl.run_cycle(_aktiv("manuell", **{
        "input_boolean.ems_luft_freigabe": "on",
        "input_boolean.ems_luft_technische_freigabe": "on",
        "input_select.ems_luft_modus": "manuell",
    }))["status"]
    assert status["devices"][0]["source"] == "aus"


def test_leeres_allowed_modes_folgt_weiter_dem_energy_pilot():
    ctrl = EMSController([{
        "name": "luft", "class": "binary", "switch_entity": "switch.luft",
        "allowed_modes": "", **BIN_FALLBACKS,
    }], residual_power_entity="sensor.s")
    status = ctrl.run_cycle(_aktiv("auto", **{
        "input_select.ems_luft_modus": "auto",
    }))["status"]
    assert status["devices"][0]["source"] == "ep"


# ---- Ungültige Geräteeinträge ----

def test_ungueltiger_eintrag_erscheint_als_inaktives_geraet():
    ctrl = EMSController([
        {"name": "luft", "class": "binary", "switch_entity": "switch.luft", **BIN_FALLBACKS},
        {"name": "kaputt", "class": "binary", "switch_entity": "switch.k"},
    ], residual_power_entity="sensor.s")
    status = ctrl.run_cycle(_aktiv())["status"]
    assert [d["id"] for d in status["devices"]] == ["luft"]
    inaktiv = status["inactive_devices"]
    assert len(inaktiv) == 1
    assert inaktiv[0]["name"] == "kaputt"
    assert inaktiv[0]["device_class"] == "binary"
    assert "power_w" in inaktiv[0]["errors"]


def test_inaktives_geraet_erzeugt_keine_erfundenen_istwerte():
    ctrl = EMSController([{"name": "kaputt", "class": "binary", "switch_entity": "switch.k"}],
                         residual_power_entity="sensor.s")
    status = ctrl.run_cycle(_aktiv())["status"]
    assert status["devices"] == []
    assert set(status["inactive_devices"][0]) == {
        "index", "name", "device_class", "label", "errors",
    }


def test_inaktives_geraet_beeinflusst_den_pool_nicht():
    mit = EMSController([{"name": "kaputt", "class": "binary", "switch_entity": "switch.k"}],
                        residual_power_entity="sensor.s").run_cycle(_aktiv())["status"]
    ohne = EMSController([], residual_power_entity="sensor.s").run_cycle(_aktiv())["status"]
    assert mit["pool_w"] == ohne["pool_w"] == 3000.0
