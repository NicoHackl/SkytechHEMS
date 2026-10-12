# D-064: Die reservierte Netzlade-Schnittstelle v1 entfällt ersatzlos

- **Datum:** 12.10.2026
- **Status:** Aktiv
- **Betrifft:** [`app/ems/devices.py`](../../app/ems/devices.py) (`BatteryDevice`), `web/src/`,
  Tests, Doku zu `class: battery`; behebt [B-4](../bekannte-luecken.md#offene-bugs)

## Kontext

Der AC-Speicher-Entwurf (`erweiterungen/erweiterung_ac_speicher_1.md` §11) hatte für ein späteres
Netzladen drei Helfer je Speicher reserviert: `input_boolean.ems_<prefix>_netzladen_aktiv`,
`input_number.ems_<prefix>_netzlade_leistung_w` und `input_number.ems_<prefix>_netzlade_soc_ziel_prozent`.
Die ersten beiden wurden bereits gelesen und **ausgeführt**: `netzladen_aktiv: on` schaltete die
D-B10-Klemme ab und lud mit `netzlade_leistung_w` aus dem Netz, ohne SoC-Ziel, Zeitlimit und
Preislogik (B-4). Das SoC-Ziel wurde nie gelesen.

Inzwischen ist entschieden, dass das HEMS den dynamischen Strompreis selbst auswertet
([D-065](D-065-preis-und-prognosemodul.md)). Ein externer Schalter „jetzt aus dem Netz laden“ mit
fester Leistung passt nicht mehr dazu. In der Anlage waren die Helfer am 12.10.2026 nicht angelegt.

## Betrachtete Optionen

### Option A — Ersatzlos entfernen (gewählt)

- Dafür: B-4 ist damit endgültig geschlossen; kein halbfertiger Pfad im Code; die Steuerung kann
  ihre Helfer ohne Rücksicht auf alte Namen neu festlegen.
- Dagegen: Die vorbereiteten Namen gehen verloren. Da sie nirgends angelegt waren, kostet das
  nichts.

### Option B — Pfad hart sperren, Helfer behalten

- Dafür: Namen bleiben reserviert.
- Dagegen: Toter Code mit einer Sperre, die man beim späteren Ausbau wieder lösen muss; die
  Semantik („externer Befehl mit fester Leistung“) widerspricht D-065.

## Entscheidung

Option A, vom User am 12.10.2026 so festgelegt (Plan „Dynamischer Strompreis“, F-16):

- Das HEMS liest `netzladen_aktiv` und `netzlade_leistung_w` nicht mehr. Stehen sie noch in HA,
  bleiben sie wirkungslos (Regressionstests in `tests/test_battery_device.py` und
  `tests/test_run_cycle.py`).
- Die D-B10-Klemme gilt **ohne Ausnahme**: Bei Hausdefizit wird nie geladen.
- Der D-B16-Zweig „Netzladen schlägt Entladen“ und der Sperrgrund `netzladen` entfallen.
- Das Statusfeld `netzladen_aktiv` je Speicher entfällt. Kein Vertrag und keine Gegenstelle hat es
  gelesen (geprüft: Energy Pilot, Power Flow Card, Battery- und Wallbox-Provider).

## Folgen

- **Positiv:** B-4 behoben; ein Speicher lädt nur noch aus PV-Überschuss.
- **Negativ:** keine.
- **Aufwand:** Code, Tests, Oberfläche (Statusfeld und Sperrgrund-Label), Doku.

## Rücknahmebedingung

Keine. Die Netzladesteuerung entsteht neu unter D-065 mit eigenen Helfern, eigenem SoC-Ziel und
eigenen Sicherungen. Die Regeln aus §11.3 des Entwurfs (Netzladen nicht in den Pool, sperrt
Entladen, SoC-Ziel und Zeitlimit, PV-Vorrang) gelten dort weiter als Anforderung.
