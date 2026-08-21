# Skytech HEMS

PV-Überschuss-Energiemanagementsystem als Home-Assistant-Add-on. Es verteilt den Solarüberschuss
zyklisch und prioritätsbasiert auf regelbare Verbraucher (Heizstab, Wallbox), binäre Verbraucher
(Heizlüfter) und AC-gekoppelte Speicher — mit Zeitschutz, Hysterese, Rampenbegrenzung und
Notabschaltung.

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

## AC-Speicher (`class: battery`)

Ein Speicher ist das einzige Gerät, das Leistung auch **abgeben** kann. Er wird aus PV-Überschuss
geladen und entlädt zur Deckung des **normalen Hausverbrauchs** — ausdrücklich **nicht** für die
Überschussverbraucher. Der Heizstab läuft also nie aus der Batterie.

### Was das HEMS schreibt, und was nicht

Das Add-on schreibt zwei HA-Helfer:

```
input_number.ems_<prefix>_anforderung_leistung_w    # + laden / − entladen
input_select.ems_<prefix>_anforderung_betriebsart   # laden | entladen | standby
```

Die Übersetzung in Modbus- oder MQTT-Aufrufe übernimmt eine **HA-Automation**, nicht das Add-on.
Register, Reihenfolge am Gerät und Übernahmezeit sind damit kein HEMS-Thema.

> **Der Leistungs-Helfer braucht ein negatives Minimum.** Steht dort `min: 0`, klemmt Home
> Assistant jede Entladeanforderung serverseitig auf 0 und der Speicher entlädt nie.

### Vor der Inbetriebnahme prüfen

1. **Steckt der Speicher im Überschuss-Sensor?** EMS deaktivieren, Speicher von Hand auf 1 kW
   Entladung zwingen, den Sensor beobachten. Steigt er um 1 kW, gehört
   `speicher_in_residual_enthalten` auf `true` (Default). Ein Fehler hier lässt das HEMS die
   eigene Entladung als Überschuss lesen — der Speicher ist dann in einem Zyklus leer.
2. **Hausleistungsbilanz einrichten.** `battery_residual_power_entity` ist bei AC-Speichern
   Pflicht und enthält Netzleistung plus E3DC-Batterieleistung: negativ = Unterdeckung, positiv =
   Einspeisung. Sie steuert ausschließlich das Entladen; das Laden bleibt am Überschuss-Sensor.
   Die drei Kontrollfälle mit `700 W` und die HA-Template-Vorlage stehen in
   [konfiguration.md](docs/konfiguration.md#hausleistungsbilanz-für-ac-speicher).
3. **E3DC-Übergabe messen.** Bei einer E3DC-Entladung fordert das HEMS den AC-Speicher an; der
   E3DC muss anschließend selbst zurückregeln. In dieser Anlage reagiert er in unter zwei
   Sekunden bei einem HEMS-Zyklus von drei Sekunden. Liegt die Reaktionszeit darüber oder
   oszilliert sie, `hoch_regelzeit_s` und Schrittbegrenzung erhöhen.
4. **Eigene Nulleinspeisung des Geräts abschalten.** Zwei Regler auf einer Messgröße haben kein
   Gleichgewicht; das Ergebnis ist ein Grenzzyklus.

### Watchdog — Pflicht, nicht Empfehlung

Stirbt das Add-on, während ein Entlade-Sollwert in HA steht, entlädt der Speicher weiter bis leer.
Es gibt keine autonome Rückfallebene, die das auffängt. Deshalb:

1. **Heartbeat.** Ein HA-Skript setzt `input_datetime.ems_letzter_zyklus` auf `now()`; das Add-on
   ruft es über die Option `post_cycle_script` nach jedem Zyklus auf. Ist der Slot schon belegt,
   bekommt das vorhandene Skript diese Aktion zusätzlich.
2. **Totmann-Automation.** Ist der Zeitstempel älter als 3 × `interval_s` (`for: 00:02:00`), alle
   `ems_*_anforderung_leistung_w` auf 0 und alle `…_anforderung_betriebsart` auf `standby`
   setzen — **beides**, nicht nur die Leistung.
3. **Geräteseitiger Watchdog**, falls vorhanden. Die einzige Ebene, die auch einen HA-Ausfall
   überlebt.

### Ein Hinweis zur Anzeige

Läuft ein HEMS-Gerät von Hand (Force-Modus), sinkt das Hausdefizit um dessen volle Istleistung und
der Restbezug erscheint am Netz statt aus dem Speicher. **Das ist gewollt** — ein von Hand
eingeschalteter Heizstab bleibt ein Überschussverbraucher. Im Energiedashboard sieht es trotzdem
wie ein Regelfehler aus; die Statuskachel „Hausdefizit" benennt den Betrag deshalb ausdrücklich.

Ein Speicher, der sich **selbst** regelt und nicht vom HEMS gesteuert wird, gehört **nicht** in die
Geräteliste. Seine Leistung steckt bereits im Überschuss-Sensor; als `battery` eingetragen würde
sie zweimal abgezogen.

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
