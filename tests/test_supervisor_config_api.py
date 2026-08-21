"""Tests für ConfigService: lesen, validieren, speichern, Revision, Neustart.

Gefahren wird gegen einen gefälschten Supervisor und einen gefälschten
Schreibkanal – ohne Netzwerk, ohne Home Assistant, ohne aiohttp-Server. Geprüft
wird die Fachlogik: die HTTP-Handler in main.py übersetzen nur noch Ausnahmen in
Statuscodes.
"""

import asyncio
import logging

import pytest

import configuration as cfg
from config_service import (
    ConfigConflict, ConfigInvalid, ConfigReadOnly, ConfigService, ConfigUnavailable,
)
from ems.ops import WriteResult
from supervisor_client import SupervisorRejected, SupervisorUnavailable

from test_configuration import battery, binary, controllable


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------

class FakeSupervisor:
    def __init__(self, options=None, *, available=True, valid=True,
                 message="", fehler=None):
        self.options = dict(options or {})
        self.available = available
        self._valid = valid
        self._message = message
        self._fehler = fehler
        self.saved = []
        self.validated = []
        self.restarts = 0

    async def get_self_info(self):
        if self._fehler:
            raise self._fehler
        return {"options": dict(self.options), "version": "1.2.1"}

    async def validate_self_options(self, options):
        self.validated.append(options)
        return self._valid, self._message

    async def save_self_options(self, options):
        self.saved.append(options)
        self.options = dict(options)

    async def restart_self(self):
        self.restarts += 1


class FakeWriter:
    """Führt Schreiboperationen aus; `failing` sind die Entitäten, die scheitern."""

    def __init__(self, failing=()):
        self.failing = set(failing)
        self.ops = []

    async def __call__(self, ops):
        self.ops.extend(ops)
        return [
            WriteResult(op, op.data.get("entity_id") not in self.failing,
                        "" if op.data.get("entity_id") not in self.failing else "HTTP 400")
            for op in ops
        ]


def options(*devices, **globals_):
    raw = {"devices": list(devices)}
    raw.update(globals_)
    return raw


def service(stored=None, loaded=None, *, supervisor=None, writer=None,
            snapshot=None, restart_hook=None):
    supervisor = supervisor or FakeSupervisor(stored if stored is not None else {})
    return ConfigService(
        supervisor=supervisor,
        write_ops=writer or FakeWriter(),
        local_options=dict(stored or {}),
        loaded_options=dict(loaded if loaded is not None else (stored or {})),
        instance_id="instanz-1",
        entity_snapshot=lambda: snapshot or {},
        restart_hook=restart_hook,
        restart_delay_s=0.0,
    )


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------

def test_read_liefert_normalisierte_optionen_und_revisionen():
    stored = options(binary(), interval_s=20)
    svc = service(stored)
    data = run(svc.read())
    assert data["options"]["interval_s"] == 20
    assert data["options"]["devices"][0]["name"] == "luft"
    assert data["stored_revision"] == data["loaded_revision"] == cfg.revision(stored)
    assert data["restart_required"] is False
    assert data["can_save"] is True and data["can_restart"] is True


def test_read_meldet_neustartbedarf_bei_abweichender_revision():
    svc = service(options(binary(), interval_s=20), loaded=options(binary(), interval_s=30))
    data = run(svc.read())
    assert data["restart_required"] is True


def test_read_liefert_feldfehler_und_inaktive_geraete():
    svc = service(options({"name": "kaputt", "class": "binary", "switch_entity": "switch.k"}))
    data = run(svc.read())
    assert data["valid"] is False
    assert "devices[0].power_w" in data["field_errors"]
    assert data["inactive_devices"][0]["name"] == "kaputt"


def test_read_liefert_die_unterstuetzten_wertebereiche():
    unterstuetzt = run(service().read())["supported"]
    assert unterstuetzt["modes"] == ["manuell", "nur_heizen", "nur_laden"]
    assert "auto" in unterstuetzt["special_modes"]
    assert unterstuetzt["device_defaults"]["controllable"]["maximum_step_change"] == 1000.0


def test_read_gibt_keine_unbekannten_felder_an_den_browser():
    """Nur bekannte, für die UI bestimmte Felder – keine potenziellen Geheimnisse."""
    svc = service({"interval_s": 30, "zukunftsfeld": {"token": "geheim"}})
    data = run(svc.read())
    assert "zukunftsfeld" not in data["options"]
    assert "geheim" not in str(data)


# ---------------------------------------------------------------------------
# Nur-Lese-Modus ohne Supervisor
# ---------------------------------------------------------------------------

def test_ohne_supervisor_bleibt_lesen_moeglich():
    svc = service(options(binary()), supervisor=FakeSupervisor(available=False))
    data = run(svc.read())
    assert data["options"]["devices"][0]["name"] == "luft"
    assert data["supervisor_available"] is False
    assert data["can_save"] is False and data["can_restart"] is False


def test_ohne_supervisor_ist_speichern_und_neustarten_gesperrt():
    svc = service(options(binary()), supervisor=FakeSupervisor(available=False))
    with pytest.raises(ConfigReadOnly):
        run(svc.save(options(binary()), "egal"))
    with pytest.raises(ConfigReadOnly):
        run(svc.restart())


def test_supervisor_ausfall_beim_lesen_faellt_auf_die_lokale_datei_zurueck():
    sup = FakeSupervisor(fehler=SupervisorUnavailable("Der Supervisor ist nicht erreichbar."))
    svc = service(options(binary()), supervisor=sup)
    data = run(svc.read())
    assert data["options"]["devices"][0]["name"] == "luft"
    assert data["can_save"] is False
    assert "nicht erreichbar" in data["supervisor_error"]


# ---------------------------------------------------------------------------
# Validieren
# ---------------------------------------------------------------------------

def test_validate_speichert_nichts():
    sup = FakeSupervisor(options(binary()))
    svc = service(supervisor=sup)
    ergebnis = svc.validate(options(binary(power_w=0)))
    assert ergebnis["valid"] is False
    assert "devices[0].power_w" in ergebnis["field_errors"]
    assert sup.saved == []


# ---------------------------------------------------------------------------
# Speichern
# ---------------------------------------------------------------------------

def test_speichern_prueft_erst_fachlich_dann_beim_supervisor():
    sup = FakeSupervisor(options(binary()))
    svc = service(supervisor=sup, stored=options(binary()))
    with pytest.raises(ConfigInvalid) as fehler:
        run(svc.save(options(binary(power_w=0)), cfg.revision(options(binary()))))
    assert "devices[0].power_w" in fehler.value.payload["field_errors"]
    assert sup.validated == [] and sup.saved == []


def test_speichern_uebernimmt_den_entwurf_und_startet_nicht_neu():
    stored = options(binary())
    sup = FakeSupervisor(stored)
    svc = service(stored, supervisor=sup)
    ergebnis = run(svc.save(options(binary(power_w=2000)), cfg.revision(stored)))
    assert sup.saved[0]["devices"][0]["power_w"] == 2000
    assert sup.restarts == 0
    assert svc.restart_task is None
    assert ergebnis["restart_required"] is True


def test_speichern_behaelt_unbekannte_top_level_felder():
    stored = {"interval_s": 30, "zukunftsfeld": {"a": 1}, "devices": []}
    sup = FakeSupervisor(stored)
    svc = service(stored, supervisor=sup)
    run(svc.save({"interval_s": 15, "devices": []}, cfg.revision(stored)))
    assert sup.saved[0]["zukunftsfeld"] == {"a": 1}
    assert sup.saved[0]["interval_s"] == 15


def test_revisionskonflikt_ueberschreibt_keine_fremde_aenderung():
    stored = options(binary())
    sup = FakeSupervisor(stored)
    svc = service(stored, supervisor=sup)
    sup.options = options(binary(power_w=999))          # jemand anderes war schneller
    with pytest.raises(ConfigConflict) as fehler:
        run(svc.save(options(binary(power_w=2000)), cfg.revision(stored)))
    assert sup.saved == []
    assert fehler.value.payload["stored_revision"] == cfg.revision(sup.options)


def test_supervisor_ablehnung_verhindert_das_speichern():
    stored = options(binary())
    sup = FakeSupervisor(stored, valid=False, message="devices[0]: unbekanntes Feld")
    svc = service(stored, supervisor=sup)
    with pytest.raises(ConfigInvalid) as fehler:
        run(svc.save(options(binary()), cfg.revision(stored)))
    assert "unbekanntes Feld" in fehler.value.message
    assert sup.saved == []


def test_supervisor_ausfall_beim_speichern_wird_als_502_gemeldet():
    stored = options(binary())
    sup = FakeSupervisor(stored, fehler=SupervisorUnavailable("Der Supervisor ist nicht erreichbar."))
    svc = service(stored, supervisor=sup)
    with pytest.raises(ConfigUnavailable) as fehler:
        run(svc.save(options(binary()), cfg.revision(stored)))
    assert fehler.value.status == 502


# ---------------------------------------------------------------------------
# Sichere Deaktivierung und Neustart
# ---------------------------------------------------------------------------

def test_neustart_speichert_nichts():
    stored = options(binary())
    sup = FakeSupervisor(stored)
    svc = service(stored, supervisor=sup)
    ergebnis = run(_mit_neustart(svc))
    assert sup.saved == []
    assert sup.restarts == 1
    assert ergebnis["restarting"] is True


async def _mit_neustart(svc, **kw):
    ergebnis = await (svc.restart() if not kw else svc.save_and_restart(**kw))
    if svc.restart_task is not None:
        await svc.restart_task
    return ergebnis


def test_reine_intervall_aenderung_deaktiviert_keine_geraete():
    alt = options(binary(), interval_s=30)
    neu = options(binary(), interval_s=10)
    writer = FakeWriter()
    svc = service(neu, loaded=alt, supervisor=FakeSupervisor(neu), writer=writer)
    run(_mit_neustart(svc))
    assert writer.ops == []


def test_geaendertes_altgeraet_wird_vor_dem_neustart_sicher_deaktiviert():
    alt = options(binary(), controllable(), battery())
    neu = options(binary(power_w=2000), controllable(), battery())
    writer = FakeWriter()
    svc = service(neu, loaded=alt, supervisor=FakeSupervisor(neu), writer=writer)
    run(_mit_neustart(svc))
    assert [op.data["entity_id"] for op in writer.ops] == [
        "input_boolean.ems_luft_anforderung_an",
    ]


def test_globale_aenderung_deaktiviert_alle_altgeraete_in_sicherer_reihenfolge():
    alt = options(binary(), battery())
    neu = options(binary(), battery(), residual_power_entity="sensor.anders")
    writer = FakeWriter()
    svc = service(neu, loaded=alt, supervisor=FakeSupervisor(neu), writer=writer)
    run(_mit_neustart(svc))
    assert [op.data["entity_id"] for op in writer.ops] == [
        "input_boolean.ems_luft_anforderung_an",
        # Speicher: erst Leistung 0, dann standby
        "input_number.ems_acspeicher1_anforderung_leistung_w",
        "input_select.ems_acspeicher1_anforderung_betriebsart",
    ]


def test_fehlgeschlagene_deaktivierung_verhindert_den_neustart():
    alt = options(binary())
    neu = options(binary(power_w=2000))
    sup = FakeSupervisor(neu)
    writer = FakeWriter(failing={"input_boolean.ems_luft_anforderung_an"})
    svc = service(neu, loaded=alt, supervisor=sup, writer=writer)
    with pytest.raises(ConfigReadOnly) as fehler:
        run(svc.restart())
    assert sup.restarts == 0
    assert svc.restart_task is None
    assert fehler.value.payload["deactivation_failed"] == ["luft"]


# ---------------------------------------------------------------------------
# Speichern und neu starten
# ---------------------------------------------------------------------------

def test_save_and_restart_haelt_die_reihenfolge_ein():
    stored = options(binary())
    sup = FakeSupervisor(stored)
    writer = FakeWriter()
    svc = service(stored, supervisor=sup, writer=writer)
    ergebnis = run(_mit_neustart(svc, draft=options(binary(power_w=2000)),
                                 stored_revision=cfg.revision(stored)))
    assert sup.saved and sup.restarts == 1
    assert writer.ops, "das geänderte Altgerät muss vorher sicher abgeschaltet werden"
    assert ergebnis["restarting"] is True


def test_save_and_restart_speichert_auch_wenn_die_deaktivierung_scheitert():
    """Der Teilstatus wird ausdrücklich benannt – gespeichert, aber nicht neu gestartet."""
    stored = options(binary())
    sup = FakeSupervisor(stored)
    writer = FakeWriter(failing={"input_boolean.ems_luft_anforderung_an"})
    svc = service(stored, supervisor=sup, writer=writer)
    ergebnis = run(svc.save_and_restart(options(binary(power_w=2000)), cfg.revision(stored)))
    assert sup.saved, "die Konfiguration bleibt gespeichert"
    assert sup.restarts == 0
    assert ergebnis["restarting"] is False
    assert ergebnis["deactivation_failed"] == ["luft"]
    assert "nicht ausgelöst" in ergebnis["message"]


def test_save_and_restart_speichert_bei_ungueltigem_entwurf_nichts():
    stored = options(binary())
    sup = FakeSupervisor(stored)
    svc = service(stored, supervisor=sup)
    with pytest.raises(ConfigInvalid):
        run(svc.save_and_restart(options(binary(power_w=0)), cfg.revision(stored)))
    assert sup.saved == [] and sup.restarts == 0


# ---------------------------------------------------------------------------
# Entitätsauswahl
# ---------------------------------------------------------------------------

SNAPSHOT = {
    "sensor.ueberschuss": {"state": "1500",
                           "attributes": {"friendly_name": "Überschuss", "unit": "W"}},
    "switch.heizlufter":  {"state": "off", "attributes": {}},
    "script.hems":        {"state": "off", "attributes": {}},
    "input_number.ems_luft_prioritat": {"state": "5", "attributes": {}},
}


def test_entitaeten_default_domains_und_reduzierte_felder():
    svc = service(snapshot=SNAPSHOT)
    eintraege = svc.entities()
    assert [e["entity_id"] for e in eintraege] == [
        "script.hems", "sensor.ueberschuss", "switch.heizlufter",
    ]
    assert set(eintraege[1]) == {"entity_id", "domain", "state", "friendly_name"}
    assert eintraege[1]["friendly_name"] == "Überschuss"


def test_entitaeten_koennen_gefiltert_werden():
    svc = service(snapshot=SNAPSHOT)
    assert [e["entity_id"] for e in svc.entities(["input_number"])] == [
        "input_number.ems_luft_prioritat",
    ]


# ---------------------------------------------------------------------------
# Geheimnisse
# ---------------------------------------------------------------------------

def test_weder_token_noch_optionen_erscheinen_in_fehlern_oder_logs(caplog):
    stored = options(binary(switch_entity="switch.geheime_anlage"))
    sup = FakeSupervisor(stored, valid=False, message="Schema-Fehler")
    svc = service(stored, supervisor=sup)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ConfigInvalid) as fehler:
            run(svc.save(options(binary(switch_entity="switch.geheime_anlage")),
                         cfg.revision(stored)))
    assert "geheime_anlage" not in fehler.value.message
    assert "geheime_anlage" not in caplog.text
    assert "Bearer" not in caplog.text


def test_supervisor_client_loggt_keine_rohdaten(caplog):
    from supervisor_client import SupervisorClient
    client = SupervisorClient(token="", base_url="http://supervisor")
    assert client.available is False
    with pytest.raises(SupervisorUnavailable):
        run(client.get_self_info())
    assert "Bearer" not in caplog.text


def test_supervisor_rejected_traegt_nur_die_meldung():
    fehler = SupervisorRejected("devices[0]: unbekanntes Feld")
    assert str(fehler) == "devices[0]: unbekanntes Feld"
