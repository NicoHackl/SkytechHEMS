# D-061: HEMS-interne Ersatzwerte für HA-Helfer

- **Datum:** 06.10.2026
- **Status:** Aktiv
- **Betrifft:** [`app/ems/state.py`](../../app/ems/state.py),
  [`app/internal_values.py`](../../app/internal_values.py),
  [`app/ems/controller.py`](../../app/ems/controller.py), [`app/main.py`](../../app/main.py),
  [`web/src/pages/Steuerung.tsx`](../../web/src/pages/Steuerung.tsx),
  [`web/src/pages/SteuerungInfo.tsx`](../../web/src/pages/SteuerungInfo.tsx),
  [device_classes/global.md](../device_classes/global.md), [datenmodell.md](../datenmodell.md),
  [api-referenz.md](../api-referenz.md)

## Kontext

Laufzeitwerte liest das HEMS aus HA-Helfern nach der Namenskonvention
`<domain>.ems_<prefix>_<suffix>`. Fehlt ein Helfer, griff bisher das Add-on-Feld und sonst ein
interner Default. Im Steuerung-Tab stand dann nur „Helfer nicht gefunden“: der Wert war ohne
Anlegen eines Helfers in Home Assistant oder eine Änderung der Add-on-Konfiguration samt Neustart
nicht einstellbar.

Gewünscht ist, jeden solchen Wert direkt in der HEMS-Oberfläche einzugeben. Der HA-Helfer soll
Vorrang behalten; ein neuer Tab soll zeigen, welche Werte wirklich aus HA kommen und welche nur im
HEMS existieren.

## Betrachtete Optionen

### Speicherort

- **Datei unter `/data`** — sofort wirksam, übersteht einen Neustart. Zweite eigene Persistenz
  neben dem Merker der Notabschaltung (D-059). **Gewählt.**
- **Add-on-Optionen über die Supervisor-API** — keine neue Persistenz, aber jede Änderung braucht
  einen Add-on-Neustart. Verworfen: eine Steuerung, die erst nach einem Neustart wirkt, ist keine.
- **Nur im Speicher** — geht beim Neustart verloren. Verworfen.

### Verhältnis zu den Add-on-Fallbackfeldern

Der interne Wert steht **vor** dem Add-on-Feld; die Add-on-Felder bleiben als Grundwert erhalten.
Kein Feld entfällt, keine Konfiguration muss migriert werden.

### Abgleich mit einem vorhandenen Helfer

- **Unabhängig** — der interne Wert wird nur bearbeitet, wenn der Helfer fehlt, ausgefallen oder
  ungültig ist. **Gewählt.**
- **Spiegeln** des letzten gültigen Helferwerts — verworfen: eine ausgefallene Freigabe hieße dann
  „weiterlaufen mit dem letzten Wert“ statt „aus“. Das kehrt das bisherige Sicherheitsverhalten um.

## Entscheidung

Reihenfolge der Auflösung für jeden gelesenen Helfer:

```text
gültiger HA-Helfer → HEMS-interner Wert → Add-on-Feld → interner Default
```

- Neuer Quell-Token `hems` („HEMS-intern“) in `entity_diagnostics`. `internal` bleibt der
  Sicherheitsdefault ohne Eingabe — additiv, kein Rename (D-034). Die Ursache (`missing`,
  `unavailable`, `invalid`) bleibt erhalten.
- Gespeichert in `/data/interne_werte.json` als `{"values": {<entity_id>: <wert>}}`, atomar
  geschrieben wie der Merker der Notabschaltung. Eine unlesbare Datei gilt als leer, der Fehler
  steht im Log und in der API; Schreiben ist dann gesperrt, damit nichts überschrieben wird.
  Anders als bei D-059 gibt es kein „im Zweifel aktiv“: ohne internen Wert greift die bisherige
  Kette.
- **Nie intern einstellbar:** `input_boolean.ems_pv_regelung_aktiv` sowie je Gerät `freigabe`,
  `technische_freigabe`, `force` und `force_leistung_w`. Ein im HEMS gespeicherter Wert darf ein
  Gerät nie freigeben oder erzwingen. Durchgesetzt an drei Stellen: im Steuerschema
  (`internal_editable: false`), beim Speichern und im `StateProxy` selbst, damit auch eine von Hand
  bearbeitete Datei nichts freigibt.
- **Umfang:** alle übrigen Lese-Helfer im Steuerung-Tab, global und je Gerät. Nicht im Umfang:
  Ladestufen (D-056), `netzladen_aktiv`, `netzlade_leistung_w` und alle Ausgabe-Helfer — für die
  gibt es weiterhin keinen Ersatz (ein Sollwert lässt sich nicht erfinden).
- Die globalen Helfer laufen jetzt ebenfalls über den Resolve-Vertrag und erscheinen als
  `global_entity_diagnostics` im Status. Bei gültigem HA-State bleibt jedes Ergebnis wie bisher;
  der globale Regelmodus wird weiter roh gelesen, damit ein unbekannter Modus sichtbar bleibt.
- Ohne HA-Helfer fehlen dessen Attribute `min`/`max`/`options`; die Eingabegrenzen stehen deshalb
  im Steuerschema: Zahlen ≥ 0, Prozent bis 100, Prioritäten ganzzahlig, Auswahllisten aus den
  Code-Optionen.
- Neuer Tab „Steuerung Info“ zeigt je Wert Helferzustand, wirksame Quelle, wirksamen Wert und
  wohin die Steuerung schreibt; dort lassen sich auch verwaiste interne Werte löschen.

## Konsequenzen

- `AGENTS.md` nennt zwei Persistenz-Ausnahmen statt einer.
- Energy Pilot und Power Flow Card lesen HA-Entitäten; ein nur intern vorhandener Wert ist für sie
  unsichtbar. Im Gerätemodus `auto` steht ein gültiger EP-Vorschlag weiterhin vor der Helferkette.
- Ein interner Wert wirkt nur, solange der Helfer fehlt oder ausfällt. Wird der Helfer angelegt,
  gilt sofort wieder dessen Wert; der interne bleibt als Ersatz für einen späteren Ausfall stehen.
