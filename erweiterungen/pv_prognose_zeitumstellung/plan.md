# Plan: PV-Prognosekurve über die Zeitumstellung hinweg korrekt prüfen

Stand: 19.10.2026 · Status: **umgesetzt am 19.10.2026** (Frühjahr Fall b mit umgesetzt, siehe 2.3 und 4) · Variante: **A** (mit User festgelegt am
19.10.2026) · Bezug: D-065 (Preis- und Prognosemodul)

## 1. Problem

### 1.1 Befund in Home Assistant (per MCP gelesen am 19.10.2026)

- `sensor.ems_dyn_pv_prognose` meldet die Tageswerte gültig (heute 34,737 kWh, morgen
  34,325 kWh, Rest heute 34,23 kWh), aber `kurve_gueltig: false` und `kurve_bis: null`.
- Konfiguriert ist `pv_curve_entity: sensor.helios_hausdach_power_now`,
  `pv_curve_attribute: forecast` (Integration `helios_forecast`).
- Das Attribut `forecast` enthält 672 Einträge im 15-min-Raster vom 19.10.2026 00:00 bis
  25.10.2026 23:45. Alle Leistungs-, p10- und p90-Werte sind gültig.
- Einzige Unregelmäßigkeit ist die Nacht der Zeitumstellung:

  ```text
  2026-10-25T02:30:00+02:00
  2026-10-25T02:45:00+02:00
  2026-10-25T03:00:00+01:00   ← Wanduhr +15 min, real +75 min
  ```

- Nachprüfung per MCP am 19.10.2026: Der Sprung zu `03:00+01:00` (real 75 min) ist der einzige
  Abstand ≠ 15 min. p10/p90 sind nur in der Zukunft gesetzt; 142 vergangene Einträge haben `null`
  (zulässig, ohne Folgen).
- Lokal nachgestellt mit dem Live-Zustand liefert `parse_pv_curve`:
  `Kurve ist lückenhaft, unsortiert oder hat gemischte Abstände`.

### 1.2 Ursache

Helios gibt **je Kalendertag 96 Viertelstunden nach Wanduhrzeit** aus, jeweils mit dem korrekten
Offset. Bei der Rückstellung im Oktober kommt die Wanduhrzeit 02:00–02:59 zweimal vor
(erst `+02:00`, dann `+01:00`). Helios liefert sie nur einmal, nämlich mit `+02:00`. Es fehlen also
die vier Slots `02:00`, `02:15`, `02:30`, `02:45` mit `+01:00`. Der Umstellungstag hat real
100 Viertelstunden, Helios liefert 96.

Aus Sicht von Helios ist die Prognose vollständig: Jede Wanduhr-Viertelstunde ist genau einmal
vorhanden. Die fehlende Stunde liegt nachts, die Werte der Wanduhr-Zwillinge sind 0 W.

`app/tariff/pv_source.py` (`parse_pv_curve`) verlangt dagegen **einen einzigen realen Abstand**
über die ganze Kurve. Eine einzige abweichende Stelle macht die **komplette** Kurve ungültig,
obwohl die Lücke erst in sechs Tagen liegt.

### 1.3 Auswirkungen

- Ingress-Übersicht „Dynamischer Strompreis“: Prognosekurve rot, keine Tagessummen der Kurve.
- `analysis.simulate()` (Speicherreichweite, Kennzahlen) läuft ohne PV-Kurve.
- `insight_sync._write_pv_run` schreibt keinen PV-Prognoselauf nach Data Insight.
- Der Grund ist in HA nicht sichtbar: der Publisher schreibt nur `kurve_gueltig`, nicht den Grund.
- Tritt bei **jeder** Zeitumstellung auf, jeweils ab dem Tag, an dem die Umstellung in den
  Helios-Horizont (7 Tage) rückt, bis sie vorbei ist.

## 2. Lösung (Variante A)

Grundsatz: Die strenge Prüfung bleibt. Toleriert wird **genau ein** eindeutig erkennbares Muster –
die Zeitumstellung in `Europe/Berlin` – und die dabei fehlenden Slots werden **ausdrücklich** aus
den Helios-Werten derselben Wanduhrzeit gebildet. Nach dem Parser sieht jede gültige Kurve
wieder lückenlos aus; Simulation, Data Insight und Tagessummen bleiben unverändert.

### 2.1 Prüfregel für zwei aufeinanderfolgende Einträge

Zwei Einträge `a → b` gelten als lückenlos, wenn **eine** der beiden Bedingungen gilt:

1. **Normalfall:** realer Abstand `b.start − a.start` = Raster.
2. **Zeitumstellung:** alle folgenden Punkte zugleich:
   - Abstand auf der **Berliner Wanduhr** (naive Ortszeit) = Raster,
   - zwischen `a` und `b` liegt laut `zoneinfo` `Europe/Berlin` ein Offset-Wechsel,
   - realer Abstand = Raster + (Offset vorher − Offset nachher), also im Oktober Raster + 60 min,
   - die Offsets von `a` und `b` entsprechen dem, den Berlin zu diesem Zeitpunkt tatsächlich hat
     (`utcoffset()` von `start.astimezone(BERLIN)` = mitgelieferter Offset).

Alles andere bleibt ungültig: echte Lücken, Überschneidungen, unsortierte Einträge, gemischte
Raster, eine scheinbare Umstellung an einem falschen Tag, falsche Offsets.

Das Raster wird aus den **Normalfall-Abständen** bestimmt (müssen alle gleich sein und 15 oder
60 min betragen), nicht aus der Menge aller Abstände.

### 2.2 Auffüllen der doppelten Stunde

Für jede als Zeitumstellung erkannte Stelle im Herbst:

- Anzahl fehlender Slots = (Offset vorher − Offset nachher) / Raster
  (15-min-Raster: 4 Slots, 60-min-Raster: 1 Slot).
- Die eingefügten Slots liegen real lückenlos zwischen `a` und `b`
  (im Beispiel `02:00+01:00` bis `02:45+01:00`).
- Werte (`watts`, `p10`, `p90`) je eingefügtem Slot = Werte des Eintrags mit **derselben
  Wanduhrzeit** aus dem ersten Durchlauf (`02:00+02:00` … `02:45+02:00`). Das ist der Wert, den
  Helios für genau diese Uhrzeit liefert – kein erfundener Ersatzwert.
- `PvSlot` erhält ein Kennzeichen `dst_filled: bool` (Default `False`), damit die
  Herkunft nachvollziehbar bleibt.
- **Plausibilitätsschranke:** Aufgefüllt wird nur, wenn die Werte der Wanduhr-Zwillinge 0 W
  betragen (siehe offene Frage F2). Andernfalls wird die Kurve mit Grund ungültig, z. B.
  „Zeitumstellung 25.10.2026: Helios-Werte der doppelten Stunde sind nicht 0 W“.
- Fehlt ein Wanduhr-Zwilling in der Kurve (Umstellung direkt am Kurvenanfang), wird die Kurve
  mit Grund ungültig.

### 2.3 Frühjahr (Vorstellung der Uhr)

Geklärt über den Quelltext von Helios 2026.9.6 (`forecast.py`, `build_forecast_series`): Helios
beginnt um Berliner Mitternacht und zählt `t += step` auf der Ortszeit mit Zone, also nach Wanduhr.
Lokal nachgestellt ergibt das im Herbst genau die Ausgabe aus 1.1. Im Frühjahr gilt deshalb
**Fall b**: Helios liefert die nicht existierenden Zeiten `02:00`–`02:45` mit `+01:00`. Das sind real
dieselben Zeitpunkte wie `03:00`–`03:45+02:00` (Abstand −45 min, 96 statt 92 Einträge).

Regel (mit dem User festgelegt am 19.10.2026): Ein Eintrag wird verworfen, wenn sein Offset nicht
zu Berlin passt, seine Wanduhrzeit in der übersprungenen Stunde liegt und sein realer Zeitpunkt in
der Kurve noch einmal vorkommt – und nur, wenn er 0 W ist. Sonst ist die Kurve ungültig mit Grund
„Zeitumstellung TT.MM.JJJJ: Helios-Werte der übersprungenen Stunde sind nicht 0 W“. Fall a (real
lückenlos) bleibt ohne Sonderbehandlung gültig.

## 3. Umsetzung

### Schritt 0 – Klärung vor dem Code

- F1 klären: Verhalten von `helios_forecast` bei der Vorstellung im März prüfen (Quelltext unter
  `custom_components/helios_forecast` in HA oder Test mit vorgetäuschtem Datum).
- Offene Fragen F2–F4 (Abschnitt 4) mit dem User entscheiden.

### Schritt 1 – `app/tariff/pv_source.py`

- `PvSlot` um `dst_filled: bool = False` erweitern.
- Neue Hilfsfunktion `_dst_gap(previous, following, raster) -> Optional[int]`:
  liefert die Zahl fehlender Slots, wenn die Stelle eine gültige Herbst-Umstellung ist
  (Regel 2.1 Punkt 2), sonst `None`. Nutzt `BERLIN` aus `tariff.price_source`.
- `parse_pv_curve` umbauen:
  1. Einträge wie bisher einzeln prüfen.
  2. Raster aus den Abständen bestimmen, die dem Normalfall entsprechen; Abstand ≤ 0 → ungültig.
  3. Jede Stelle prüfen: Normalfall → weiter; `_dst_gap` liefert Anzahl → Slots nach 2.2
     einfügen; sonst ungültig mit Ortsangabe im Grund, z. B.
     „Lücke zwischen 14:00 und 15:00 am 20.10.2026“ (Format über `format_berlin`, Regel 9).
  4. Prüfung „vollständig in der Vergangenheit“ bleibt.
- Modul-Docstring ergänzen: Regel zur Zeitumstellung, Herkunft der aufgefüllten Slots.
- `energy_per_day_kwh` bleibt unverändert (aufgefüllte Slots zählen mit; bei 0 W ohne Wirkung).

### Schritt 2 – nachgelagerte Module prüfen (voraussichtlich ohne Änderung)

- `app/tariff/analysis.py` `_pv_watts` / `simulate`: arbeiten über `slot.start` + Raster;
  mit lückenloser Kurve kein Abbruch mehr am 25.10. um 02:45. Nur per Test absichern.
- `app/tariff/insight_sync.py` `_write_pv_run`: schreibt je Slot; die vier aufgefüllten Slots
  landen mit in Data Insight (siehe offene Frage F3). Signatur-Vergleich bleibt gültig.
- `app/tariff/service.py`: Ansicht unverändert; `tage` enthält den 25.10. mit 100 Slots.

### Schritt 3 – Grund in HA sichtbar machen

- `app/tariff_publisher.py`: Attribut `kurve_grund` (aus `pv.kurve.grund`) an
  `sensor.ems_dyn_pv_prognose` ergänzen.
- Prüfen, ob `docs/api-referenz.md` bzw. `docs/datenmodell.md` die Attribute des Sensors
  auflisten, und dort nachziehen. Data-Insight-Vertrag (`contract/contract_hems_data_insight/`)
  prüfen, ob die Attribute dieses Sensors Teil des Vertrags sind; falls ja, Regel 12 (beide
  Kopien) beachten.

### Schritt 4 – Tests (`tests/test_tariff.py`, ggf. `tests/test_tariff_p5.py`)

Pflichtfälle:

1. Herbst-Umstellung im Helios-Format (96 Einträge am 25.10.2026, 15-min-Raster, Nachtwerte
   0 W) → gültig, 100 Slots am 25.10.2026, vier Slots mit `dst_filled=True`, Werte = Wanduhr-
   Zwillinge, `until` = 26.10.2026 00:00.
2. Dasselbe im 60-min-Raster → gültig, 25 Slots am Umstellungstag.
3. 75-min-Lücke an einem normalen Tag → ungültig, Grund nennt die Stelle.
4. Wanduhr-lückenlos mit Offset-Wechsel an einem Tag ohne Umstellung (z. B. 20.10.2026
   `02:45+02:00 → 03:00+01:00`, real 75 min) → ungültig.
5. Doppelte Stunde mit Werten > 0 W → ungültig mit eigenem Grund.
6. Umstellung am Kurvenanfang ohne Wanduhr-Zwillinge → ungültig.
7. Frühjahrs-Umstellung im Fall a (`01:45+01:00 → 03:00+02:00`) → gültig, 92 Slots.
8. `simulate()` mit Kurve über die Herbst-Umstellung → Horizont endet nicht am 25.10. 02:45.
9. Publisher: `kurve_grund` gesetzt bei ungültiger Kurve, `None` bei gültiger.
10. Bestehende Fälle aus `test_pv_curve_invalid_cases` bleiben grün (ggf. Grundtexte anpassen).

### Schritt 5 – Doku und Changelog (selbes Arbeitspaket, Regeln 4 und 5)

- `CHANGELOG.md`: Eintrag „PV-Prognosekurve bleibt über die Zeitumstellung gültig“ und
  „Grund der ungültigen Kurve als Attribut `kurve_grund`“.
- `docs/adr/D-065-preis-und-prognosemodul.md`: Regel zur Zeitumstellung bei der PV-Kurve
  (Wanduhr-Raster von Helios, Auffüllen aus Wanduhr-Zwillingen, 0-W-Schranke).
- `docs/design-entscheidungen.md`: Zeile D-065 ergänzen oder neue D-Nummer, falls der User das
  als eigene Grundsatzentscheidung sieht (offene Frage F4).
- `docs/bekannte-luecken.md`: Fehler bis zur Umsetzung eintragen, mit Umsetzung austragen;
  Frühjahrs-Fall b dort vermerken, falls F1 ihn bestätigt.
- `docs/test-strategie.md`: Pflicht-Testfälle ergänzen, falls dort je Modul gelistet.

### Schritt 6 – Abschluss

- `pytest -q` und `ruff check app tests` fehlerfrei.
- Kein Frontend-Build nötig (keine Änderung an `web/`).
- Commit und Push auf `claude/main`.
- Nach dem Update in HA prüfen: `sensor.ems_dyn_pv_prognose` → `kurve_gueltig: true`,
  `kurve_bis` = 26.10.2026 00:00 (bei Kurvenende 25.10.2026 23:45).

## 4. Entscheidungen (19.10.2026, vorher offene Fragen)

- **F1 – Frühjahr:** Fall b laut Quelltext von Helios; mit umgesetzt (2.3).
- **F2 – 0-W-Schranke:** ja, im Herbst wie im Frühjahr.
- **F3 – Data Insight:** aufgefüllte Slots gehen wie normale Slots in den PV-Lauf.
- **F4 – Entscheidungslog:** Ergänzung von D-065 (ADR Punkt 3), keine eigene D-Nummer.
