# Regelbares Gerät (`class: controllable`)

Ein regelbares Gerät nimmt eine stufenlos vorgebbare Leistung auf, zum Beispiel ein Heizstab oder
eine Wallbox. Das HEMS liest die tatsächliche Leistung und schreibt einen Leistungssollwert. Es
unterstützt eine Regelung in Watt sowie eine Regelung in Ampere mit einer oder drei Phasen.

Zusätzlich zu den hier beschriebenen Feldern und Entitäten gelten die
[gemeinsamen Gerätefelder und HA-Helfer](global.md#gemeinsame-felder-in-devices).

## Felder in der Add-on-Konfiguration

| Feld | Pflicht | Default | Funktion beziehungsweise zugehörige Entität |
|---|---:|---|---|
| `actual_power_entity` | ja | – | Vollständige Entity-ID des nur gelesenen Ist-Leistungssensors in Watt |
| `output_unit` | nein | `watt` | `watt` verwendet `_w`-Helfer und schreibt Watt; `ampere` verwendet `_a`-Helfer und schreibt ganze Ampere |
| `phases` | nein | `"1"` | Nur bei `output_unit: ampere`: `"1"`, `"3"` oder `"1,3"`; bei ungültigem Inhalt wird eine Phase verwendet |
| `phase_switch_delay_s` | nein | `300` | Nur bei `phases: "1,3"`: Fallback für `input_number.ems_<prefix>_min_umschaltzeit_s` |
| `voltage_l1_entity` | nein | intern `230 V` | Optionaler Spannungssensor für L1; nur im Ampere-Modus gelesen |
| `voltage_l2_entity` | nein | intern `230 V` | Optionaler Spannungssensor für L2; nur bei dreiphasiger Umrechnung gelesen |
| `voltage_l3_entity` | nein | intern `230 V` | Optionaler Spannungssensor für L3; nur bei dreiphasiger Umrechnung gelesen |

Fehlt `actual_power_entity`, wird der Geräteeintrag beim Start übersprungen. Liefert der
konfigurierte Sensor später keinen numerischen Wert, verwendet der Zyklus `0 W`; anders als beim
globalen Überschuss-Sensor entsteht dadurch kein Hard-Lockout.

## Über Namenskonvention gelesene HA-Helfer

`<u>` ist `w` bei `output_unit: watt` und `a` bei `output_unit: ampere`.

| Entität | Einheit | Pflicht | Fehlender/ungültiger State | Funktion |
|---|---|---:|---|---|
| `input_number.ems_<prefix>_min_technisch_<u>` | W oder A | ja | `0` | Untere technische Grenze; Werte darunter rasten auf `0` oder auf das Minimum |
| `input_number.ems_<prefix>_max_technisch_<u>` | W oder A | ja | `0` | Obere technische Grenze; mit `0` kann das Gerät keine Leistung erhalten |
| `input_number.ems_<prefix>_geschutzte_mindestleistung_<u>` | W oder A | ja | `0` | Reservierter Sockel vor der normalen Überschussverteilung |
| `input_number.ems_<prefix>_reserve_w` | W | ja | `0` | Gerätespezifischer Zusatzpuffer; auch im Ampere-Modus immer Watt |
| `input_number.ems_<prefix>_hoch_regelzeit_s` | s | ja | `0` | Mindestabstand beim Erhöhen des Sollwerts |
| `input_number.ems_<prefix>_runter_regelzeit_s` | s | ja | `0` | Mindestabstand beim normalen Absenken; bei Defizit wird sofort abgesenkt |
| `input_number.ems_<prefix>_max_anderung_pro_schritt_<u>` | W oder A | ja | `1000` | Maximale Sollwertänderung je Regelzyklus |
| `input_number.ems_<prefix>_min_anderung_pro_schritt_<u>` | W oder A | ja | `0` | Totband; kleinere Änderungen werden nicht geschrieben |
| `input_number.ems_<prefix>_min_umschaltzeit_s` | s | nein | Add-on-Feld `phase_switch_delay_s` | Optionale Sperrzeit zwischen Phasenwechseln; nur bei `phases: "1,3"` gelesen |

Die vier [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer) werden ebenfalls gelesen.

## Externe, nur gelesene Entitäten

| Add-on-Feld | Pflicht | Erwarteter Wert | Funktion |
|---|---:|---|---|
| `actual_power_entity` | ja | Leistung in W, negativ wird auf `0` geklemmt | Tatsächliche Leistungsaufnahme und Pool-Rückrechnung |
| `voltage_l1_entity` | nein | `180 < U < 260 V` | Umrechnung A → W für L1 |
| `voltage_l2_entity` | nein | `180 < U < 260 V` | Umrechnung A → W für L2 |
| `voltage_l3_entity` | nein | `180 < U < 260 V` | Umrechnung A → W für L3 |

Ein fehlender oder unplausibler Spannungssensor wird einzeln durch `230 V` ersetzt.

## Gelesene und geschriebene HA-Helfer

| Entität | Wann erforderlich | Richtung | Funktion |
|---|---|---|---|
| `input_number.ems_<prefix>_anforderung_leistung_w` | `output_unit: watt` | lesen und schreiben | Aktueller und neuer Sollwert in Watt; `last_changed` steuert das Rampen-Timing |
| `input_number.ems_<prefix>_anforderung_leistung_a` | `output_unit: ampere` | lesen und schreiben | Sollwert in ganzen Ampere; intern rechnet das HEMS in Watt |
| `input_number.ems_<prefix>_anzahl_phase` | nur bei `phases: "1,3"` | lesen und schreiben | Zuletzt angeforderte und neu gewählte Phasenzahl `1` oder `3` |

Das HEMS schreibt den Leistungssollwert nur bei einer wirksamen Änderung. Dadurch bleibt
`last_changed` als Zeitbasis der Rampe nutzbar. Eine HA-Automation oder Geräteintegration muss den
Helferwert auf das reale Gerät übertragen.

## Fallbacks und interne Defaults

| Primäre Quelle | Fallback | Wirkung |
|---|---|---|
| `input_number.ems_<prefix>_min_umschaltzeit_s` mit Wert > `0` | `phase_switch_delay_s`, regulär `300 s` | Einziger unmittelbarer Add-on-Konfigurationsfallback für einen klassenspezifischen HA-Helfer |
| Konfigurierter Spannungssensor mit plausiblem State | intern `230 V` je Phase | Hält die A/W-Umrechnung bei fehlendem oder unplausiblem Sensor funktionsfähig |
| `entity_prefix` | `name` | Bestimmt nur die abgeleiteten Entity-IDs, nicht deren States |
| `output_unit` | `watt` | Bestimmt Suffix und Ausgabeeinheit |
| `phases` | `"1"` | Deaktiviert die automatische Phasenumschaltung |

Für `min_technisch`, `max_technisch`, Rampenwerte, Reserve und Priorität gibt es keine
entsprechenden Werte in der Add-on-Konfiguration. Die oben genannten internen Defaults sind nur
Ausfallsicherheit; die HA-Helfer bleiben Bestandteil des Gerätevertrags.

## Energy-Pilot-Vorschläge

Zusätzlich zu `sensor.ep_<prefix>_freigabe_vorschlag` und
`sensor.ep_<prefix>_prio_vorschlag` liest ein Watt-Gerät:

```text
sensor.ep_<prefix>_geschutzte_mindestleistung_w_vorschlag
```

Im Ampere-Modus wird dieser Watt-Vorschlag nicht übernommen. Für alle Vorschläge gelten der
[Commit-Vertrag und der Fallback auf die HA-Helfer](global.md#energy-pilot-vertrag).

## Pflicht für eine funktionsfähige Instanz

- Add-on-Felder `name`, `class: controllable` und `actual_power_entity`
- alle [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer)
- die klassenspezifischen Eingangshelfer mit zum Gerät passenden Grenzen
- der zur Ausgabeeinheit passende `anforderung_leistung_*`-Helfer
- bei `phases: "1,3"` zusätzlich `anzahl_phase`; `min_umschaltzeit_s` ist optional und
  überschreibt den Add-on-Fallback
- eine Automation oder Integration, die den Anforderungshelfer auf das reale Gerät überträgt

## Beispiel

```yaml
devices:
  - name: wallbox_1
    label: "Wallbox"
    class: controllable
    entity_prefix: wallbox
    allowed_modes: "manuell,nur_laden"
    actual_power_entity: sensor.wallbox_1_istleistung
    output_unit: "ampere"
    phases: "1,3"
    phase_switch_delay_s: 300
    voltage_l1_entity: sensor.netzspannung_l1
    voltage_l2_entity: sensor.netzspannung_l2
    voltage_l3_entity: sensor.netzspannung_l3
```
