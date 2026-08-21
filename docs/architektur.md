# Architektur

> Beschreibt den **tatsächlichen** Stand. Geplantes, aber nicht Umgesetztes gehört nach
> [roadmap.md](roadmap.md), Abweichungen nach [bekannte-luecken.md](bekannte-luecken.md).

## Zweck und Abgrenzung

PV-Überschuss-Energiemanagementsystem als Home-Assistant-Add-on. Es verteilt den Solarüberschuss
zyklisch und prioritätsbasiert auf regelbare Verbraucher (Heizstab, Wallbox) und binäre
Verbraucher (Heizlüfter) — mit Zeitschutz, Hysterese, Rampenbegrenzung und Notabschaltung.

**Nicht** Aufgabe dieses Projekts:

- **Eigene Persistenz.** Es gibt keine Datenbank und keine Datei mit Zustand. Alles, was einen
  Neustart überleben soll, steht als HA-Helfer-Entität in Home Assistant.
- **Anlegen der HA-Helfer.** Das Add-on liest und schreibt sie, erzeugt sie aber nicht.
- **Prognose und Planung.** Vorausschauende Optimierung liefert der separate **Energy Pilot**;
  HEMS übernimmt dessen Vorschläge nur, siehe [datenmodell.md](datenmodell.md).
- **Direktes Schalten der Endgeräte.** Geschrieben werden ausschließlich `input_*`-Helfer;
  die Übersetzung in reale Schaltvorgänge erledigen HA-Automationen.

## Tech-Stack

| Schicht | Technologie | Warum |
|---|---|---|
| Sprache / Laufzeit | Python 3.11 | Standard im HA-Umfeld, `asyncio` im Kern der Sprache |
| Webserver / HTTP | aiohttp | Ein Framework für Scheduler **und** Weboberfläche, ohne zweiten Prozess |
| Oberfläche | React 18 + TypeScript (`strict`) + Vite | Eiserne Regel 8, siehe [frontend.md](frontend.md) |
| Auslieferung | Docker-Image als HA-Add-on mit Ingress | Installation über das Add-on-Repository, Authentifizierung über den Supervisor |
| Tests | pytest + Hypothesis | Property-Tests decken die Verteilungslogik breiter ab als Beispieltests, siehe [test-strategie.md](test-strategie.md) |

## Komponenten

```text
  ┌──────────────┐   Zyklus alle    ┌────────────────┐   liest/schreibt   ┌──────────────┐
  │  main.py     │ ───interval_s──► │ EMSController  │ ─────────────────► │  HAClient    │
  │  Scheduler   │                  │ (ems/          │                    │ ha_client.py │
  │  + Webserver │ ◄──status/────── │  controller.py)│                    └──────┬───────┘
  └──────┬───────┘   write_ops      └───────┬────────┘                           │ REST
         │ JSON                             │ hält                               ▼
         ▼                                  ▼                            ┌──────────────┐
  ┌──────────────┐                  ┌────────────────┐                   │ Home         │
  │ SPA (web/)   │                  │ Device-Objekte │                   │ Assistant    │
  │ app/static/  │                  │ (ems/devices)  │                   └──────────────┘
  └──────────────┘                  └────────────────┘
```

| Komponente | Verantwortung | Darf nicht |
|---|---|---|
| `app/main.py` | Add-on-Optionen laden, Scheduler betreiben, HTTP-Routen bereitstellen, Steuerschema aus der Gerätekonfiguration ableiten | Regelentscheidungen treffen |
| `app/ems/controller.py` | Einen Zyklus orchestrieren: globale Eingaben, Pool, Prioritätskaskade, Statusaufbau | Selbst HTTP sprechen |
| `app/ems/devices.py` | Verhalten je Gerätetyp: Eligibility, Pool-Verbrauch, Rampe, Zeitschutz, Write-Ops. Hierarchie: `Device` → `ControllableDevice` → `BatteryDevice`, daneben `BinaryDevice` | Auf HA zugreifen (bekommt einen `StateProxy`) |
| `app/ems/state.py` | Lesezugriff auf den State-Schnappschuss, `safe_float`, `parse_ts` | Zustand halten, der einen Zyklus überdauert |
| `app/ha_client.py` | Einzige Stelle mit HA-REST-Zugriff, Session-Verwaltung, Timeouts | Fachlogik enthalten |
| `web/` → `app/static/` | Darstellung und Bedienung | Fachlogik doppeln — sie rechnet nur an, was `/api/status` liefert |

Regel: Keine Komponente übernimmt Aufgaben einer anderen. Verschiebt sich eine Verantwortung,
ist das eine Design-Entscheidung → [design-entscheidungen.md](design-entscheidungen.md).

## Datenfluss

Ein Zyklus (`EMSController.run_cycle()`), ausgelöst alle `interval_s` Sekunden:

1. **Globale Eingaben** aus HA lesen (Freigabe, Regelmodus, globaler Puffer, Einschaltreserve,
   Überschuss-Sensor, Debug-Schalter).
2. **Eligibility** je Gerät: Der globale Modus muss in `allowed_modes` liegen, `freigabe`,
   `technische_freigabe` und der Gerätemodus müssen passen.
3. **Netz bereinigen:** `residual_bereinigt_w = residual_w − Σ netz_support_w`. Nur Speicher
   liefern hier etwas; für alle Verbraucher ist `netz_support_w` gleich `0`. Ein Speicher ist kein
   Verbraucher mit Vorzeichen — seine Entladung erhöht `residual_w`, ist aber kein Überschuss.
   Erst bereinigen, dann regeln.
4. **Pool und Hausdefizit** aus zwei Summen: `pool_roh_w = residual_bereinigt_w + Σ current_w`
   und `entlade_basis_w = residual_bereinigt_w + Σ gemessene_last_w`. Daraus
   `pool_w = max(pool_roh_w, 0)` und `hausdefizit_w = max(−entlade_basis_w, 0)`; bei Lockout oder
   EMS aus beide `0`. Die zweite Summe filtert den Force-Modus **nicht** heraus: eine von Hand
   eingeschaltete HEMS-Last bleibt Überschussverbraucher und wird von keinem Speicher gedeckt.
   Weil je Gerät `gemessene_last_w ≥ current_w` gilt, schließen `pool_w` und `hausdefizit_w`
   einander strukturell aus. `current_w` zählt
   nur die **vom EMS angeforderte** Leistung — extern erzwungene Last („Force-Modus") steckt
   bereits in `residual_w` und wird nicht doppelt gutgeschrieben.
5. **Phasenauswahl** für regelbare Ampere-Geräte mit `phases="1,3"`: höchste Phasenzahl, für die
   `floor(pool_w / (phases × U)) ≥ min_technisch_a` gilt, gebremst durch `phase_switch_delay_s`.
6. **Defizit** aus `residual_bereinigt_w` ermitteln und prüfen, ob die regelbaren Geräte es
   allein abregeln können (`binary_immediate_off`). Bereinigt, nicht roh: sonst verschwindet das
   Defizit, sobald ein Speicher die Hauslast deckt, und die Verbraucher liefen faktisch aus der
   Batterie.
7. **Pool nach Priorität verteilen**: regelbare Geräte reservieren ihre Schutzleistung, binäre
   Geräte ermitteln ihre hysteresebehaftete Wunschvorgabe.
8. **Kandidat** je binärem Gerät unter Mindestlaufzeit, Abschaltverzögerung und Mindestauszeit.
9. **Prioritätskaskade** (Demotion/Promotion) und **One-Change-Limit** anwenden.
10. **Allocation** der regelbaren Geräte aus dem verbleibenden Pool.
11. **Entladeplanung:** `hausdefizit_w` wird **einmal** über alle entladebereiten Speicher
    aufgeteilt, strikt nach `entlade_prioritat`. Rechnete jeder Speicher für sich, entladen bei
    drei Speichern und 2 kW Defizit alle drei mit 2 kW. Muss nach Schritt 10 und vor Schritt 12
    laufen — der Speicher löst dort seine Richtung auf.
12. **Rampenbegrenzung** der Sollwerte, bei Defizit sofortiger Run-down.
13. **Write-Ops** sammeln, bei `output_unit=ampere` von Watt in ganze Ampere abrunden und gegen die
    HA-REST-API ausführen; optional das Post-Cycle-Skript auslösen.

Die Geräteobjekte leben über alle Zyklen hinweg. Dadurch bleiben interne Timer (z. B.
`_off_since_ts`) ohne zusätzliche HA-Helfer erhalten — ein Add-on-Neustart setzt sie zurück.

Details zu Formaten: [datenmodell.md](datenmodell.md).
Details zu Endpunkten: [api-referenz.md](api-referenz.md).

## Verzeichnisstruktur

```text
.
├── Dockerfile              Add-on-Image (python:3.11-slim, aiohttp)
├── config.yaml             Add-on-Manifest: Version, Optionen, Schema, Ingress
├── repository.yaml         Manifest des Custom-Repositories
├── translations/           Feldbeschreibungen der Add-on-Optionen (de, en)
├── app/
│   ├── main.py             Scheduler, HTTP-Routen, Steuerschema
│   ├── ha_client.py        HA-REST-Client
│   ├── requirements.txt    Laufzeit-Abhängigkeiten des Containers
│   ├── ems/
│   │   ├── controller.py   EMSController, config-getriebene Geräte-Registry
│   │   ├── devices.py      Device / ControllableDevice / BinaryDevice
│   │   └── state.py        StateProxy, safe_float, parse_ts
│   └── static/             gebautes SPA-Bundle (eingecheckt, D-035)
├── web/                    Quellen der Oberfläche (React + TypeScript + Vite)
├── tests/                  pytest, inklusive Hypothesis-Property-Tests
├── erweiterungen/          Entwürfe für geplante Ausbaustufen
└── docs/                   diese Doku
```

## Invarianten

Zusagen, auf die sich der gesamte Code verlässt. Wer eine davon bricht, bricht das System:

1. **Der Gerätename ist die Identität.** `name` aus der Konfiguration ist die stabile ID und taucht
   unverändert als `id` in `/api/status` auf; `label` ist reine Anzeige und darf sich ändern.
2. **Nur der `HAClient` spricht mit Home Assistant.** Geräte und Controller sehen ausschließlich
   einen `StateProxy` auf einen Schnappschuss.
3. **Ein Zyklus liest einen Schnappschuss.** Innerhalb eines Zyklus ändert sich der gelesene
   Zustand nicht — sonst wären Pool und Zuteilung inkonsistent.
4. **Geschrieben werden ausschließlich `input_*`-Helfer.** Reale Geräte schaltet Home Assistant.
5. **Ein Zyklusfehler schaltet nichts.** Schlägt der Zyklus fehl, bleibt der letzte Sollwert
   stehen; die Anlage fällt nicht in einen undefinierten Zustand.
6. **Ein Speicher lädt und entlädt nie gleichzeitig.** Das ist keine nachträgliche Prüfung,
   sondern eine Eigenschaft der Formeln aus Schritt 4: `pool_w > 0` und `hausdefizit_w > 0`
   schließen sich mathematisch aus.
7. **Der sichere Zustand eines Speichers wird aktiv geschrieben.** Bei Lockout, fehlender
   Freigabe oder unbrauchbaren Messwerten schreibt das HEMS `0 W` und `standby` — es lässt den
   Sollwert nicht einfach stehen. Sonst entlädt der Speicher nach einem Add-on-Absturz bis leer.
8. **Mindestlaufzeit und Abschaltverzögerung gelten auch bei Notabschaltung** — Geräteschutz
   schlägt Regelgüte (siehe [design-entscheidungen.md](design-entscheidungen.md)).

## Start und Betrieb

```bash
pip install -r requirements-dev.txt -r app/requirements.txt
cd web && npm install && npm run build     # Bundle nach app/static/
```

Lokal gegen eine bestehende HA-Instanz:

```bash
export HA_URL=http://homeassistant.local:8123
export HA_TOKEN=<long-lived-access-token>
python app/main.py                          # Oberfläche unter http://localhost:8099
```

Als Container:

```bash
docker build -t skytech-hems .
docker run --rm -p 8099:8099 -e HA_URL=… -e HA_TOKEN=… skytech-hems
```

Konfiguration: [konfiguration.md](konfiguration.md).
