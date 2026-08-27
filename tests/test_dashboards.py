"""Formen der Dashboard-Liste für die Zielauswahl (D-049).

Der WebSocket selbst bleibt ungetestet — wie der übrige HA-Client. Geprüft
wird die reine Funktion daneben, und zwar an den Fällen, die im Betrieb
tatsächlich vorkommen: Strategie-Dashboards und YAML-Dashboards liefern keine
Ansichtsliste.
"""

from ha_client import STANDARD_DASHBOARD, forme_dashboards


def test_ansichten_werden_mit_pfad_und_titel_uebernommen():
    dashboards, warnungen = forme_dashboards([
        ({"url_path": "dashboard-pv", "title": "PV"},
         {"views": [{"path": "ems", "title": "EMS"}, {"path": "netz"}]}, ""),
    ])
    assert warnungen == []
    assert dashboards[0]["views"] == [
        {"path": "ems", "title": "EMS"},
        {"path": "netz", "title": "netz"},
    ]


def test_ansicht_ohne_pfad_ist_ueber_ihre_position_erreichbar():
    dashboards, _ = forme_dashboards([
        ({"url_path": "d", "title": "D"}, {"views": [{"title": "Erste"}]}, ""),
    ])
    assert dashboards[0]["views"] == [{"path": "0", "title": "Erste"}]


def test_standard_dashboard_bekommt_seinen_pfad():
    # In lovelace/dashboards/list taucht es nicht auf; es wird mit url_path
    # None abgefragt und heisst im Adressfeld "lovelace".
    dashboards, _ = forme_dashboards([
        ({"url_path": None, "title": "Übersicht"}, {"views": []}, ""),
    ])
    assert dashboards[0]["url_path"] == STANDARD_DASHBOARD


def test_strategie_dashboard_erscheint_ohne_ansichten_mit_warnung():
    dashboards, warnungen = forme_dashboards([
        ({"url_path": None, "title": "Übersicht"}, {"strategy": {"type": "original-states"}}, ""),
    ])
    assert dashboards[0]["views"] == []
    assert len(warnungen) == 1
    assert "Strategie-Dashboard" in warnungen[0]


def test_unlesbares_dashboard_erscheint_ohne_ansichten_mit_warnung():
    dashboards, warnungen = forme_dashboards([
        ({"url_path": "yaml-dash", "title": "YAML"}, None, "config not found"),
    ])
    assert dashboards[0]["views"] == []
    assert len(warnungen) == 1
    assert "konnten nicht gelesen werden" in warnungen[0]


def test_ohne_titel_traegt_das_dashboard_seinen_pfad():
    dashboards, _ = forme_dashboards([
        ({"url_path": "dashboard-test"}, {"views": []}, ""),
    ])
    assert dashboards[0]["title"] == "dashboard-test"
