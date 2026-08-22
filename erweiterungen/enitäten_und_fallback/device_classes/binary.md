# Binäres Gerät (`class: binary`)

Ein binäres Gerät kennt nur AN und AUS, zum Beispiel einen Heizlüfter. Das HEMS liest den realen
Schaltzustand, berechnet unter Berücksichtigung von Hysterese und Zeitschutz eine Anforderung und
schreibt diese in einen HA-Helfer. Eine HA-Automation setzt die Anforderung am realen Schalter um.

Zusätzlich zu den hier beschriebenen Feldern und Entitäten gelten die
[gemeinsamen Gerätefelder und HA-Helfer](global.md#gemeinsame-felder-in-devices).

## Felder in der Add-on-Konfiguration

| Feld | Pflicht | Default | Funktion beziehungsweise zugehörige Entität |
|---|---:|---|---|
| `switch_entity` | ja | – | Vollständige Entity-ID des realen Schalters; wird nur gelesen |

Fehlt `switch_entity`, wird der Geräteeintrag beim Start übersprungen. Für keinen
klassenspezifischen HA-Helfer eines binären Geräts existiert ein Ersatzwert in der
Add-on-Konfiguration.

## Über Namenskonvention gelesene HA-Helfer

| Entität | Einheit/Werte | Pflicht | Fehlender/ungültiger State | Funktion |
|---|---|---:|---|---|
| `input_number.ems_<prefix>_leistung_w` | W | ja | Muss als Fallback-Feld in der App/Addon Config vorhanden sein | Angenommene Leistungsaufnahme im EIN-Zustand; Grundlage der Pool-Reservierung |
| `input_number.ems_<prefix>_einschaltreserve_w` | W | ja | Muss als Fallback-Feld in der App/Addon Config vorhanden sein | Gerätespezifischer Hysterese-Aufschlag beim Einschalten, zusätzlich zur globalen Einschaltreserve |
| `input_number.ems_<prefix>_mindestlaufzeit_s` | s | ja | Muss als Fallback-Feld in der App/Addon Config vorhanden sein | Verhindert zu frühes Ausschalten; gilt auch bei Notabschaltung |
| `input_number.ems_<prefix>_mindestauszeit_s` | s | ja | Muss als Fallback-Feld in der App/Addon Config vorhanden sein | Verhindert zu frühes Wiedereinschalten |
| `input_number.ems_<prefix>_abschaltverzogerung_s` | s | ja | Muss als Fallback-feld in der App/Addon Config vorhanden sein | Verzögert den Aus-Befehl nach Ablauf der Mindestlaufzeit; gilt auch bei Notabschaltung |

Die vier [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer) werden ebenfalls gelesen.

## Externe, nur gelesene Entität

| Add-on-Feld | Erwarteter State | Funktion |
|---|---|---|
| `switch_entity` | `on` oder `off` | Liefert den tatsächlichen Zustand und über `last_changed` die aktuelle Lauf- beziehungsweise Auszeit |

Ein fehlender oder anderer State wird wie `off` behandelt. Die Laufzeitberechnung benötigt das
von Home Assistant bereitgestellte Attribut `last_changed`.

## Gelesener und geschriebener HA-Helfer

| Entität | Richtung | Werte | Funktion |
|---|---|---|---|
| `input_boolean.ems_<prefix>_anforderung_an` | lesen und schreiben | `on`, `off` | HEMS-Anforderung; unterscheidet eine eigene Anforderung von einem extern erzwungenen Schaltzustand |

Der Regelzyklus schreibt diese Anforderung derzeit in jedem Zyklus. Er schreibt niemals direkt auf
`switch_entity`.

## Fallbacks und interne Defaults

- `entity_prefix` fällt auf `name` zurück und bestimmt nur die Entity-IDs.
- Für `leistung_w`, Einschaltreserve und Zeitparameter gibt es keine entsprechenden
  Add-on-Konfigurationsfelder.
- Fehlende Zahlenwerte werden intern als `0` behandelt. Das ist ein sicherer technischer Fallback,
  aber kein Ersatz für die Pflicht-Helfer. Insbesondere macht `leistung_w: 0` die Pool-Rechnung
  fachlich unbrauchbar.
- `input_number.ems_einschaltreserve_global_w` wird zusätzlich zur gerätespezifischen
  `einschaltreserve_w` angewandt.

## Energy-Pilot-Vorschläge

Im EP-Modus liest ein binäres Gerät:

```text
sensor.ep_<prefix>_freigabe_vorschlag
sensor.ep_<prefix>_prio_vorschlag
```

Für beide gelten der [Commit-Vertrag und der Fallback auf die HA-Helfer](global.md#energy-pilot-vertrag).

## Pflicht für eine funktionsfähige Instanz

- Add-on-Felder `name`, `class: binary` und `switch_entity`
- alle [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer)
- alle fünf klassenspezifischen Eingangshelfer
- `input_boolean.ems_<prefix>_anforderung_an`
- eine HA-Automation, die `anforderung_an` auf den realen Schalter überträgt

## Beispiel

```yaml
devices:
  - name: heizlufter_1
    label: "Heizlüfter 1"
    class: binary
    allowed_modes: "manuell,nur_heizen"
    switch_entity: switch.heizlufter
```
