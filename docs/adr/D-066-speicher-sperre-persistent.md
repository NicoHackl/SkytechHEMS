# D-066: Die Sperre der Speicher am SoC-Maximum übersteht einen Neustart

- **Datum:** 13.10.2026
- **Status:** Aktiv
- **Betrifft:** [`app/battery_latch.py`](../../app/battery_latch.py) (neu),
  [`app/ems/devices.py`](../../app/ems/devices.py) (`BatteryDevice`),
  [`app/ems/controller.py`](../../app/ems/controller.py), [`app/main.py`](../../app/main.py),
  Doku zu `class: battery` und zur Persistenz

## Kontext

Ein Speicher, der `soc_max` erreicht, wird für das Laden gesperrt. Freigegeben wird erst wieder
bei `soc_max − soc_max_hysteresis_percent` („Wiedereinstieg unter SoC-Maximum“). Ohne diese
Hysterese würde der Speicher bei 100 % im Takt zwischen Laden und Standby wechseln.

Die Sperre (`BatteryDevice._soc_max_latch`) lag nur im Speicher des Add-ons und begann nach jedem
Start mit „nicht gesperrt“. Ein Neustart von Add-on oder Home Assistant im Hysterese-Band gab das
Laden deshalb wieder frei. Beispiel: `soc_max` 100 %, Wiedereinstieg 3 %, der Speicher fällt nach
dem Vollladen auf 99 %, dann folgt ein Neustart. 99 % liegt zwischen 97 und 100, die Sperre wird
nicht neu gesetzt, und der Speicher lädt bei Überschuss wieder auf 100 %.

## Betrachtete Optionen

- **Sperre unter `/data` speichern**, dritte eigene Persistenz neben D-059 und D-061. Verhält
  sich nach einem Neustart genau so wie ohne Neustart. **Gewählt** (Entscheidung des Users).
- **Sicherer Start ohne Persistenz:** Liegt der erste gültige SoC im Band, wird die Sperre
  gesetzt. Verworfen: Ein Speicher, der vor dem Neustart gerade von 97 auf 99 % geladen hat, würde
  stoppen und erst unter 97 % wieder laden. Das ist falsch in die andere Richtung.
- **HA-Helfer als Merker:** Verworfen. Er hängt an Nutzerkonfiguration und wäre ein weiteres
  Pflichtfeld für einen rein internen Zustand.

## Entscheidung

- Datei `/data/speicher_sperre.json`, Inhalt `{"latches": {"<geräte-id>": true|false}}`, atomar
  über `json_file.write_json_atomic`.
- Sie wird beim Start gelesen, und die Sperren werden vor dem ersten Zyklus übernommen. Nach dem
  Quittieren der Notabschaltung baut das HEMS den Controller neu auf. Die Sperre wird dabei aus
  dem alten Controller übernommen, weil sie dem SoC folgt und nicht dem Regelzustand.
- Geschrieben wird nach jedem Regelzyklus, aber nur wenn sich eine Sperre geändert hat, also
  selten.
- Fehlt die Datei oder ist sie unlesbar, startet das HEMS ohne Sperre (Verhalten vor D-066). Eine
  unlesbare Datei wird beim nächsten Wechsel überschrieben. Anders als bei D-059 (unlesbar =
  aktiv) und D-061 (unlesbar = gesperrt) ist das unkritisch: Im schlimmsten Fall lädt der
  Speicher einmal bis `soc_max` nach.
- Ein Schreibfehler wird geloggt und hält die Regelung nicht an.
- Ist der SoC im ersten Zyklus ungültig, bleibt die übernommene Sperre stehen.
- Einträge umbenannter oder gelöschter Speicher wirken nicht und fallen beim nächsten Schreiben
  weg.

## Folgen

- Kein Vertrag betroffen: keine neuen Entitäten, Statusfelder oder Topics. Im Status steht wie
  bisher `lade_blockiert_grund = soc_max`.
- Bekannte Grenze: Ändert sich `soc_max` bei gesetzter Sperre (Add-on-Feld oder EP-Vorschlag),
  wird erst bei `neues soc_max − Hysterese` freigegeben. Das ist dieselbe Semantik wie ohne
  Neustart.

## Rücknahmebedingung

Wenn das HEMS seinen Regelzustand allgemein persistiert, geht die Sperre in diesem Mechanismus auf.
