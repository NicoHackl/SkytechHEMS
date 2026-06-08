# Claude-Analyse – Skytech HEMS

**Analysedatum:** 2026-06-07
**Analysiertes Repository:** `NicoHackl/SkytechHEMS`
**Version:** 1.0.23 (laut `config.yaml`)
**Umfang:** Home-Assistant-Add-on (PV-Überschuss-Energiemanagement), Python/aiohttp,
ca. 1.360 Zeilen Code (`app/`) + Web-UI + Konfiguration.

Diese Analyse betrachtet das Repository sowohl **technisch** (Codequalität,
Sauberkeit, Wartbarkeit, Zukunftssicherheit, Sicherheit) als auch **fachlich**
(Regel-Logik, Plausibilität, Ungereimtheiten). Jede Erkenntnis ist mit einer
Fundstelle `Datei:Zeile` versehen.

---

## Inhalt

- [Gesamteindruck](#gesamteindruck)
- [🔴 Fehler / Bugs](#-fehler--bugs)
- [🟠 Fachliche Ungereimtheiten & Risiken](#-fachliche-ungereimtheiten--risiken)
- [🟡 Code-Qualität & Wartbarkeit](#-code-qualität--wartbarkeit)
- [🔵 Sicherheit](#-sicherheit)
- [🟢 Zukunftssicherheit](#-zukunftssicherheit)
- [💡 Verbesserungsvorschläge (priorisiert)](#-verbesserungsvorschläge-priorisiert)
- [✅ Positives / Stärken](#-positives--stärken)

---

## Gesamteindruck

Das Projekt hinterlässt einen **überdurchschnittlich gepflegten Eindruck**. Die
Architektur ist sauber geschnitten (klare Trennung `main.py` ↔ `ha_client.py` ↔
`ems/`-Domänenlogik), die EMS-Logik ist gut kommentiert und konsequent
config-driven aufgebaut. Die README ist außergewöhnlich ausführlich.

Die wesentlichen Schwächen liegen in drei Bereichen:

1. **Keine automatisierten Tests** für eine fachlich nicht-triviale Regel-Logik
   (Prioritätskaskade, Rampen, Phasenumschaltung, Zeit-Guards).
2. **Inkonsistente „Config-driven"-Philosophie**: Geräte sind frei
   konfigurierbar, die *globalen* Entitäten (insb. der zentrale Überschuss-Sensor)
   sind dagegen hart codiert.
3. **HTTP-Client-Handling** (neue `ClientSession` pro Aufruf) und einige
   Aufräum-/Robustheitsdetails.

Keiner der Punkte ist akut kritisch – das Add-on dürfte im Normalbetrieb stabil
laufen – aber sie betreffen Wartbarkeit und Erweiterbarkeit.

---

## Umsetzungsstatus (Stand 2026-06-08)

Die folgenden Punkte wurden auf dem Umsetzungs-Branch bearbeitet. Verifiziert
über `ruff check` (sauber) und `pytest` (**42 Tests grün**) sowie einen
Smoke-Test von `run_cycle`.

| Punkt | Status | Umsetzung |
|-------|--------|-----------|
| **F1** | ✅ behoben | `voltage_entity` → `voltage_l1/l2/l3_entity` in `config.yaml`, README und Übersetzungen korrigiert. |
| **F2** | ✅ behoben | Sensorname auf `…_uberschussverbraucher` (fehlendes „s") korrigiert; HA-Umlaut-Slugifizierung (ü→u, ö→o, ä→a, ß→ss) dokumentiert. |
| **F3** | ✅ behoben | Neue Add-on-Option `residual_power_entity` (Schema + Default in `config.yaml`, `main.py`, `EMSController`); Überschuss-Sensor frei konfigurierbar. |
| **A1** | ⏸️ unverändert | Bewusste Designentscheidung (Geräteschutz vor Netzschonung) – beibehalten. |
| **A2** | ✅ behoben | README-Hinweis zur erwarteten Sensor-Semantik (Pool-Rückrechnung) ergänzt. |
| **A3** | ✅ behoben/bestätigt | Ladestart wählt höchstmögliche Phase; bei geringem Überschuss Fallback auf einphasig mit entsprechender Ampere-Zahl. Verhalten per Test abgesichert. |
| **A4** | ✅ behoben | Exakte Float-Vergleiche durch `EPS_W`-Schwelle ersetzt (`devices.py`). |
| **A5** | ⏸️ unverändert | Magic Number nicht angefragt – belassen. |
| **Q1** | ✅ behoben | Pytest-Suite (`tests/`, 42 Tests) für State, Binär-/Regelbar-Geräte und Controller. |
| **Q2** | ✅ behoben | Langlebige `aiohttp.ClientSession` + `close()` statt Session pro Request. |
| **Q3** | ✅ behoben | Ungenutzten `os`-Import in `main.py` entfernt. |
| **Q4** | ✅ behoben | Tote Basis-Methode `Device.allocate` entfernt. |
| **Q5** | ✅ behoben | `Optional[Dict[...]] = None` in `call_service`. |
| **Q6** | ✅ behoben | `controllable_relief` → `total_relief_w`. |
| **Q7** | ✅ behoben | Einheitliche Zeitquelle `time.time()` (Controller-`now_ts` durchgereicht, Geräte nutzen `_now_ts`). |
| **Q8** | ✅ behoben | CI-Workflow `ci.yaml` (Ruff + Pytest) + `pyproject.toml`. |
| **Q9** | ✅ behoben | Web-UI in `index.html` + `static/styles.css` + `static/app.js` aufgeteilt; Inline-Handler → Event-Delegation. |
| **Q10** | ✅ behoben | Code-Kommentare durchgängig auf Deutsch. |
| **S1** | ⏸️ unverändert | Auf Wunsch belassen (HEMS aktuell Single-User). |
| **S2** | ⏸️ unverändert | Vorerst belassen. |
| **S3** | ✅ behoben | `esc()`-HTML-Escaping aller dynamischen Werte in `app.js`. |
| **S4** | ✅ behoben | `aiohttp` 3.9.5 → 3.11.11; Dependabot (`.github/dependabot.yml`). |
| **Z1** | ✅ behoben | Dockerfile-Basis `python:3.11-slim`. |
| **Z2** | ⏸️ unverändert | Versionsstrategie vorerst belassen. |
| **Z3** | ⏸️ unverändert | State-Pull vorerst belassen. |
| **Z4** | ✅ behoben | Graceful Shutdown (SIGTERM/SIGINT, Scheduler-Cancel, Session-/Runner-Cleanup). |
| **Z5** | ✅ behoben | `.dockerignore` ergänzt. |

---

## 🔴 Fehler / Bugs

### F1 – Dokumentations-Inkonsistenz: `voltage_entity` vs. `voltage_l1/l2/l3_entity`
**`config.yaml:18`**

Die eingebettete Beschreibung nennt ein einzelnes Feld
`voltage_entity (optional, HA-Sensor für Phasenspannung, Fallback 230 V)`.
Tatsächlich existiert dieses Feld **nirgends** – Code, Schema (`config.yaml:80-82`)
und README verwenden drei getrennte Felder `voltage_l1_entity`,
`voltage_l2_entity`, `voltage_l3_entity` (`devices.py:114-116`).
→ Veraltete Beschreibung, die Anwender in die Irre führt. Ein gesetztes
`voltage_entity` würde stillschweigend ignoriert.

### F2 – Tippfehler im hart codierten Sensornamen
**`controller.py:24`**

```python
HA_RESIDUAL_W = "sensor.verfugbare_leistung_fur_uberschusverbraucher"
```

Der Entitätsname enthält gleich mehrere Schreibinkonsistenzen
(`verfugbare` statt `verfügbare/verfuegbare`, `fur` statt `fuer`,
`uberschusverbraucher` statt `ueberschuss…` – ein „s" fehlt). Da der Name
hart codiert ist (siehe F3), muss der Anwender genau diesen „verstümmelten"
Namen in HA nachbauen. Jeder Tippfehler bei der HA-Helfer-Anlage führt zu
**Hard-Lockout** (`controller.py:149-151`) – also dem Abschalten aller
Verbraucher – ohne offensichtlichen Grund.

### F3 – Zentraler Überschuss-Sensor ist nicht konfigurierbar
**`controller.py:24`, verwendet in `controller.py:143`**

Während Geräte vollständig über `config.yaml` konfigurierbar sind, ist der
**wichtigste Eingangswert des gesamten Systems** – der PV-Überschuss – als
String-Konstante festverdrahtet. Eine Installation mit anderem Sensornamen
kann das Add-on nur durch Code-Änderung nutzen. Das widerspricht der im
README beworbenen „Config-driven"-Philosophie und ist faktisch ein
Konfigurations-Bug für jeden, dessen Sensor anders heißt.
*(Gilt analog für die globalen Entitäten in `controller.py:22-27`.)*

---

## 🟠 Fachliche Ungereimtheiten & Risiken

### A1 – Zeit-Guards hebeln die Notabschaltung teilweise aus
**`devices.py:597-633`, `controller.py:282-302`**

`binary_immediate_off` (Notabschaltung bei Netzdefizit) umgeht zwar das
One-Change-Limit (`controller.py:284-285`), **nicht** aber die Guards in
`calculate_candidate`: Mindestlaufzeit und Abschaltverzögerung gelten laut
Kommentar (`devices.py:600-604`) *immer* – auch im Notfall. Ein binäres Gerät,
das sich noch in der Mindestlaufzeit oder Abschaltverzögerung befindet, bleibt
also trotz Netzbezug eingeschaltet.

Das ist eine **bewusste Designentscheidung** (Geräteschutz vor Netzschonung),
sollte aber als bewusster Trade-off prominent dokumentiert sein: Im
ungünstigsten Fall bezieht das System für die Dauer der Abschaltverzögerung
weiter Strom aus dem Netz. Empfehlung: dieses Verhalten in der README im
Abschnitt „Sofortabschaltung" explizit benennen.

### A2 – Pool-Rückrechnung setzt eine bestimmte Sensor-Semantik voraus
**`controller.py:247-252`**

```python
actual_used_w = sum(d.current_w for d in self._devices)
return max(residual_w + actual_used_w, 0.0)
```

Die Pool-Berechnung addiert die aktuell genutzte EMS-Leistung zum Überschuss
zurück. Das ist korrekt **nur**, wenn der Überschuss-Sensor die EMS-Lasten
bereits *abzieht* (Netz-Einspeise-orientiert). Liefert der Sensor bereits den
„echten" freien Überschuss, kommt es zu Doppelzählung und Aufschwingen. Diese
Annahme über die Sensor-Semantik ist nirgends hart geprüft und nur implizit
dokumentiert. Empfehlung: die geforderte Sensor-Semantik im README unmissverständlich
beschreiben (am besten mit Formel) und ggf. eine Plausibilitätswarnung loggen.

### A3 – Greedy-Phasenstart bevorzugt immer die höchste Phasenzahl
**`devices.py:326-334`**

Beim Ladestart wird die **höchste** Phasenanzahl gewählt, deren Minimum der Pool
trägt. Da 3-phasig ein deutlich höheres Leistungsminimum hat
(~4,1 kW vs. ~1,4 kW einphasig), startet die Wallbox erst bei deutlich höherem
Überschuss. Das ist vertretbar und dokumentiert, aber je nach Anwenderwunsch
(„lieber früh einphasig laden") kontraintuitiv. Eine konfigurierbare
Start-Strategie (`greedy` vs. `eager`) wäre eine sinnvolle Erweiterung.

### A4 – Float-Gleichheit als Zustandssignal
**`devices.py:318`** (`is_initial_start = self._anforderung_current_w == 0`)
und **`devices.py:445`** (`is_on_off = (self._new_w == 0) != ...`)

Exakte Float-Gleichheitsvergleiche mit `0` funktionieren hier praktisch, weil
die Werte aus Ganzzahlrundungen (`round`, `math.floor`) stammen. Es ist dennoch
fragil: Sobald irgendwann ein nicht gerundeter Pfad entsteht, kippt die
Erkennung „Gerät aus/ein" lautlos. Robuster wäre ein expliziter Zustand bzw.
`abs(x) < epsilon`.

### A5 – `HARD_LOCKOUT_THRESHOLD_W` als unkommentierte Magic Number
**`controller.py:29`**

Der Schwellwert `-50000.0 W` ist weder konfigurierbar noch begründet. Für
Anlagen mit großen Lasten könnte er zu hoch oder zu niedrig sein. Mindestens ein
erklärender Kommentar, idealerweise Konfigurierbarkeit.

---

## 🟡 Code-Qualität & Wartbarkeit

### Q1 – Keine automatisierten Tests *(größte Wartbarkeitslücke)*
Im gesamten Repo existiert kein einziger Test. Die Regel-Logik
(`_apply_priority_cascade`, `_limit_one_change`, `calculate_ramp`,
`select_phases`, `calculate_candidate`) ist genau die Art zustandsbehafteter,
verzweigter Logik, die ohne Tests bei jeder Änderung zur Regressionsfalle wird.
Die Architektur ist dafür **bereits ideal vorbereitet**: `run_cycle(st)` ist
rein (nimmt einen `StateProxy`, gibt `write_ops` zurück, keine I/O). Damit ließe
sich der Kern ohne HA mocken-frei testen. Empfehlung: `pytest`-Suite für
mindestens die Prioritäts-/Rampen-/Phasen-Logik.

### Q2 – Neue `aiohttp.ClientSession` pro Request
**`ha_client.py:25, 44, 61`**

Jeder `fetch_all_states`, `call_service` und `execute_write_ops` öffnet und
schließt eine eigene `ClientSession`. Das verhindert Connection-Pooling/Keep-Alive
und widerspricht der ausdrücklichen aiohttp-Empfehlung („eine Session pro
Anwendung"). Bei 30-s-Intervall plus mehreren Schreibvorgängen summiert sich der
Overhead. Empfehlung: eine langlebige Session im `HAClient` halten (lazy
erstellen, beim Shutdown schließen).

### Q3 – Ungenutzter Import
**`main.py:10`** (`import os`)

`os` wird in `main.py` nirgends verwendet. Toter Import → entfernen (ein Linter
wie `ruff`/`flake8` würde das automatisch finden – siehe Q8).

### Q4 – Tote Basis-Methode `Device.allocate`
**`devices.py:78-80`**

`Device.allocate()` wird nirgends aufgerufen (der Controller nutzt
`allocate_minimum` / `allocate_surplus` / `consume_from_pool`). Toter Code, der
das Interface unnötig aufbläht → entfernen.

### Q5 – Ungenauer Typ-Hint
**`ha_client.py:41`** (`data: Dict[str, Any] = None`)

Default `None` bei Typ `Dict` ist technisch inkorrekt; korrekt wäre
`Optional[Dict[str, Any]] = None`. Funktioniert nur, weil `data or {}` greift.

### Q6 – Namens-/Konzept-Unschärfe `controllable_relief`
**`controller.py:168`**

Die Variable heißt `controllable_relief`, summiert aber `max_relief_w` über
**alle** Geräte (Binärgeräte liefern via Basisklasse 0.0). Funktional korrekt,
aber irreführend benannt. Entweder Name anpassen oder Kommentar ergänzen.

### Q7 – Gemischte Zeitquellen
**`controller.py:133`** nutzt `datetime.datetime.now().timestamp()`,
**`devices.py:495, 648`** nutzt `time.time()`.

Beide liefern Unix-Epoch und sind damit konsistent – aber die Vermischung ist
eine versteckte Annahme. Empfehlung: eine einheitliche `now`-Quelle (z. B. den
ohnehin durchgereichten `now_ts`) verwenden; das erleichtert auch das Testen
(injizierbare Zeit).

### Q8 – Kein Linting/Formatting/CI-Qualitätsgate
Es gibt nur einen Versions-Bump-Workflow (`.github/workflows/bump-version.yaml`),
aber keine CI für `ruff`/`black`/`mypy`/`pytest`. Ein einfacher Lint-+Test-Job
würde Q3/Q4/Q5 automatisch abfangen und Regressionen verhindern.

### Q9 – Web-UI ist ein 535-Zeilen-Monolith
**`app/templates/index.html`**

HTML, CSS und JS stecken in einer Datei mit String-Template-Rendering von Hand.
Für die aktuelle Größe vertretbar, aber bei weiterem Wachstum schwer wartbar
(kein Build-Step, kein XSS-Escaping der Labels – siehe S3). Mittelfristig
Auslagern von CSS/JS bzw. ein minimales Framework erwägen.

### Q10 – Mischsprachigkeit
Code-Kommentare/Logs mischen Deutsch und Englisch (z. B. `controller.py:96` DE,
`controller.py:110` EN). Das ist kosmetisch, erschwert aber die Konsistenz.
Eine bewusste Sprachkonvention (Code/Kommentare EN, Anwendertexte DE) wäre sauberer.

---

## 🔵 Sicherheit

### S1 – `/api/set` validiert die Ziel-Entität nicht
**`main.py:191-214`**

Der Endpunkt schreibt in **jede** `input_boolean`/`input_number`/`input_select`-
Entität, nicht nur in `ems_*`-Helfer. Über das Ingress-Panel könnte ein
authentifizierter Nutzer damit beliebige Helfer in HA verändern (auch nicht zum
EMS gehörende). Empfehlung: serverseitig auf `*.ems_*`-Präfix beschränken –
analog zum Filter in `_handle_controls` (`main.py:181-185`).

### S2 – Server lauscht auf `0.0.0.0` und Port ist `EXPOSE`d
**`main.py:231`, `Dockerfile:10`**

Im HA-Ingress-Kontext ist der Zugriff normalerweise durch Ingress
authentifiziert. Da der Port aber zusätzlich exponiert wird, sollte die
Annahme „Zugriff nur über Ingress" dokumentiert und das `EXPOSE` ggf. entfernt
werden, damit nicht versehentlich ein ungeschützter Port gemappt wird.

### S3 – Kein Escaping benutzerkontrollierter Strings in der UI
**`index.html:316, 354, 477`** u. a.

Geräte-`label` und Entitätswerte werden per Template-Literal direkt ins DOM
geschrieben (`${d.label}`, `${item.label}`, `${state.state}`). Da die Werte aus
der Add-on-Config bzw. HA-Helfern stammen (lokal, vertrauenswürdig), ist das
Risiko gering, aber ein klassischer DOM-XSS-Vektor. Empfehlung: `textContent`
statt `innerHTML` bzw. eine kleine Escape-Funktion.

### S4 – Abhängigkeitspflege
**`requirements.txt:1`** (`aiohttp==3.9.5`)

`aiohttp 3.9.5` ist nicht die aktuellste Version; in der 3.10/3.11-Linie wurden
mehrere Sicherheits- und Stabilitätsfixes nachgezogen. Pinning ist gut –
empfehlenswert ist aber eine regelmäßige Aktualisierung (z. B. Dependabot/Renovate).

---

## 🟢 Zukunftssicherheit

### Z1 – Dockerfile-Basis `python:3.11-alpine`
**`Dockerfile:1`**

Alpine (musl) führt bei Python-Paketen mit C-Anteil regelmäßig zu Build-Problemen
(fehlende `musllinux`-Wheels → Kompilieren ohne `build-base`). Aktuell trägt nur
`aiohttp`, das passt – sobald eine weitere Abhängigkeit hinzukommt, kann der Build
brechen. `python:3.11-slim` (glibc) ist für Add-ons oft die robustere Wahl.

### Z2 – Versionsstrategie nur Patch-Bump
**`.github/workflows/bump-version.yaml:19-25`**

Die CI erhöht ausschließlich die Patch-Stelle bei jedem Push auf `main`. Damit
ist die Version faktisch ein Build-Zähler ohne semantische Aussage (Minor/Major
werden nie erhöht). Für ein Add-on vertretbar, aber semantische Versionierung
geht verloren. Zudem pusht der Workflow direkt auf `main` – bei aktiviertem
Branch-Schutz würde das scheitern.

### Z3 – Vollständiger State-Pull pro Zyklus
**`ha_client.py:22-39`**

`/api/states` liefert **alle** HA-Entitäten pro Zyklus. In großen Installationen
(tausende Entitäten) wächst die Payload spürbar. Da die REST-API kein Filtern
unterstützt, ist das schwer vermeidbar; mittelfristig wäre der WebSocket-API mit
gezieltem State-Subscribe deutlich effizienter und reaktiver.

### Z4 – Kein sauberes Herunterfahren / kein Healthcheck
**`main.py:137-141, 220-235`**

Die Scheduler-Schleife ist `while True` ohne Cancellation-Handling; der
`AppRunner` wird beim Shutdown nicht aufgeräumt. Ein Add-on-Stopp/Neustart
funktioniert, ist aber nicht graceful. Ein HA-Healthcheck/`SIGTERM`-Handling
würde die Robustheit erhöhen.

### Z5 – Fehlende `.dockerignore`
Build-Kontext enthält u. a. `.git`, README (31 kB), `icon.png`. Eine
`.dockerignore` verkleinert den Kontext und beschleunigt Builds.

---

## 💡 Verbesserungsvorschläge (priorisiert)

| Prio | Maßnahme | Bezug |
|------|----------|-------|
| 1 | **Globale Entitäten (v. a. Überschuss-Sensor) konfigurierbar machen** | F2, F3 |
| 2 | **Pytest-Suite für die Regel-Logik** (run_cycle ist rein → leicht testbar) | Q1 |
| 3 | **`/api/set` auf `ems_*`-Entitäten einschränken** | S1 |
| 4 | **Eine langlebige `aiohttp.ClientSession`** statt pro Request | Q2 |
| 5 | **Veraltete `voltage_entity`-Doku korrigieren** | F1 |
| 6 | **CI-Gate mit `ruff` + `pytest`** ergänzen (fängt Q3/Q4/Q5 automatisch) | Q8 |
| 7 | **Notabschaltungs-Trade-off** (Guards gelten immer) klar dokumentieren | A1 |
| 8 | **Toten Code/Imports entfernen** (`os`, `Device.allocate`) | Q3, Q4 |
| 9 | **UI-Werte escapen** (`textContent`/Escape-Helper) | S3 |
| 10 | **Dependabot/Renovate** + Wechsel auf `python:3.11-slim` erwägen | S4, Z1 |

---

## ✅ Positives / Stärken

- **Saubere Schichtung**: Transport (`ha_client`), Orchestrierung (`controller`),
  Domäne (`devices`), Zustand (`state`) sind klar getrennt.
- **Reine Kern-Funktion**: `EMSController.run_cycle()` ist seiteneffektfrei und
  gibt `write_ops` zurück – exzellente Voraussetzung für Tests.
- **Config-driven Geräte** mit ABC-basierter Erweiterbarkeit – ein neuer
  Gerätetyp braucht nur eine Subklasse + Registry-Eintrag (`controller.py:36-102`).
- **Durchdachte Regel-Features**: Hysterese, Rampenbegrenzung, Zeit-Guards,
  Prioritätskaskade, reluctant Phasenumschaltung mit Hysterese-Sperrzeit.
- **Defensive Eingabebehandlung**: `safe_float`, `parse_ts`, Spannungs-Plausibilitäts-
  prüfung (180–260 V), Sensor-Lockout bei `unavailable/unknown`.
- **Hervorragende Dokumentation**: README, `config.yaml`-Beschreibung und
  `translations/` sind ungewöhnlich ausführlich (bis auf die F1-Inkonsistenz).
- **Durchdachte Web-UI**: Live-herunterzählende Timer aus gecachtem Snapshot,
  damit Countdowns nicht bis zum nächsten Zyklus „einfrieren" (`index.html:240-243`).
- **Bewusste Schreib-Sparsamkeit**: Deadband und „nur bei Änderung schreiben",
  inkl. korrekter Begründung wegen `last_changed`/Rampen-Timing (`devices.py:446-449`).

---

*Erstellt durch automatisierte technische & fachliche Code-Analyse.*
