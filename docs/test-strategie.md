# Teststrategie

## Befehle

```bash
pytest -q                          # alle Tests
pytest -q tests/test_controller.py # gezielt eine Datei
ruff check app tests               # Linting und Formatprüfung
cd web && npm run build            # enthält `tsc --noEmit` — Typfehler brechen den Build
```

Alle drei müssen vor jedem Commit fehlerfrei durchlaufen — siehe [git-workflow.md](git-workflow.md).

## Testarten

Die Tests liegen **flach** in `tests/`, benannt nach dem geprüften Aspekt statt nach Ordnerebenen —
bei dieser Anzahl ist eine Unterordnerstruktur reine Bewegung ohne Orientierungsgewinn.

| Datei | Umfang |
|---|---|
| `test_state.py` | `StateProxy`, `safe_float`, `parse_ts` — reine Unit-Tests |
| `test_controllable_device.py` | `ControllableDevice`: Rampe, Deadband, Ampere-Umrechnung, Phasenwahl |
| `test_binary_device.py` | `BinaryDevice`: Hysterese, Mindestlaufzeit, Mindestauszeit, Abschaltverzögerung |
| `test_controller.py` | Prioritätskaskade, One-Change-Limit, Pool-Berechnung |
| `test_run_cycle.py` | Vollständiger Zyklus gegen einen gefälschten HA-State — die Integrationsebene |
| `test_ep_uebernahme.py` | Übernahme der Energy-Pilot-Vorschläge je Regelmodus, Fallback auf Nutzerwerte |
| `test_allocation_properties.py` | Property-Tests mit Hypothesis über die Pool-Verteilung |

`tests/conftest.py` stellt die gemeinsamen Fixtures bereit (State-Schnappschüsse, Gerätekonfiguration).

## Pflicht-Testfälle

Für jede neue Funktion mindestens:

1. **Normalfall** — erwartete Eingabe, erwartetes Ergebnis
2. **Fehlerfall** — ungültige Eingabe, definierter Fehler statt Absturz
3. **Leerzustand** — leere Geräteliste, `unavailable`-Sensor, fehlender Helfer

Für die Regellogik zusätzlich verpflichtend:

4. **Zeitschutz** — Mindestlaufzeit, Mindestauszeit und Abschaltverzögerung gelten **auch** bei
   Notabschaltung. Wer daran etwas ändert, ändert eine Invariante (siehe
   [architektur.md](architektur.md)).
5. **Hard-Lockout** — ungültiger oder stark negativer Überschuss-Sensor schaltet alles ab.

Ein Bugfix ohne Regressionstest ist nicht abgeschlossen. Der Test muss **vor** dem Fix
nachweislich fehlschlagen.

## Grundregeln

- Tests laufen **ohne** Netzwerkzugriff, ohne echte Zugangsdaten und ohne Home Assistant. Der
  HA-State wird als Dictionary gestellt, der `HAClient` wird nicht angefasst.
- Tests sind reihenfolgeunabhängig und hinterlassen keinen Zustand.
- Keine `sleep`-Aufrufe zur Synchronisierung. Zeitabhängige Logik bekommt den Zeitstempel
  **übergeben** (`now_ts`) — genau dafür ist der Parameter da.
- Ein Test prüft **eine** Aussage. Der Testname beschreibt sie:
  `test_binaeres_geraet_bleibt_an_waehrend_mindestlaufzeit`.

## Property-Tests

`test_allocation_properties.py` prüft mit Hypothesis Zusicherungen, die für **jede** zufällige
Gerätekonstellation gelten müssen — etwa dass die Summe der Zuteilungen den Pool nie übersteigt und
dass kein Gerät über `max_technisch` hinaus zugeteilt bekommt. Neue Regeln der Verteilungslogik
gehören hierher, nicht in ein weiteres Beispiel.

## Coverage

Zielwert: keine feste Quote — jede Regelentscheidung im EMS-Zyklus ist durch mindestens einen Test
abgedeckt. Coverage ist ein Warnsignal, kein Ziel an sich; 100 % ohne Zusicherungen im Test ist
wertlos. Ungetestet bleiben dürfen die HTTP-Verdrahtung in `main.py` und der `HAClient` — beide
haben keine Fachlogik und wären nur gegen einen Mock getestet.

## Frontend

Für die Oberfläche gibt es bewusst keine automatisierten Tests: Die Seiten enthalten keine
Fachlogik, sie stellen `/api/status` dar. Abgesichert wird sie durch `tsc --noEmit` im Build und
durch die Sichtprüfung aus [frontend.md](frontend.md) („Was ein Agent vor dem ersten Commit
prüft").
