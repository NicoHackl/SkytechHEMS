"""Tests für die steuermodus-abhängige EP-Übernahme (Energy Pilot → HEMS, D-033).

Semantik (überall): auto = KI/EP, manuell = normale Regeln, aus = aus.
  - global ems_regelmodus == "auto"          -> alle Geräte folgen dem EP-Vorschlag
  - global "manuell"/"nur_heizen"/"nur_laden" -> per-Gerät ems_<p>_modus entscheidet
      auto    -> EP (überspringt das Gerätetyp-Gate)
      manuell -> normale Regeln (Nutzer-Helfer, Typ-Gate gilt)
      aus     -> Gerät aus
Fällt ein sensor.ep_*_vorschlag aus, greift der Nutzerwert (Fallback).
"""

import pytest

from ems.controller import EMSController
from conftest import make_states
from test_run_cycle import _global, _controllable_w


def _ctrl_heizstab(allowed="manuell"):
    return EMSController(
        [{"name": "heizstab", "class": "controllable",
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": allowed}],
        residual_power_entity="sensor.s",
    )


def _dev0(res):
    return res["status"]["devices"][0]


# ---------------------------------------------------------------------------
# Global "auto": alle Geräte übernehmen EP-Werte
# ---------------------------------------------------------------------------

def test_ep_prio_and_geschuetzt_override_at_global_auto():
    ctrl = _ctrl_heizstab()
    states = {
        **_global(**{"input_select.ems_regelmodus": "auto"}),
        # Nutzerwerte: prio=1, geschuetzt=0
        **_controllable_w("heizstab", prio=1, min_w=500, max_w=3000, geschuetzt=0),
        # EP-Vorschläge: prio=5, geschuetzt=1500, freigabe on
        "sensor.ep_heizstab_prio_vorschlag": 5,
        "sensor.ep_heizstab_freigabe_vorschlag": "on",
        "sensor.ep_heizstab_geschutzte_mindestleistung_w_vorschlag": 1500,
        "sensor.s": 5000,
        "sensor.heizstab_ist": 0,
    }
    dev = _dev0(ctrl.run_cycle(make_states(states)))
    assert dev["source"] == "ep"
    assert dev["priority"] == 5                    # EP-Priorität übernommen
    assert dev["schutz_w"] == pytest.approx(1500)  # EP-geschützte Mindestleistung übernommen


def test_ep_freigabe_vorschlag_off_disables_device():
    ctrl = _ctrl_heizstab()
    states = {
        **_global(**{"input_select.ems_regelmodus": "auto"}),
        **_controllable_w("heizstab"),           # Nutzer-Freigaben beide on
        "sensor.ep_heizstab_freigabe_vorschlag": "off",   # EP will es aus
        "sensor.s": 5000, "sensor.heizstab_ist": 0,
    }
    dev = _dev0(ctrl.run_cycle(make_states(states)))
    assert dev["source"] == "ep"
    assert dev["eligible"] is False


def test_ep_freigabe_replaces_user_freigabe():
    ctrl = _ctrl_heizstab()
    states = {
        **_global(**{"input_select.ems_regelmodus": "auto"}),
        **_controllable_w("heizstab"),
        "input_boolean.ems_heizstab_freigabe": "off",     # Nutzer-Freigabe AUS
        "sensor.ep_heizstab_freigabe_vorschlag": "on",    # EP-Freigabe AN -> ersetzt
        "sensor.s": 5000, "sensor.heizstab_ist": 0,
    }
    dev = _dev0(ctrl.run_cycle(make_states(states)))
    assert dev["eligible"] is True


def test_technische_freigabe_stays_hard_gate_in_ep():
    ctrl = _ctrl_heizstab()
    states = {
        **_global(**{"input_select.ems_regelmodus": "auto"}),
        **_controllable_w("heizstab"),
        "input_boolean.ems_heizstab_technische_freigabe": "off",  # hartes Gate aus
        "sensor.ep_heizstab_freigabe_vorschlag": "on",
        "sensor.s": 5000, "sensor.heizstab_ist": 0,
    }
    dev = _dev0(ctrl.run_cycle(make_states(states)))
    assert dev["eligible"] is False   # technische Freigabe blockt trotz EP-Freigabe


def test_ep_prio_fallback_when_sensor_absent():
    ctrl = _ctrl_heizstab()
    states = {
        **_global(**{"input_select.ems_regelmodus": "auto"}),
        **_controllable_w("heizstab", prio=7),   # kein EP-prio-Sensor gesetzt
        "sensor.s": 5000, "sensor.heizstab_ist": 0,
    }
    dev = _dev0(ctrl.run_cycle(make_states(states)))
    assert dev["source"] == "ep"
    assert dev["priority"] == 7   # Fallback auf Nutzerwert


def test_device_modus_aus_kills_at_global_auto():
    ctrl = _ctrl_heizstab()
    states = {
        **_global(**{"input_select.ems_regelmodus": "auto"}),
        **_controllable_w("heizstab"),
        "input_select.ems_heizstab_modus": "aus",   # per-Gerät-Kill
        "sensor.ep_heizstab_freigabe_vorschlag": "on",
        "sensor.s": 5000, "sensor.heizstab_ist": 0,
    }
    dev = _dev0(ctrl.run_cycle(make_states(states)))
    assert dev["source"] == "aus"
    assert dev["eligible"] is False


# ---------------------------------------------------------------------------
# Global "manuell": per-Gerät ems_<p>_modus entscheidet die Quelle
# ---------------------------------------------------------------------------

def test_per_device_modus_manuell_uses_user_values():
    ctrl = _ctrl_heizstab()
    states = {
        **_global(**{"input_select.ems_regelmodus": "manuell"}),
        **_controllable_w("heizstab", prio=1),
        "input_select.ems_heizstab_modus": "manuell",
        "sensor.ep_heizstab_prio_vorschlag": 5,   # muss ignoriert werden
        "sensor.s": 5000, "sensor.heizstab_ist": 0,
    }
    dev = _dev0(ctrl.run_cycle(make_states(states)))
    assert dev["source"] == "user"
    assert dev["priority"] == 1     # Nutzerwert, nicht EP


def test_per_device_modus_auto_uses_ep():
    ctrl = _ctrl_heizstab()
    states = {
        **_global(**{"input_select.ems_regelmodus": "manuell"}),
        **_controllable_w("heizstab", prio=1),
        "input_select.ems_heizstab_modus": "auto",
        "sensor.ep_heizstab_prio_vorschlag": 5,
        "sensor.ep_heizstab_freigabe_vorschlag": "on",
        "sensor.s": 5000, "sensor.heizstab_ist": 0,
    }
    dev = _dev0(ctrl.run_cycle(make_states(states)))
    assert dev["source"] == "ep"
    assert dev["priority"] == 5


# ---------------------------------------------------------------------------
# Typ-Gate: manuell respektiert es, per-Gerät auto überspringt es
# ---------------------------------------------------------------------------

def test_manuell_respects_type_gate():
    # Wallbox nur bei nur_laden erlaubt -> unter nur_heizen + modus=manuell = aus
    ctrl = EMSController(
        [{"name": "wallbox_1", "class": "controllable",
          "actual_power_entity": "sensor.wb", "entity_prefix": "wallbox",
          "allowed_modes": "nur_laden", "output_unit": "ampere", "phases": "1"}],
        residual_power_entity="sensor.s",
    )
    base = {
        **_global(**{"input_select.ems_regelmodus": "nur_heizen"}),
        "input_boolean.ems_wallbox_freigabe": "on",
        "input_boolean.ems_wallbox_technische_freigabe": "on",
        "input_number.ems_wallbox_prioritat": 1,
        "input_number.ems_wallbox_min_technisch_a": 6,
        "input_number.ems_wallbox_max_technisch_a": 16,
        "input_number.ems_wallbox_geschutzte_mindestleistung_a": 0,
        "input_number.ems_wallbox_reserve_w": 0,
        "input_number.ems_wallbox_hoch_regelzeit_s": 0,
        "input_number.ems_wallbox_runter_regelzeit_s": 0,
        "input_number.ems_wallbox_max_anderung_pro_schritt_a": 16,
        "input_number.ems_wallbox_min_anderung_pro_schritt_a": 0,
        "input_number.ems_wallbox_anforderung_leistung_a": 0,
        "sensor.wb": 0, "sensor.s": 5000,
    }
    # modus manuell -> Typ-Gate greift -> aus
    dev = _dev0(ctrl.run_cycle(make_states({
        **base, "input_select.ems_wallbox_modus": "manuell"})))
    assert dev["source"] == "aus"

    # modus auto -> EP überspringt Typ-Gate -> ep + eligible (EP-Freigabe on)
    dev = _dev0(ctrl.run_cycle(make_states({
        **base, "input_select.ems_wallbox_modus": "auto",
        "sensor.ep_wallbox_freigabe_vorschlag": "on"})))
    assert dev["source"] == "ep"
    assert dev["eligible"] is True
