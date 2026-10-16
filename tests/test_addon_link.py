"""Tests für den Link im Sidebar-Fuß auf die HA-Konfigurationsseite (D-067)."""

import asyncio

from config_service import ADDON_FALLBACK_NAME, ConfigService
from supervisor_client import SupervisorRejected, SupervisorUnavailable


def run(coro):
    return asyncio.run(coro)


class InfoSupervisor:
    """Liefert `/addons/self/info`; zählt die Aufrufe."""

    def __init__(self, info=None, *, available=True, fehler=None):
        self.info = info or {}
        self.available = available
        self.fehler = fehler
        self.calls = 0

    async def get_self_info(self):
        self.calls += 1
        if self.fehler:
            raise self.fehler
        return dict(self.info)


def service(supervisor):
    return ConfigService(
        supervisor=supervisor,
        write_ops=None,
        local_options={},
        loaded_options={},
        instance_id="instanz-1",
        entity_snapshot=dict,
    )


def test_link_nutzt_slug_mit_repository_praefix_und_namen_vom_supervisor():
    sup = InfoSupervisor({"slug": "58c515f2_skytech_hems", "name": "Skytech HEMS"})
    assert run(service(sup).addon_link()) == {
        "name": "Skytech HEMS",
        "config_path": "/hassio/addon/58c515f2_skytech_hems/config",
    }


def test_link_wird_nach_erfolg_gemerkt():
    sup = InfoSupervisor({"slug": "58c515f2_skytech_hems", "name": "Skytech HEMS"})
    svc = service(sup)
    run(svc.addon_link())
    run(svc.addon_link())
    assert sup.calls == 1


def test_ohne_supervisor_gibt_es_nur_den_namen():
    svc = service(InfoSupervisor(available=False))
    assert run(svc.addon_link()) == {"name": ADDON_FALLBACK_NAME, "config_path": None}


def test_supervisor_ausfall_wird_nicht_gemerkt():
    sup = InfoSupervisor(fehler=SupervisorUnavailable("Der Supervisor ist nicht erreichbar."))
    svc = service(sup)
    assert run(svc.addon_link())["config_path"] is None
    sup.fehler = None
    sup.info = {"slug": "58c515f2_skytech_hems", "name": "Skytech HEMS"}
    assert run(svc.addon_link())["config_path"] == "/hassio/addon/58c515f2_skytech_hems/config"


def test_ablehnung_durch_den_supervisor_liefert_den_ersatznamen():
    svc = service(InfoSupervisor(fehler=SupervisorRejected("HTTP 500")))
    assert run(svc.addon_link()) == {"name": ADDON_FALLBACK_NAME, "config_path": None}


def test_ungueltiger_slug_wird_nicht_zum_pfad():
    svc = service(InfoSupervisor({"slug": "../../evil", "name": "Skytech HEMS"}))
    assert run(svc.addon_link())["config_path"] is None
