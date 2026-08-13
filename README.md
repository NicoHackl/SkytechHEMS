# Skytech HEMS

PV-Überschuss-Energiemanagementsystem als Home-Assistant-Add-on. Es verteilt den Solarüberschuss
zyklisch und prioritätsbasiert auf regelbare Verbraucher (Heizstab, Wallbox) und binäre Verbraucher
(Heizlüfter) — mit Zeitschutz, Hysterese, Rampenbegrenzung und Notabschaltung.

Bedient wird es über ein Ingress-Panel und Home-Assistant-Helfer-Entitäten. Eine eigene Persistenz
gibt es nicht: gelesen und geschrieben wird ausschließlich der HA-State.

## Installation

Als Add-on über ein Custom-Repository:

1. In Home Assistant: **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
2. Repository-URL `https://github.com/nicohackl/SkytechHEMS` eintragen
3. „Skytech HEMS" installieren und starten
4. Ingress-Panel **HEMS** in der Seitenleiste öffnen

Der `SUPERVISOR_TOKEN` steht im Add-on automatisch zur Verfügung — eine zusätzliche
Authentifizierung ist nicht nötig.

## Nutzung

Die Oberfläche hat drei Seiten:

| Seite | Inhalt |
|---|---|
| **Status** | Live-Anzeige von Modus, Überschuss, Pool, Defizit und je Gerät Freigabe, Ist-Leistung, Sollwert, Zuteilung, Schutzleistung sowie laufende Timer |
| **Steuerung** | Alle relevanten Helfer je Gerät und global direkt einstellbar — Schalter, Zahlenfelder, Auswahllisten |
| **Energy Pilot** | Plan-Status und die Vorschläge des Energy-Pilot-Add-ons, reine Anzeige |

Welche Geräte es gibt, steht in den Add-on-Optionen; welche Helfer sie brauchen, in
[docs/datenmodell.md](docs/datenmodell.md). Ein neues Gerät braucht einen Eintrag in den Optionen,
die zugehörigen HA-Helfer und einen Add-on-Neustart — keine Codeänderung.

## Schnellstart für Entwickler

```bash
pip install -r requirements-dev.txt -r app/requirements.txt
cd web && npm install && npm run build      # Bundle nach app/static/

export HA_URL=http://homeassistant.local:8123
export HA_TOKEN=<long-lived-access-token>
python app/main.py                          # Oberfläche unter http://localhost:8099
```

## Entwicklung

```bash
pytest -q                  # Tests
ruff check app tests       # Linting
cd web && npm run dev      # Oberfläche mit Hot Reload, Proxy auf Port 8099
```

Vor dem ersten Commit lesen: [CONTRIBUTING.md](CONTRIBUTING.md).

## Dokumentation

| Wofür | Wo |
|---|---|
| Verbindliche Projektregeln (Menschen **und** KI-Agenten) | [AGENTS.md](AGENTS.md) |
| Technische Referenz | [docs/README.md](docs/README.md) |
| Add-on-Optionen und Helfer-Entitäten | [docs/konfiguration.md](docs/konfiguration.md), [docs/datenmodell.md](docs/datenmodell.md) |
| Änderungen je Version | [CHANGELOG.md](CHANGELOG.md) |

## Lizenz

Privates Projekt, keine Lizenz erteilt.
