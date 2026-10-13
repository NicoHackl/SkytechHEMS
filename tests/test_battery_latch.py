"""Sperre am Ladedeckel der Speicher über einen Neustart hinweg (D-066).

Szenario: soc_max 100 %, Wiedereinstieg 3 %. Der Speicher fällt nach dem
Vollladen auf 99 %, dann startet das HEMS neu. Ohne gespeicherte Sperre gab der
Neustart das Laden im Hysterese-Band wieder frei.
"""

import json

from battery_latch import BatteryLatchStore
from ems.controller import EMSController

from test_battery_device import make_battery, prepare
from test_configuration import battery, binary


# ---------------------------------------------------------------------------
# Datei
# ---------------------------------------------------------------------------

def test_fehlende_datei_ergibt_keine_sperre(tmp_path):
    assert BatteryLatchStore(tmp_path / "speicher_sperre.json").load() == {}


def test_kaputte_datei_ergibt_keine_sperre(tmp_path):
    path = tmp_path / "speicher_sperre.json"
    path.write_text("{kaputt", encoding="utf-8")
    assert BatteryLatchStore(path).load() == {}


def test_falscher_aufbau_ergibt_keine_sperre(tmp_path):
    path = tmp_path / "speicher_sperre.json"
    path.write_text(json.dumps({"latches": [True]}), encoding="utf-8")
    assert BatteryLatchStore(path).load() == {}


def test_ungueltiger_eintrag_wird_verworfen(tmp_path):
    path = tmp_path / "speicher_sperre.json"
    path.write_text(json.dumps({"latches": {"a": True, "b": "ja"}}), encoding="utf-8")
    assert BatteryLatchStore(path).load() == {"a": True}


def test_speichern_und_laden(tmp_path):
    path = tmp_path / "speicher_sperre.json"
    BatteryLatchStore(path).save({"e3dc_speicher": True, "acspeicher1": False})
    assert BatteryLatchStore(path).load() == {"e3dc_speicher": True, "acspeicher1": False}


def test_ohne_aenderung_wird_nicht_geschrieben(tmp_path, monkeypatch):
    path = tmp_path / "speicher_sperre.json"
    store = BatteryLatchStore(path)
    calls = []
    monkeypatch.setattr("battery_latch.write_json_atomic", lambda p, d: calls.append(d))
    store.save({"a": True})
    store.save({"a": True})
    assert len(calls) == 1
    store.save({"a": False})
    assert len(calls) == 2


def test_nach_laden_wird_gleicher_stand_nicht_geschrieben(tmp_path, monkeypatch):
    path = tmp_path / "speicher_sperre.json"
    path.write_text(json.dumps({"latches": {"a": True}}), encoding="utf-8")
    store = BatteryLatchStore(path)
    store.load()
    calls = []
    monkeypatch.setattr("battery_latch.write_json_atomic", lambda p, d: calls.append(d))
    store.save({"a": True})
    assert calls == []


def test_schreibfehler_haelt_die_regelung_nicht_an(tmp_path, monkeypatch):
    def fail(path, data):
        raise OSError("Dateisystem schreibgeschützt")
    monkeypatch.setattr("battery_latch.write_json_atomic", fail)
    store = BatteryLatchStore(tmp_path / "speicher_sperre.json")
    store.save({"a": True})          # wirft nicht
    monkeypatch.undo()
    store.save({"a": True})          # nächster Versuch schreibt
    assert BatteryLatchStore(tmp_path / "speicher_sperre.json").load() == {"a": True}


# ---------------------------------------------------------------------------
# Speicher
# ---------------------------------------------------------------------------

def test_ohne_gespeicherte_sperre_laedt_der_speicher_im_band():
    """Das bisherige Verhalten nach einem Neustart – der Grund für D-066."""
    b = make_battery(soc_max_hysteresis_percent=3.0)
    prepare(b, soc=99, soc_max=100)
    assert b._lade_limit_w() > 0.0


def test_gespeicherte_sperre_haelt_den_speicher_im_band_gesperrt():
    b = make_battery(soc_max_hysteresis_percent=3.0)
    b.restore_soc_max_latch(True)
    prepare(b, soc=99, soc_max=100)
    assert b._lade_limit_w() == 0.0
    assert b.soc_max_latch is True
    prepare(b, soc=97, soc_max=100)      # Wiedereinstieg erreicht
    assert b._lade_limit_w() > 0.0
    assert b.soc_max_latch is False


def test_gespeicherte_sperre_bleibt_bei_ungueltigem_soc():
    b = make_battery(soc_max_hysteresis_percent=3.0)
    b.restore_soc_max_latch(True)
    prepare(b, soc="unavailable", soc_max=100)
    assert b.soc_max_latch is True


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

def test_controller_liefert_und_uebernimmt_nur_speicher():
    ctrl = EMSController([battery(), binary()],
                         battery_residual_power_entity="sensor.hausleistungsbilanz")
    assert ctrl.battery_latches() == {"acspeicher1": False}
    ctrl.restore_battery_latches({"acspeicher1": True, "geloescht": True, "luft": True})
    assert ctrl.battery_latches() == {"acspeicher1": True}


# ---------------------------------------------------------------------------
# Einbindung in main.py
# ---------------------------------------------------------------------------

def test_neustart_uebernimmt_die_gespeicherte_sperre(tmp_path, monkeypatch):
    from test_emergency import make_app

    (tmp_path / "speicher_sperre.json").write_text(
        json.dumps({"latches": {"acspeicher1": True}}), encoding="utf-8")
    app, _ = make_app(tmp_path, monkeypatch,
                      {"battery_residual_power_entity": "sensor.bilanz", "devices": [battery()]})
    assert app.ems.battery_latches() == {"acspeicher1": True}
