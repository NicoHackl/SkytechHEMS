# Architektur

> Beschreibt den **tatsächlichen** Stand. Geplantes, aber nicht Umgesetztes gehört nach
> [roadmap.md](roadmap.md), Abweichungen nach [bekannte-luecken.md](bekannte-luecken.md).

## Zweck und Abgrenzung

PV-Überschuss-Energiemanagementsystem als Home-Assistant-Add-on. Es verteilt den Solarüberschuss
zyklisch und prioritätsbasiert auf regelbare Verbraucher (Heizstab, Wallbox) und binäre
Verbraucher (Heizlüfter) — mit Zeitschutz, Hysterese, Rampenbegrenzung und Notabschaltung.

**Nicht** Aufgabe dieses Projekts:

- **Eigene Persistenz.** Es gibt keine Datenbank und keine Datei mit Zustand. Alles, was einen
  Neustart überleben soll, steht als HA-Helfer-Entität in Home Assistant. Auch die
  Konfigurationsseite legt nichts an: sie schreibt über die Supervisor-API dieselbe Optionsquelle,
  die die native Add-on-Seite bedient.
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
| `app/main.py` | Add-on-Optionen laden, Scheduler betreiben, HTTP-Routen bereitstellen, Steuerschema aus der Gerätekonfiguration ableiten | Regelentscheidungen treffen, Optionen selbst prüfen |
| `app/supervisor_client.py` | Einzige Stelle mit Supervisor-REST-Zugriff: eigene Optionen lesen, validieren, speichern, Add-on neu starten | Fachlogik enthalten, Token oder rohe Optionen loggen |
| `app/config_service.py` | Ablauf der Konfigurationsverwaltung: lesen, validieren, Revision prüfen, mischen, speichern, Altgeräte sicher deaktivieren, Neustart anstoßen | HTTP sprechen — die Handler übersetzen nur Ausnahmen in Statuscodes |
| `app/configuration.py` | Add-on-Optionen normalisieren und validieren, Modus-Listen parsen und stabil serialisieren, Revisions-Hash bilden, Diff für die sichere Deaktivierung liefern | HA oder den Supervisor ansprechen, Zustand halten |
| `app/formula.py` | Formel-basierte Sensorwerte (D-045): AST-Whitelist prüfen, eingeschränkten Code gegen ein fertiges Namespace-Dict auswerten | HA-Entitäten auflösen, Zustand zwischen Aufrufen halten, `exec`/`eval` auf kompiliertem Python verwenden |
| `app/ems/controller.py` | Einen Zyklus orchestrieren: globale Eingaben, Pool, Prioritätskaskade, Statusaufbau | Selbst HTTP sprechen |
| `app/ems/devices.py` | Verhalten je Gerätetyp: Eligibility, Pool-Verbrauch, Rampe, Zeitschutz, Write-Ops. Hierarchie: `Device` → `ControllableDevice` → `BatteryDevice`, daneben `BinaryDevice` | Auf HA zugreifen (bekommt einen `StateProxy`) |
| `app/ems/state.py` | Lesezugriff auf den State-Schnappschuss, Resolve-Vertrag (`has`, `availability`, `resolve_number/bool/select`), `safe_float`, `parse_ts` | Zustand halten, der einen Zyklus überdauert; klassenspezifische Defaultwerte kennen |
| `app/ha_client.py` | Einzige Stelle mit HA-Zugriff: REST für Zustände und Dienste, dazu **eine** WebSocket-Abfrage für die Dashboardliste (D-049), Session-Verwaltung, Timeouts; meldet je Schreiboperation Erfolg oder bereinigten Fehler zurück | Fachlogik enthalten, einen Fehlschlag im Regelpfad verschlucken |
| `app/ems/ops.py` | `WriteOp` (Operation samt verursachendem Gerät), `WriteResult`, `WriteTarget` | Selbst schreiben |
| `app/flow_publisher.py` | Anzeigedaten der Power Flow Card (D-046) aus Optionen, Steuerschema und Zyklusstatus bauen und als zwei `sensor.*`-Entitäten veröffentlichen | Ein Gerät schalten, eine Ausnahme nach außen lassen, Home Assistant zusätzlich abfragen |
| `web/` → `app/static/` | Darstellung und Bedienung | Fachlogik doppeln — sie rechnet nur an, was `/api/status` liefert |

Regel: Keine Komponente übernimmt Aufgaben einer anderen. Verschiebt sich eine Verantwortung,
ist das eine Design-Entscheidung → [design-entscheidungen.md](design-entscheidungen.md).

## Datenfluss

Ein Zyklus (`EMSController.run_cycle()`), ausgelöst alle `interval_s` Sekunden:

1. **Globale Eingaben** aus HA lesen (Freigabe, Regelmodus, globaler Puffer, Einschaltreserve,
   Überschuss-Sensor, Hausleistungsbilanz für AC-Speicher, Debug-Schalter). Ist für Überschuss
   oder Hausleistungsbilanz eine Formel (D-045) konfiguriert, wird sie **vor** der jeweiligen
   Einzel-Entität ausgewertet ([`app/formula.py`](../app/formula.py)); liefert sie einen
   gültigen, endlichen Wert, ersetzt dieser die Entität vollständig, sonst greift unverändert
   der Entitäts-Pfad. Welche Quelle wirkte, steht als `residual_source`/`battery_residual_source`
   im Status.
2. **Eligibility** je Gerät: Der globale Modus muss in `allowed_modes` liegen, `freigabe`,
   `technische_freigabe` und der Gerätemodus müssen passen.
3. **Netz bereinigen:** `residual_bereinigt_w = residual_w − Σ netz_support_w`. Nur Speicher
   liefern hier etwas; für alle Verbraucher ist `netz_support_w` gleich `0`. Ein Speicher ist kein
   Verbraucher mit Vorzeichen — seine Entladung erhöht `residual_w`, ist aber kein Überschuss.
   Erst bereinigen, dann regeln.
4. **Pool und Hausdefizit aus getrennten Sensoren:** Der PV-Pool bleibt
   `pool_roh_w = residual_bereinigt_w + Σ current_w`, daraus `pool_w = max(pool_roh_w, 0)`.
   Das Hausdefizit für `battery` stammt dagegen aus der separaten,
   vorzeichenbehafteten Hausleistungsbilanz:

   ```text
   battery_residual_bereinigt_w = battery_residual_w − Σ netz_support_w
   entlade_basis_w               = battery_residual_bereinigt_w + Σ gemessene_last_w
   hausdefizit_w                 = max(−entlade_basis_w, 0)
   ```

   Die zweite Summe filtert den Force-Modus **nicht** heraus: eine von Hand eingeschaltete
   HEMS-Last bleibt Überschussverbraucher und wird von keinem Speicher gedeckt. `current_w` zählt
   nur die **vom EMS angeforderte** Leistung — extern erzwungene Last („Force-Modus") steckt
   bereits im Überschuss-Sensor und wird nicht doppelt gutgeschrieben. Weil Pool und Entladung
   unterschiedliche Sensorverträge haben, können `pool_w` und `hausdefizit_w` diagnostisch
   gleichzeitig positiv sein; die Richtungsauflösung eines Speichers schreibt trotzdem immer nur
   einen signierten Sollwert. Liefert die Hausleistungsbilanz keinen gültigen Zahlenwert, fahren
   alle AC-Speicher sicher auf `standby`; der Pool für übrige Verbraucher bleibt verfügbar.
5. **Phasenauswahl** für regelbare Ampere-Geräte mit `phases="1,3"`: höchste Phasenzahl, für die
   `floor(pool_w / (phases × U)) ≥ min_technisch_a` gilt, gebremst durch `phase_switch_delay_s`.
6. **Defizit** aus `residual_bereinigt_w` ermitteln und prüfen, ob die regelbaren Geräte es
   allein abregeln können (`binary_immediate_off`). Bereinigt, nicht roh: sonst verschwindet das
   Defizit, sobald ein Speicher die Hauslast deckt, und die Verbraucher liefen faktisch aus der
   Batterie.
7. **Pool nach Priorität verteilen**: regelbare Geräte reservieren ihre Schutzleistung, binäre
   Geräte ermitteln ihre hysteresebehaftete Wunschvorgabe. `protected_minimum_scope` entscheidet,
   ob der Schutz ausschließlich gegen Binärgeräte wirkt (`binary_only`) oder anschließend auch
   die Reihenfolge der regelbaren Zuteilung bestimmt (`binary_and_controllable`).
8. **Kandidat** je binärem Gerät unter Mindestlaufzeit, Abschaltverzögerung und Mindestauszeit.
9. **Prioritätskaskade** (Demotion/Promotion) und **One-Change-Limit** anwenden.
10. **Allocation** der regelbaren Geräte aus dem verbleibenden Pool: Im Standardmodus zuerst
    technische Minima, danach Zusatzleistung. Im erweiterten Modus zuerst die geschützten
    Mindestleistungen in Prioritätsreihenfolge — der reine Helferwert, ohne `reserve_w` und
    globalen Puffer —, danach Zusatzleistung. Bei sinkendem Pool verschwinden dadurch erst
    Anteile oberhalb der Sockel, dann die Sockel des niedrigsten Teilnehmers.
11. **Entladeplanung:** `hausdefizit_w` wird **einmal** über alle entladebereiten Speicher
    aufgeteilt, strikt nach `entlade_prioritat`. Rechnete jeder Speicher für sich, entladen bei
    drei Speichern und 2 kW Defizit alle drei mit 2 kW. Muss nach Schritt 10 und vor Schritt 12
    laufen — der Speicher löst dort seine Richtung auf.
12. **Rampenbegrenzung** der Sollwerte, bei Defizit sofortiger Run-down.
13. **Write-Ops** sammeln, bei `output_unit=ampere` von Watt in ganze Ampere abrunden und gegen die
    HA-REST-API ausführen; optional das Post-Cycle-Skript auslösen. Jede Operation trägt ihr
    verursachendes Gerät; das Ergebnis geht an den Controller zurück.
14. **Kartendaten veröffentlichen** (`app/flow_publisher.py`, nur bei `flow_publish: true`):
    Aus dem fertigen Status und dem bereits geholten Zustandsabbild entstehen die beiden
    Anzeige-Sensoren der Power Flow Card. Der Schritt liegt **nach** dem Zyklus, nicht darin:
    er löst keine zusätzliche HA-Abfrage aus, trifft keine Regelentscheidung und verschluckt
    jeden Fehler. Die Konfigurationsentität wird nur geschrieben, wenn sich ihr Revisionshash
    geändert hat oder sie im Zustandsabbild fehlt — Letzteres deckt den HA-Neustart ab, nach dem
    per `POST /api/states` erzeugte Entitäten verschwinden. Datenvertrag:
    [`vertrag_powerflow_card_hems/kontrakt.md`](../vertrag_powerflow_card_hems/kontrakt.md).

Zwischen Schritt 2 und 3 steht ein hartes Gate: **Schreibziel-Gesundheit.** Für jedes Gerät wird
geprüft, ob seine Ausgabe-Entitäten im Schnappschuss vorhanden, verfügbar, von der richtigen Domain
und ausreichend konfiguriert sind (`input_select` mit den nötigen Optionen, der Speicher-Sollwert
mit negativem Minimum). Fehlt oder taugt eines davon — oder ist der letzte Schreibversuch
fehlgeschlagen — wird **nur dieses** Gerät `runtime_active: false`: es bekommt keine Zuteilung,
schreibt aber weiter seinen sicheren Zustand, damit eine reparierte Entität ohne Add-on-Neustart
wieder eingefangen wird.

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
│   ├── configuration.py    Optionen normalisieren, validieren, Revision und Diff
│   ├── config_service.py   Ablauf der Konfigurationsverwaltung (ohne HTTP)
│   ├── supervisor_client.py Supervisor-REST-Client für die eigenen Optionen
│   ├── ha_client.py        HA-REST-Client
│   ├── flow_publisher.py   Anzeigedaten der Power Flow Card (D-046)
│   ├── requirements.txt    Laufzeit-Abhängigkeiten des Containers
│   ├── ems/
│   │   ├── controller.py   EMSController, config-getriebene Geräte-Registry
│   │   ├── devices.py      Device / ControllableDevice / BinaryDevice / BatteryDevice
│   │   ├── ops.py          WriteOp, WriteResult, WriteTarget
│   │   └── state.py        StateProxy, Resolve-Vertrag, safe_float, parse_ts
│   └── static/             gebautes SPA-Bundle (eingecheckt, D-035)
├── web/                    Quellen der Oberfläche (React + TypeScript + Vite)
├── tests/                  pytest, inklusive Hypothesis-Property-Tests
├── erweiterungen/          Entwürfe für geplante Ausbaustufen
├── vertrag_powerflow_card_hems/  Datenvertrag und Umsetzungsplan der Power Flow Card
└── docs/                   diese Doku
```

## Invarianten

Zusagen, auf die sich der gesamte Code verlässt. Wer eine davon bricht, bricht das System:

1. **Der Gerätename ist die Identität.** `name` aus der Konfiguration ist die stabile ID und taucht
   unverändert als `id` in `/api/status` auf; `label` ist reine Anzeige und darf sich ändern.
2. **Nur der `HAClient` spricht mit Home Assistant.** Geräte und Controller sehen ausschließlich
   einen `StateProxy` auf einen Schnappschuss. Das gilt auch für die WebSocket-Abfrage der
   Dashboardliste (D-049) — sie liegt im selben Client und außerhalb des Regelpfads.
3. **Ein Zyklus liest einen Schnappschuss.** Innerhalb eines Zyklus ändert sich der gelesene
   Zustand nicht — sonst wären Pool und Zuteilung inkonsistent.
4. **Im Regelpfad werden ausschließlich `input_*`-Helfer geschrieben.** Reale Geräte schaltet
   Home Assistant. Darüber hinaus veröffentlicht das Add-on reine Anzeigedaten als eigene
   `sensor.*`-Entitäten, die kein Gerät schalten und in keiner Regelentscheidung vorkommen
   (D-046). Der Regelpfad selbst bleibt davon unberührt.
5. **Ein Zyklusfehler schaltet nichts.** Schlägt der Zyklus fehl, bleibt der letzte Sollwert
   stehen; die Anlage fällt nicht in einen undefinierten Zustand.
6. **Ein Speicher lädt und entlädt nie gleichzeitig.** Sein einzelner signierter Sollwert und die
   Richtungsauflösung wählen stets genau `laden`, `entladen` oder `standby`. Pool und
   Hausdefizit nutzen bewusst unterschiedliche Sensoren und können im Status gleichzeitig
   positiv sein; das ist kein zweiter Leistungspfad.
7. **Der sichere Zustand eines Speichers wird aktiv geschrieben.** Bei Lockout, fehlender
   Freigabe oder unbrauchbaren Messwerten schreibt das HEMS `0 W` und `standby` — es lässt den
   Sollwert nicht einfach stehen. Sonst entlädt der Speicher nach einem Add-on-Absturz bis leer.
8. **Mindestlaufzeit und Abschaltverzögerung gelten auch bei Notabschaltung** — Geräteschutz
   schlägt Regelgüte (siehe [design-entscheidungen.md](design-entscheidungen.md)).
9. **Ein defektes Gerät legt nur sich selbst still.** Ein fehlendes oder nicht beschreibbares
   Schreibziel und ein fehlgeschlagener Service-Aufruf werden dem verursachenden Gerät zugeordnet
   und im Status sichtbar gemacht; die übrigen Geräte regeln weiter, und der Zyklus gilt nicht als
   fehlgeschlagen.
10. **Ein gültiger Wert `0` wird nie durch einen Ersatzwert verdrängt.** Jede Auflösung eines
   HA-States läuft über den Resolve-Vertrag in [`app/ems/state.py`](../app/ems/state.py) und meldet
   neben dem Wert auch Ursache (`valid`, `missing`, `unavailable`, `invalid`) und Quelle (`ha`,
   `addon`, `internal`). Wahrheitswert-Ausdrücke wie `wert or fallback` sind damit ausgeschlossen.
11. **Eine Formel (D-045) ist nie ein zweiter, stiller Mechanismus.** Liefert sie einen gültigen
    Wert, ersetzt sie die konfigurierte Entität vollständig; sonst greift unverändert der
    Entitäts-Pfad — nie eine Mischung aus beidem. Welche Quelle gerade wirkt, steht immer im
    Status (`residual_source`/`battery_residual_source`), nie nur im Log (Lehre aus
    [D-041](design-entscheidungen.md)). Der Formel-Interpreter selbst wirft nie: jeder Fehler wird
    zu `valid: false`, ein Regelzyklus bricht an einer kaputten Formel nicht ab.

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
