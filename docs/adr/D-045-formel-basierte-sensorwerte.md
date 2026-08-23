# D-045: Formel-basierte Sensorwerte für Überschuss und Hausleistungsbilanz

- **Datum:** 22.08.2026
- **Status:** Aktiv
- **Betrifft:** [`app/formula.py`](../../app/formula.py), [`app/ems/state.py`](../../app/ems/state.py),
  [`app/ems/controller.py`](../../app/ems/controller.py), [`app/configuration.py`](../../app/configuration.py),
  [`app/config_service.py`](../../app/config_service.py), [`app/main.py`](../../app/main.py),
  [`config.yaml`](../../config.yaml), `web/src/`

> Diese Entscheidung ergänzt [D-044](D-044-hausleistungsbilanz-ac-speicher.md) um eine zweite,
> intern gepflegte Möglichkeit, mehrere HA-Entitäten zu einem Sensorwert zu kombinieren. D-044s
> externe HA-Vorlage bleibt für reine Entity-Konfigurationen vollständig gültig und wird durch
> diese Entscheidung nicht ersetzt.

## Kontext

Die beiden zentralen Eingangswerte des Reglers — der Überschuss-Sensor (`residual_power_entity`)
und die Hausleistungsbilanz für AC-Speicher (`battery_residual_power_entity`) — sind bisher je genau
eine feste HA-Entity-ID. Wer mehrere Rohsensoren kombinieren muss (das Standardbeispiel dieser
Anlage: eine signierte Bilanz aus Netz- und E3DC-Batterieleistung, siehe D-044), muss das heute
**außerhalb** des Add-ons als eigenen HA-Template-Sensor in YAML pflegen
([`erweiterungen/zusatz_sensor_für_speicher_null_einspeisung/ueberschusssensor_von_ha.yaml`](../../erweiterungen/zusatz_sensor_für_speicher_null_einspeisung/ueberschusssensor_von_ha.yaml)).
Das funktioniert, ist aber weder im Ingress-Panel sichtbar noch dort testbar, und jede Anlage
pflegt ihre eigene, nicht versionierte YAML-Kopie.

Der Wunsch: dieselbe Kombinationsfähigkeit direkt im Add-on, mit einem editierbaren, testbaren
Formular statt einer externen YAML-Datei. Damit stellen sich zwei eigenständige Fragen:

1. **Wie wird nutzerdefinierter Code sicher ausgeführt?** `app/main.py` `_scheduler()`/
   `_run_cycle()` und `app/ems/controller.py` `run_cycle()` laufen synchron, inline, im selben
   einzigen asyncio-Prozess — es gibt keinen Thread- oder Prozess-Pool im gesamten Projekt.
   Hängender oder rechenintensiver Nutzer-Code würde dort auch die Notabschaltung blockieren.
2. **Wie verhält sich das Ergebnis zur bestehenden Einzel-Entität?** Beide Konzepte existieren dann
   nebeneinander für denselben Zielwert — genau die Situation, vor der D-041 warnt („welcher
   Mechanismus gerade griff, war ohne Debug-Log nicht zu beantworten").

## Betrachtete Optionen (Frage 1: Ausführung)

### Option A — Vollständiges Python in einem isolierten Subprozess (Timeout + Hard-Kill)

- Dafür: entspricht dem Wunsch nach „Python-Code" am genauesten — echte Schleifen, eigene
  Funktionen, die volle Sprache.
- Dagegen: unverhältnismäßiger Aufwand für den tatsächlichen Bedarf (wenige Sensoren zu einer Zahl
  verrechnen). Neue Prozess-Architektur, eine Timeout-Politik muss neu festgelegt werden, ein
  Prozess-Spawn pro Formel und Zyklus (Intervall ab `1 s` möglich) ist die erste
  Subprozess-Komponente im gesamten Projekt. `SUPERVISOR_TOKEN` und Umgebungsvariablen müssten aktiv
  vom Kindprozess ferngehalten werden.

### Option B — Reine Ausdruckssprache (z. B. eine `simpleeval`-artige Bibliothek)

- Dafür: sehr sicher und sehr einfach, kein Interpreter selbst zu bauen.
- Dagegen: nur ein einzelner Ausdruck, keine Zwischenvariablen oder mehrschrittige Zuweisung —
  weicht vom Wunsch „Code schreiben, am Ende `ueberschuss` zuweisen" ab. Neue Laufzeit-Abhängigkeit
  für ein Projekt, das mit genau einer auskommt (`aiohttp`).

### Option C — `eval`/`exec` auf kompiliertem Python mit AST-Vorfilter

- Dafür: „echtes" Python, volle Ausdrucksmächtigkeit innerhalb der Whitelist, aus der Stdlib.
- Dagegen: zwei bekannte Lücken machen „AST-Whitelist reicht" allein unzureichend: (1) CPython fügt
  `__builtins__` automatisch in den `globals`-Dict ein, wenn keiner gesetzt ist — leicht zu
  übersehen; (2) wiederholte Zuweisung/Multiplikation von Python-`int` (beliebige Genauigkeit) kann
  ganz ohne Schleife auf Zahlen mit Milliarden Stellen anwachsen. Beide Lücken sind schließbar
  (explizit leere `__builtins__`, jeden Wert zu `float` erzwingen), aber `exec()` bleibt ein Aufruf
  in echte CPython-Bytecode-Ausführung mit entsprechender Angriffsfläche.

### Option D — Eigener, baumwandelnder Interpreter über eine AST-Whitelist (gewählt)

- Dafür: kein `eval`/`exec` auf kompiliertem Python — die Auswertung geht nie durch reale
  CPython-Bytecode-Ausführung, sondern durch eine selbst geschriebene, rekursive Funktion, die jeden
  Knoten einzeln auswertet und dabei jede Zahl durchgängig als `float` hält. Damit entfallen beide
  Lücken aus Option C strukturell, nicht nur durch zusätzliche Härtung. Reine Stdlib (`ast`, `math`),
  keine neue Abhängigkeit. Ohne Schleifen, Funktionsdefinitionen und Imports ist die Ausführung
  strukturell auf die Anzahl der Ausdrucksbausteine im Quelltext beschränkt — kein Timeout nötig.
- Dagegen: mehr Code als eine Bibliothek einzubinden; die Sprache ist eine bewusst kleine
  Teilmenge (keine Schleifen, keine eigenen Funktionen) und deckt nicht jeden denkbaren Anwendungsfall.

## Betrachtete Optionen (Frage 2: Verhältnis zur Einzel-Entität)

### Option A — Formel ersetzt das Feld vollständig, keine Einzel-Entität mehr

- Dagegen sofort verworfen: bräche jede Bestandsanlage, die die Einzel-Entität bereits pflegt.

### Option B — Formel und Einzel-Entität nebeneinander, ohne festgelegte Reihenfolge

- Dagegen: exakt die D-041-Falle — zwei Mechanismen für denselben Wert ohne klare Priorität.

### Option C — Formel hat Vorrang, wirksame Quelle ist immer sichtbar (gewählt)

- Dafür: additiv (leere Formel-Felder sind der Default, Verhalten jeder Bestandsanlage bleibt
  bit-identisch), klare, code-seitig erzwungene Reihenfolge, und die D-041-Lehre wird konkret
  umgesetzt statt nur zitiert: `residual_source`/`battery_residual_source` stehen im Status und
  werden im Sensoren-Formular sowie auf der Status-Seite angezeigt.

## Entscheidung

**Option D** für die Ausführung, **Option C** für das Verhältnis zur Einzel-Entität.

Ein neues, abhängigkeitsfreies Modul `app/formula.py` prüft Quelltext gegen eine feste
AST-Whitelist (Zuweisungen, Arithmetik, Vergleiche, boolesche Verknüpfungen, `if`/`else`, eine kleine
Funktions-Whitelist `abs`/`min`/`max`/`round`) und wertet ihn danach über einen eigenen,
rekursiven Auswerter aus — nie über `compile()`/`exec()`. Jede Zahl bleibt durchgängig `float`.

Zwei neue Konfigurationsfelder je Zielwert (`residual_formula_variables`/`residual_formula_code`,
`battery_residual_formula_variables`/`battery_residual_formula_code`) sind vollständig optional und
standardmäßig leer. `EMSController.run_cycle()` wertet eine konfigurierte Formel **vor** dem
bisherigen Entitäts-Pfad aus; liefert sie einen gültigen, endlichen Wert, ersetzt er die Entität
vollständig, sonst greift unverändert der bisherige Pfad. Welche Quelle gerade wirkt, steht als
`residual_source`/`battery_residual_source` in `/api/status`.

Ein neuer Endpunkt `POST /api/config/sensors/test` führt einen Formel-Entwurf live gegen den
aktuellen HA-Schnappschuss aus, ohne zu speichern — der „Testen"-Knopf im neuen Sidebar-Bereich
„Sensoren" (Tabs „Überschuss", „Hausbilanz").

## Folgen

- **Positiv:** Dieselbe Kombinationsfähigkeit wie die bisherige externe HA-Vorlage, jetzt im
  Ingress-Panel editier- und vor dem Speichern testbar. Additiv — keine Migration nötig, jede
  Bestandsanlage verhält sich unverändert. Die D-041-Lehre ist strukturell umgesetzt: welche Quelle
  wirkt, ist nie nur aus dem Log erschließbar.
- **Negativ:** Eine neue, im Projekt bisher nicht vorhandene Angriffs- und Fehlerfläche
  (nutzerdefinierter Code, wenn auch strukturell stark eingeschränkt) — siehe
  [sicherheit-datenschutz.md](../sicherheit-datenschutz.md#nutzerdefinierte-sensor-formeln-d-045).
  Die Formel-Sprache ist bewusst klein: keine Schleifen, keine eigenen Funktionen. Ein Anwendungsfall,
  der das braucht, lässt sich mit dieser Sprache nicht ausdrücken (siehe Rücknahmebedingung).
- **Aufwand:** Neuer Interpreter mit eigener Testsuite (Beispieltests je erlaubtem/verbotenem
  Konstrukt, zwei Hypothesis-Property-Tests für Robustheit gegen beliebigen Text), Validierung,
  Statusvertrag, neuer Endpunkt, neue Seiten samt neuer Zeilen-Listen-Komponente, Dokumentation.

## Rücknahmebedingung

Die Entscheidung wird überprüft, wenn mindestens eines dieser Signale auftritt:

1. **Ein Sandbox-Escape wird gefunden** — ein Formel-Code erreicht nachweislich etwas außerhalb der
   reinen Zahlenberechnung (Datei-, Netzwerk- oder Prozesszugriff, unbegrenzter Ressourcenverbrauch).
   Dann muss der Interpreter geschlossen oder durch eine stärker isolierte Ausführung (Option A)
   ersetzt werden.
2. **Eine reale Formel braucht ein Konstrukt, das die Sprache strukturell nicht ausdrücken kann**
   (eine echte Schleife, eine eigene Hilfsfunktion) und Umformulieren ohne Schleife ist nicht
   praktikabel. Dann muss die Whitelist gezielt erweitert oder eine leistungsfähigere Ausführung
   gewählt werden — nicht die Whitelist pauschal aufweichen.
3. **Die Vorrangregel wird in der Praxis verwechselt** — Nutzer melden wiederholt, nicht zu wissen,
   ob gerade die Formel oder die Entität wirkt, obwohl der Status es anzeigt. Dann reicht die
   Statusanzeige allein nicht und die Oberfläche braucht eine deutlichere Warnung.
