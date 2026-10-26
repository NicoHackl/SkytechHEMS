"""Simuliert den echten HEMS-Regelcode (app/ems) gegen eine steigende PV-Überschusskurve.

Eingabe: Helferwerte und Add-on-Konfiguration als Schnappschuss aus der echten Anlage
(Home Assistant per MCP gelesen am 26.10.2026). Ausgabe: JSON mit den Verläufen je Gerät,
das `regelverhalten_grafik.py` in ein SVG umsetzt.

Aufruf (aus dem Repo-Wurzelverzeichnis): python docs/grafiken/regelverhalten_simulation.py
"""

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))

import ems.controller as controller_module  # noqa: E402
from ems.controller import EMSController  # noqa: E402
from ems.state import StateProxy  # noqa: E402

logging.disable(logging.CRITICAL)

CYCLE_S = 4            # interval_s der Anlage
DURATION_S = 32 * 60
T0 = 1_000_000.0       # beliebige Wanduhr-Epoche; nur Differenzen zählen

# Annahme des Tests: AC Speicher 1 hat keine Freigabe, Heizlüfter 1 ist freigegeben.
ASSUME = {
    "input_boolean.ems_acspeicher1_freigabe": "off",
    "input_boolean.ems_heizlufter_1_freigabe": "on",
}

# Steigende bzw. gleichbleibende PV-Überschusskurve: (Sekunde, Watt)-Stützpunkte, linear dazwischen.
SURPLUS_POINTS = [
    (0, 0), (90, 0), (240, 1500), (360, 1500), (540, 3500), (660, 3500),
    (840, 6000), (1020, 6000), (1200, 8500), (1380, 8500), (1560, 12000), (1920, 12000),
]

# Add-on-Konfiguration der echten Anlage (nur regelrelevante Felder).
DEVICES = [
    {"name": "heizstab", "class": "controllable", "label": "Heizstab", "entity_prefix": "heizstab",
     "allowed_modes": "manuell,nur_heizen", "actual_power_entity": "sensor.elwa_istleistung_modbus",
     "output_unit": "watt", "phases": "1", "phase_switch_delay_s": 300,
     "technical_minimum": 0, "technical_maximum": 3500, "increase_delay_s": 0,
     "decrease_delay_s": 0, "maximum_step_change": 3500, "minimum_step_change": 50},
    {"name": "heizlufter_1", "class": "binary", "label": "Heizlüfter 1", "entity_prefix": "heizlufter_1",
     "allowed_modes": "manuell,nur_heizen", "switch_entity": "switch.ems_uv_1",
     "power_actual_entity": "sensor.ems_uv_1_leistung", "power_w": 1500, "on_reserve_w": 0,
     "min_runtime_s": 60, "min_offtime_s": 20, "off_delay_s": 30, "on_delay_s": 0},
    {"name": "acspeicher1", "class": "battery", "label": "AC Speicher 1", "entity_prefix": "acspeicher1",
     "allowed_modes": "manuell,nur_laden", "soc_entity": "sensor.ac_speicher_1_ladezustand",
     "power_entity": "sensor.mqtt_ac_speicher_1_leistung", "power_sign": "positiv_laden",
     "capacity_kwh": 5, "available_charge_power_w": 2500, "available_discharge_power_w": 2500,
     "soc_max_hysteresis_percent": 4, "direction_switch_delay_s": 3},
    {"name": "e3dc_speicher", "class": "battery", "label": "E3DC Speicher", "entity_prefix": "e3dc_speicher",
     "allowed_modes": "manuell,nur_heizen,nur_laden", "soc_entity": "sensor.e3dc_batterie_soc_modbus",
     "power_entity": "sensor.e3dc_leistung_batterie_modbus", "power_sign": "positiv_laden",
     "capacity_kwh": 12, "available_charge_power_w": 6000, "available_discharge_power_w": 6000,
     "soc_max_hysteresis_percent": 4, "direction_switch_delay_s": 5},
]

# Helferwerte aus Home Assistant (Schnappschuss 26.10.2026); Testannahmen: geschützte Mindestleistung Heizstab 1000 W (HA: 500 W); alle Reserven und Puffer 0 W (HA: Puffer 100 W, Einschaltreserve 200 W, Heizstab-Reserve 200 W, Heizlüfter-Einschaltreserve 200 W).
HELPERS = {
    "input_boolean.ems_pv_regelung_aktiv": "on",
    "input_select.ems_regelmodus": "manuell",
    "input_number.ems_globaler_puffer_w": 0,
    "input_number.ems_einschaltreserve_global_w": 0,
    "input_number.ems_ac_speicher_entlade_abschlag_w": 0,
    # Heizstab
    "input_boolean.ems_heizstab_freigabe": "on", "input_boolean.ems_heizstab_technische_freigabe": "on",
    "input_boolean.ems_heizstab_force": "off", "input_select.ems_heizstab_modus": "manuell",
    "input_number.ems_heizstab_prioritat": 10, "input_number.ems_heizstab_min_technisch_w": 0,
    "input_number.ems_heizstab_max_technisch_w": 3500, "input_number.ems_heizstab_geschutzte_mindestleistung_w": 1000,
    "input_number.ems_heizstab_reserve_w": 0, "input_number.ems_heizstab_hoch_regelzeit_s": 1,
    "input_number.ems_heizstab_runter_regelzeit_s": 1, "input_number.ems_heizstab_max_anderung_pro_schritt_w": 1000,
    "input_number.ems_heizstab_min_anderung_pro_schritt_w": 50, "input_number.ems_heizstab_force_leistung_w": 700,
    "input_number.ems_heizstab_anforderung_leistung_w": 0,
    # Heizlüfter 1
    "input_boolean.ems_heizlufter_1_technische_freigabe": "on", "input_boolean.ems_heizlufter_1_force": "off",
    "input_boolean.ems_heizlufter_1_anforderung_an": "off", "input_select.ems_heizlufter_1_modus": "manuell",
    "input_number.ems_heizlufter_1_prioritat": 20, "input_number.ems_heizlufter_1_leistung_w": 1500,
    "input_number.ems_heizlufter_1_einschaltreserve_w": 0, "input_number.ems_heizlufter_1_mindestlaufzeit_s": 120,
    "input_number.ems_heizlufter_1_mindestauszeit_s": 60, "input_number.ems_heizlufter_1_abschaltverzogerung_s": 30,
    "input_number.ems_heizlufter_1_einschaltverzogerung_s": 30,
    # AC Speicher 1
    "input_boolean.ems_acspeicher1_technische_freigabe": "on", "input_boolean.ems_acspeicher1_netzladen_erlaubt": "off",
    "input_select.ems_acspeicher1_modus": "manuell", "input_select.ems_acspeicher1_betriebsart": "auto",
    "input_select.ems_acspeicher1_anforderung_betriebsart": "standby",
    "input_number.ems_acspeicher1_anforderung_leistung_w": 0, "input_number.ems_acspeicher1_prioritat": 8,
    "input_number.ems_acspeicher1_entlade_prioritat": 1, "input_number.ems_acspeicher1_geschutzte_mindestleistung_w": 2500,
    "input_number.ems_acspeicher1_hoch_regelzeit_s": 3, "input_number.ems_acspeicher1_runter_regelzeit_s": 3,
    "input_number.ems_acspeicher1_min_anderung_pro_schritt_w": 25, "input_number.ems_acspeicher1_min_ladeleistung_w": 0,
    "input_number.ems_acspeicher1_reserve_w": 0, "input_number.ems_acspeicher1_soc_min_prozent": 12,
    "input_number.ems_acspeicher1_umschalt_totzone_w": 25,
    # E3DC Speicher
    "input_boolean.ems_e3dc_speicher_freigabe": "on", "input_boolean.ems_e3dc_speicher_technische_freigabe": "on",
    "input_boolean.ems_e3dc_speicher_netzladen_erlaubt": "off", "input_select.ems_e3dc_speicher_modus": "manuell",
    "input_select.ems_e3dc_speicher_betriebsart": "auto", "input_select.ems_e3dc_speicher_anforderung_betriebsart": "standby",
    "input_number.ems_e3dc_speicher_anforderung_leistung_w": 0, "input_number.ems_e3dc_speicher_prioritat": 5,
    "input_number.ems_e3dc_speicher_entlade_prioritat": 10, "input_number.ems_e3dc_speicher_geschutzte_mindestleistung_w": 3000,
    "input_number.ems_e3dc_speicher_hoch_regelzeit_s": 3, "input_number.ems_e3dc_speicher_runter_regelzeit_s": 3,
    "input_number.ems_e3dc_speicher_min_anderung_pro_schritt_w": 25, "input_number.ems_e3dc_speicher_min_ladeleistung_w": 0,
    "input_number.ems_e3dc_speicher_reserve_w": 0, "input_number.ems_e3dc_speicher_soc_min_prozent": 1,
    "input_number.ems_e3dc_speicher_umschalt_totzone_w": 25,
    "input_boolean.ems_e3dc_speicher_ladestufe_1_aktiv": "on", "input_number.ems_e3dc_speicher_ladestufe_1_soc_prozent": 40,
    "input_number.ems_e3dc_speicher_ladestufe_1_max_ladeleistung_w": 5200,
    "input_boolean.ems_e3dc_speicher_ladestufe_2_aktiv": "on", "input_number.ems_e3dc_speicher_ladestufe_2_soc_prozent": 80,
    "input_number.ems_e3dc_speicher_ladestufe_2_max_ladeleistung_w": 4950,
    "input_boolean.ems_e3dc_speicher_ladestufe_3_aktiv": "on", "input_number.ems_e3dc_speicher_ladestufe_3_soc_prozent": 96,
    "input_number.ems_e3dc_speicher_ladestufe_3_max_ladeleistung_w": 800,
}

E3DC_SOC_START = 48.0
E3DC_CAPACITY_WH = 12_000.0
AC1_SOC = 30.0  # nur Platzhalter, der Speicher hat keine Freigabe


def surplus_at(t: float) -> float:
    for (t1, w1), (t2, w2) in zip(SURPLUS_POINTS, SURPLUS_POINTS[1:]):
        if t1 <= t <= t2:
            return w1 + (w2 - w1) * (t - t1) / (t2 - t1) if t2 > t1 else w2
    return SURPLUS_POINTS[-1][1]


def main() -> None:
    clock = {"t": T0}
    controller_module.time = SimpleNamespace(time=lambda: clock["t"])

    ctrl = EMSController(
        DEVICES,
        residual_power_entity="sensor.verfugbare_leistung_fur_uberschusverbraucher",
        battery_residual_power_entity="sensor.hausleistung_bilanz_fur_ac_speicher",
        speicher_in_residual_enthalten=True,
        protected_minimum_scope="binary_and_controllable",
        available_modes="manuell,nur_heizen,nur_laden",
    )

    # Zustandsspeicher: entity_id -> {"state", "attributes", "last_changed"}
    states = {}

    def put(eid, value, attrs=None):
        old = states.get(eid)
        if old is not None and old["state"] == str(value):
            return
        states[eid] = {"state": str(value), "attributes": attrs or (old["attributes"] if old else {}),
                       "last_changed": clock["t"]}

    attrs = {
        "input_number.ems_heizstab_anforderung_leistung_w": {"min": 0, "max": 3500, "step": 1},
        "input_number.ems_acspeicher1_anforderung_leistung_w": {"min": -20000, "max": 20000, "step": 1},
        "input_number.ems_e3dc_speicher_anforderung_leistung_w": {"min": -20000, "max": 20000, "step": 1},
        "input_select.ems_acspeicher1_anforderung_betriebsart": {"options": ["laden", "entladen", "standby"]},
        "input_select.ems_e3dc_speicher_anforderung_betriebsart": {"options": ["laden", "entladen", "standby"]},
    }
    for eid, val in {**HELPERS, **ASSUME}.items():
        states[eid] = {"state": str(val), "attributes": attrs.get(eid, {}), "last_changed": 0.0}
    for eid in ("input_select.ems_heizstab_modus", "input_select.ems_heizlufter_1_modus",
                "input_select.ems_acspeicher1_modus", "input_select.ems_e3dc_speicher_modus"):
        states[eid]["attributes"] = {"options": ["auto", "manuell", "aus"]}

    # Anlagenzustand
    fan_on = False
    soc = E3DC_SOC_START
    heizstab_w = 0.0
    e3dc_w = 0.0          # signiert, positiv = Laden
    rows = []

    steps = DURATION_S // CYCLE_S + 1
    for i in range(steps):
        t = i * CYCLE_S
        clock["t"] = T0 + t
        surplus_w = surplus_at(t)
        fan_w = 1500.0 if fan_on else 0.0
        # Messpunkt Netzübergabe: Überschuss minus eigene Last plus Entladung (Speicher im Sensor enthalten)
        residual = surplus_w - heizstab_w - fan_w - e3dc_w

        put("sensor.verfugbare_leistung_fur_uberschusverbraucher", round(residual, 1))
        put("sensor.hausleistung_bilanz_fur_ac_speicher", round(residual, 1))
        put("sensor.elwa_istleistung_modbus", round(heizstab_w, 1))
        put("switch.ems_uv_1", "on" if fan_on else "off")
        put("sensor.ems_uv_1_leistung", fan_w)
        put("sensor.e3dc_batterie_soc_modbus", round(soc, 2))
        put("sensor.e3dc_leistung_batterie_modbus", round(e3dc_w, 1))
        put("sensor.ac_speicher_1_ladezustand", AC1_SOC)
        put("sensor.mqtt_ac_speicher_1_leistung", 0)

        result = ctrl.run_cycle(StateProxy(states))
        devs = {d["id"]: d for d in result["status"]["devices"]}

        # Schreiboperationen in den HA-State übernehmen (die HA-Automationen und Geräte folgen sofort)
        for op in result["write_ops"]:
            eid = op.data.get("entity_id")
            if op.service == "set_value":
                put(eid, op.data["value"])
            elif op.service == "select_option":
                put(eid, op.data["option"])
            elif op.service == "turn_on":
                put(eid, "on")
            elif op.service == "turn_off":
                put(eid, "off")
        fan_on = states["input_boolean.ems_heizlufter_1_anforderung_an"]["state"] == "on"
        heizstab_w = float(states["input_number.ems_heizstab_anforderung_leistung_w"]["state"])
        e3dc_w = float(states["input_number.ems_e3dc_speicher_anforderung_leistung_w"]["state"])
        if states["input_select.ems_e3dc_speicher_anforderung_betriebsart"]["state"] == "standby":
            e3dc_w = 0.0
        soc = min(100.0, soc + e3dc_w * CYCLE_S / 3600.0 / E3DC_CAPACITY_WH * 100.0)

        rows.append({
            "t": t, "surplus": surplus_w, "pool": result["status"]["pool_w"],
            "e3dc": e3dc_w, "heizstab": heizstab_w, "heizlufter": 1500.0 if fan_on else 0.0,
            "ac1": 0.0, "soc": soc,
            "e3dc_limit": devs["e3dc_speicher"].get("lade_limit_w"),
        })

    out = Path(__file__).with_name("regelverhalten_daten.json")
    out.write_text(json.dumps(rows, indent=0), encoding="utf-8")
    print(f"{len(rows)} Zyklen -> {out.name}")


if __name__ == "__main__":
    main()
