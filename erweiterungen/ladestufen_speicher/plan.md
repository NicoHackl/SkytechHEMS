# Plan: SoC-abhängige Maximal-Ladestufen für AC-Speicher

Stand: 29.09.2026 · Status: Entwurf, noch nicht umgesetzt

## Ausgangslage (Bestand in HA, per MCP gelesen)

Die alte E3DC-Regelung steckt im Template-Sensor „Verfügbare Leistung für Überschussverbraucher“
(`erweiterungen/zusatz_sensor_für_speicher_null_einspeisung/ueberschusssensor_von_ha.yaml`):

| Stufe | Schalter | SoC-Schwelle | Leistung |
|---|---|---|---|
| 1 | `input_boolean.ems_speicher_regelung_stufe_1_aktiv` (on) | `ems_speicher_soc_mindestwert_1` = 50 % | `ems_speicher_mindesladeleistung_1` = 4500 W |
| 2 | – (immer aktiv) | `ems_speicher_soc_mindestwert_2` = 65 % | `ems_speicher_mindesladeleistung_2` = 1500 W |

Logik dort: ab SoC ≥ Schwelle bekommt der E3DC **mindestens** die Stufenleistung, der Rest geht an
die Verbraucher; unterhalb aller Schwellen hat der Speicher Vorrang. Die Stufen sind fest verdrahtet
(genau zwei, Schalter nur an Stufe 1). Daneben setzt
`automation.pye3dc_max_ladeleistung_speicher_setzen` per `pyscript.e3dc_set_power_limits` ein
Ladelimit aus `sensor.speicher_max_ladeleistung_pye3dc` (YAML-Template, per MCP nicht einsehbar).

Diese Bestandsregelung bleibt **unberührt** — der E3DC ist kein HEMS-Gerät.

## Ziel

Optionale, beliebig viele Ladestufen je HEMS-Speicher (`class: battery`), die die **maximale**
Ladeleistung SoC-abhängig begrenzen. Ohne Stufen-Helfer ändert sich nichts.

## Entscheidungen (mit User geklärt, 29.09.2026)

1. Gilt nur für HEMS-Speicher (`class: battery`), Helfer im Namensraum `ems_<prefix>_*`.
2. Eine Stufe greift bei **SoC ≥ Schwelle**. Passen mehrere aktive Stufen, gilt das **kleinste
   Maximum** — die Reihenfolge der Stufen ist damit egal.
3. Einlesen durch **Hochzählen ab 1 bis zur ersten Lücke**.
4. **Keine** SoC-Hysterese; Rampe und Totband dämpfen.

## Namenskonvention (Vorschlag)

Angelehnt an die bestehenden Speicher-Helfer (`soc_min_prozent`, `min_ladeleistung_w`):

```text
input_boolean.ems_<prefix>_ladestufe_<n>_aktiv
input_number.ems_<prefix>_ladestufe_<n>_soc_prozent
input_number.ems_<prefix>_ladestufe_<n>_max_ladeleistung_w
```

`<n>` beginnt bei `1`, ohne führende Nullen. Beispiel `acspeicher1`, Stufe 2:
`input_number.ems_acspeicher1_ladestufe_2_max_ladeleistung_w`.

## Regelverhalten

```text
stufen_max = min(max_ladeleistung_w  für alle Stufen mit aktiv=on und SoC ≥ soc_prozent)
lade_limit = min(available_charge_power_w, stufen_max)   # ohne passende Stufe: unverändert
```

- Einbau in `BatteryDevice._lade_limit_w()` (`app/ems/devices.py`). Weil `_raw_max` daraus gespeist
  wird, bekommen die nachrangigen Verbraucher den Überschuss über dem Stufenmaximum automatisch.
- Ein gesunkenes Limit gilt sofort (bestehende Klemme nach der Rampe), ein steigendes läuft über
  Rampe und Regelzeiten.
- `max_ladeleistung_w = 0` sperrt den Ladepfad; neuer Sperrgrund `ladestufe` in `_darf_laden()`.
- `min_ladeleistung_w` > Stufenmaximum → Anforderung rastet auf `0 W` (heutiges `_raste`-Verhalten).
- Ungültiger SoC: Laden ist ohnehin gesperrt, Stufen werden nicht ausgewertet.

## Einlesen

- In `BatteryDevice.update_from_ha()` je Zyklus: `n = 1, 2, …` lesen, bis eine Stufe **fehlt**.
- Eine Stufe „existiert“, wenn der SoC-Helfer existiert (Anker). Fehlt er → Ende der Liste.
- Obergrenze als Schutz: höchstens 20 Stufen.

## Annahmen — bitte bestätigen

| # | Fall | Vorschlag |
|---|---|---|
| A1 | Schalter fehlt, SoC- und Max-Helfer vorhanden | Stufe gilt als **aktiv** (analog `laden_erlaubt`: nie angelegt = keine Zusatzbedingung) |
| A2 | Schalter `unavailable`/ungültig | Stufe gilt als **aktiv** — die strengere Grenze ist der sichere Zustand |
| A3 | SoC- oder Max-Wert `unavailable`/ungültig | Stufe wird ignoriert, Diagnose im Status |
| A4 | Max-Helfer fehlt ganz | wie Lücke → Ende der Liste |
| A5 | Energy Pilot | liefert keine Stufenvorschläge; physische Grenzen bleiben HA/Add-on-Sache |

## Status und Oberfläche

- Neue Statusfelder je Speicher: `ladestufe_aktiv` (Nummer oder `null`), `ladestufe_max_w`,
  `ladestufen` (Liste mit `n`, `aktiv`, `soc_prozent`, `max_w`, `gueltig`, `greift`).
- `web/src/pages/Status.tsx`: Zeile „Laden ≤ …“ um „(Stufe n)“ ergänzen; `types.ts` erweitern.
- Keine Bearbeitung in der Oberfläche — gepflegt wird über die HA-Helfer.

## Tests (`tests/test_battery_device.py`)

- keine Stufen → Verhalten wie bisher
- eine Stufe über/unter Schwelle; mehrere passend → kleinstes Maximum
- Lücke (Stufe 1, 3 vorhanden → nur 1 wirkt); Schalter aus
- A1–A3; Max `0` → Sperrgrund `ladestufe`; Limit sinkt sofort, steigt über Rampe
- Überschuss oberhalb des Stufenmaximums geht an nachrangige Verbraucher

## Doku und Pflichten im selben Arbeitspaket

- `docs/device_classes/battery.md` — neuer Abschnitt „Ladestufen“
- `docs/datenmodell.md` — neue Helfer und Statusfelder
- `docs/design-entscheidungen.md` + `docs/adr/D-056-ladestufen-speicher.md`
- `CHANGELOG.md`; Beispiel-Helfer in `erweiterungen/erster_ac_speicher/input_*.yaml`
- Build von `web/`, Bundle mit committen

## Offen außerhalb des Codes

- Stufenwerte für `acspeicher1` festlegen und Helfer in HA anlegen.
