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
| `power_w` | ja | Formular `0` | Fallback für `leistung_w`; endlich und `> 0` |
| `on_reserve_w` | ja | Formular `0` | Fallback für `einschaltreserve_w`; endlich und `>= 0` |
| `min_runtime_s` | ja | Formular `0` | Fallback für `mindestlaufzeit_s`; endlich und `>= 0` |
| `min_offtime_s` | ja | Formular `0` | Fallback für `mindestauszeit_s`; endlich und `>= 0` |
| `off_delay_s` | ja | Formular `0` | Fallback für `abschaltverzogerung_s`; endlich und `>= 0` |
| `power_actual_entity` | nein | – | Ist-Leistungssensor als reine Datenquelle für spätere Ausbaustufen; aktuell ohne Wirkung auf die Regelung |

Fehlt `switch_entity` oder eines der fünf Fallbackfelder, wird der Geräteeintrag beim Start nicht
instanziiert und erscheint mit seinem konkreten Feldfehler unter `inactive_devices` im Status.
`power_w: 0` ist ausdrücklich ungültig: eine angenommene Leistung von null macht die Pool-Rechnung
fachlich unbrauchbar, und genau dieser Fall lief bisher unbemerkt mit.

## Über Namenskonvention gelesene HA-Helfer

Alle Helfer sind optional. Ein **gültiger** HA-State hat immer Vorrang; fehlt er, ist er
`unknown`/`unavailable` oder unbrauchbar, greift das gleichnamige Add-on-Feld. Die Ursache steht je
Entität in `entity_diagnostics`, siehe
[Doppelte Auflösung](global.md#doppelte-auflösung-von-ha-entitäten).

| Entität | Einheit/Werte | Ersatzwert bei fehlendem/ungültigem State | Funktion |
|---|---|---|---|
| `input_number.ems_<prefix>_leistung_w` | W | Add-on-Feld `power_w` | Angenommene Leistungsaufnahme im EIN-Zustand; Grundlage der Pool-Reservierung |
| `input_number.ems_<prefix>_einschaltreserve_w` | W | Add-on-Feld `on_reserve_w` | Gerätespezifischer Hysterese-Aufschlag beim Einschalten, zusätzlich zur globalen Einschaltreserve |
| `input_number.ems_<prefix>_mindestlaufzeit_s` | s | Add-on-Feld `min_runtime_s` | Verhindert zu frühes Ausschalten; gilt auch bei Notabschaltung |
| `input_number.ems_<prefix>_mindestauszeit_s` | s | Add-on-Feld `min_offtime_s` | Verhindert zu frühes Wiedereinschalten |
| `input_number.ems_<prefix>_abschaltverzogerung_s` | s | Add-on-Feld `off_delay_s` | Verzögert den Aus-Befehl nach Ablauf der Mindestlaufzeit; gilt auch bei Notabschaltung |

Ein negativer Wert ist ungültig und löst den Ersatzwert aus. Ein gültiger Wert `0` ist ein Wert und
wird nie ersetzt.

Die vier [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer) werden ebenfalls gelesen.

## Externe, nur gelesene Entitäten

| Add-on-Feld | Erwarteter State | Funktion |
|---|---|---|
| `switch_entity` | `on` oder `off` | Liefert den tatsächlichen Zustand und über `last_changed` die aktuelle Lauf- beziehungsweise Auszeit |
| `power_actual_entity` | numerischer Wert in Watt | Optional. Reine Datenquelle für spätere Ausbaustufen — erscheint als `power_actual_w` im Status, sofern konfiguriert und gültig. Ohne Wirkung auf die Regelung |

Ein fehlender oder anderer State wird wie `off` behandelt. Die Laufzeitberechnung benötigt das
von Home Assistant bereitgestellte Attribut `last_changed`. Ein fehlender oder ungültiger
`power_actual_entity`-State lässt lediglich `power_actual_w` im Status entfallen.

## Gelesener und geschriebener HA-Helfer

| Entität | Richtung | Werte | Funktion |
|---|---|---|---|
| `input_boolean.ems_<prefix>_anforderung_an` | lesen und schreiben | `on`, `off` | HEMS-Anforderung; unterscheidet eine eigene Anforderung von einem extern erzwungenen Schaltzustand |

Dieses Schreibziel hat **keinen** Fallback — eine Anforderung lässt sich nicht erfinden. Fehlt es,
ist es `unavailable` oder hat es die falsche Domain, wird das Gerät als
[zur Laufzeit inaktiv](global.md#schreibziele-und-inaktive-geräte) gekennzeichnet.

Der Regelzyklus schreibt diese Anforderung in jedem Zyklus. Er schreibt niemals direkt auf
`switch_entity`.

## Weitere Fallbacks

- `entity_prefix` fällt auf `name` zurück und bestimmt nur die Entity-IDs.
- `prioritat` behält den internen Fallback `99`.
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

- Add-on-Felder `name`, `class: binary`, `switch_entity` und die fünf Fallbackfelder
- alle [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer)
- `input_boolean.ems_<prefix>_anforderung_an`
- eine HA-Automation, die `anforderung_an` auf den realen Schalter überträgt

Die fünf klassenspezifischen Eingangshelfer sind dagegen optional: ohne sie regelt das Gerät mit
den Add-on-Werten weiter.

## Beispiel

```yaml
devices:
  - name: heizlufter_1
    label: "Heizlüfter 1"
    class: binary
    allowed_modes: "manuell,nur_heizen"
    switch_entity: switch.heizlufter
    power_w: 1500
    on_reserve_w: 200
    min_runtime_s: 600
    min_offtime_s: 300
    off_delay_s: 120
```
