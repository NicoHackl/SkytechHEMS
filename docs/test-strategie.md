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
| `test_state.py` | `StateProxy`, Resolve-Vertrag (`missing`/`unavailable`/`invalid`/`valid`, Quelle), `safe_float`, `parse_ts` |
| `test_configuration.py` | Normalisierung, Validierung mit Feldpfaden, Modus-Listen, Eindeutigkeit, Revisions-Hash, Diff für die sichere Deaktivierung |
| `test_controllable_device.py` | `ControllableDevice`: Rampe, Deadband, Ampere-Umrechnung, Phasenwahl |
| `test_binary_device.py` | `BinaryDevice`: Hysterese, Mindestlaufzeit, Mindestauszeit, Abschaltverzögerung |
| `test_controller.py` | Prioritätskaskade, One-Change-Limit, Pool-Berechnung |
| `test_run_cycle.py` | Vollständiger Zyklus gegen einen gefälschten HA-State — die Integrationsebene |
| `test_ep_uebernahme.py` | Übernahme der Energy-Pilot-Vorschläge je Regelmodus, Fallback auf Nutzerwerte |
| `test_battery_device.py` | `BatteryDevice`: Pool-Semantik, SoC-Grenzen, getrennte `available_*`-Limits, Richtungsauflösung, Rampe, signierter Schreibvertrag |
| `test_allocation_properties.py` | Property-Tests mit Hypothesis über die Pool-Verteilung und die Speicher-Invarianten P1–P7 |

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

Für Speicher zusätzlich verpflichtend:

6. **Die Entladung erhöht den Pool nicht.** Der wichtigste Test der Speicher-Erweiterung —
   ohne ihn steht die Aufschaukelung wieder offen.
7. **Das Hausdefizit schließt HEMS-Lasten aus**, auch fremdgesteuerte — **nicht** aber eine
   Zwangslast (D-053), die bewusst als Hausverbrauch gilt. Sonst deckt der Speicher den von Hand
   eingeschalteten Heizstab.
8. **Ohne konfigurierten Speicher bleibt das Verhalten unverändert.**
   `test_pool_ohne_speicher_unveraendert` und die Property P7 sind der Beweis, dass die
   Erweiterung wirklich additiv ist.
9. **Der sichere Zustand wird aktiv geschrieben**, nicht ausgelassen.
10. **Beide `available_*_w`-Limits begrenzen getrennt.** Ein konfigurierter Wert `0` sperrt nur
    die jeweilige Richtung bewusst; negative, fehlende oder nicht endliche Werte sind ungültig.
11. **Nach der Rampe nie über dem konfigurierten Speicherlimit.**
12. **Separate Hausleistungsbilanz:** Die drei E3DC/AC-Speicher-Fälle (`−700 W`, `0 W`,
    `−1400 W`) ergeben jeweils das erwartete Entladeziel. Ein ausgefallener Bilanzsensor schreibt
    den Speicher aktiv auf `0 W` und `standby`, ohne den Verbraucher-Pool zu sperren; der globale
    Entlade-Abschlag wirkt weiterhin genau einmal.

Für jeden Fallback zusätzlich verpflichtend:

13. **Die volle Matrix je Feld:** gültiger HA-Wert, gültiger HA-Nullwert, fehlende Entität,
    `unavailable`, `unknown` und nicht numerischer Wert. Wert und Diagnose werden getrennt
    geprüft — `missing` und `unavailable` liefern denselben Wert, aber verschiedene Ursachen.

Für den Zwang (D-053) zusätzlich verpflichtend:

14. **Zwang wirkt bei jeder Sperre außer der technischen Freigabe** — globales Aus, Regelmodus
    `aus`, Hard-Lockout, Gerätemodus `aus`, fehlende Bedienfreigabe — und nie bei
    `runtime_active: false`. Er ignoriert Notabschaltung, Mindestauszeit, Rampe, Totband,
    Kaskade und One-Change; reserviert nichts und rechnet nichts in den Pool zurück; die
    Zwangslast wird vom Speicher gedeckt. Das Zwang-Ende schaltet im selben Zyklus sofort ohne
    Mindestlaufzeit, Abschaltverzögerung, Rampe und Totband; die Mindestauszeit ist für den
    ersten regulären Neustart ausgesetzt; ab dem Folgezyklus gilt der Zeitschutz wieder. Für
    `force` und `force_leistung_w` gilt die volle Matrix aus Punkt 13, für Ampere-Geräte
    zusätzlich Phasenwahl und Umschaltsperre unter Zwang.

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

Invarianten auf **Zuteilungs**- und **Sollwertebene** auseinanderhalten: `_alloc_w` und
`_entlade_ziel_w` dürfen Pool und Hausdefizit nie überschreiten. Der geschriebene Sollwert darf
das vorübergehend sehr wohl — die Schrittbegrenzung dämpft eine Zielabsenkung absichtlich, sonst
wird aus Sensor-Versatz ein Grenzzyklus. Auf Sollwertebene gilt deshalb nur die Monotonie-Form:
nie über Ziel **und** bisherigen Wert hinaus.

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
