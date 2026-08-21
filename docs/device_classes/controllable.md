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
| `technical_minimum` | ja | Formular `0` | Fallback für `min_technisch_<u>`; endlich und `>= 0` |
| `technical_maximum` | ja | Formular `0` | Fallback für `max_technisch_<u>`; endlich, `> 0` und `>= technical_minimum` |
| `increase_delay_s` | ja | Formular `60` | Fallback für `hoch_regelzeit_s`; endlich und `>= 0` |
| `decrease_delay_s` | ja | Formular `60` | Fallback für `runter_regelzeit_s`; endlich und `>= 0` |
| `maximum_step_change` | ja | Formular `1000` | Fallback für `max_anderung_pro_schritt_<u>`; endlich und `> 0` |
| `minimum_step_change` | ja | Formular `0` | Fallback für `min_anderung_pro_schritt_<u>`; endlich, `>= 0`, nicht größer als das Maximum |
| `output_unit` | nein | `watt` | `watt` verwendet `_w`-Helfer und schreibt Watt; `ampere` verwendet `_a`-Helfer und schreibt ganze Ampere |
| `phases` | nein | `"1"` | Nur bei `output_unit: ampere`: `"1"`, `"3"` oder `"1,3"` |
| `phase_switch_delay_s` | nein | `300` | Nur bei `phases: "1,3"`: Fallback für `input_number.ems_<prefix>_min_umschaltzeit_s` |
| `voltage_l1_entity` | nein | intern `230 V` | Optionaler Spannungssensor für L1; nur im Ampere-Modus gelesen |
| `voltage_l2_entity` | nein | intern `230 V` | Optionaler Spannungssensor für L2; nur bei dreiphasiger Umrechnung gelesen |
| `voltage_l3_entity` | nein | intern `230 V` | Optionaler Spannungssensor für L3; nur bei dreiphasiger Umrechnung gelesen |

`<u>` ist `w` bei `output_unit: watt` und `a` bei `output_unit: ampere`. **Die sechs
Fallbackwerte liegen in derselben nativen Einheit wie die zugehörigen Helfer**; die Umrechnung nach
Watt über Phasenzahl × Spannung erfolgt erst danach.

Fehlt `actual_power_entity` oder eines der sechs Fallbackfelder, wird der Geräteeintrag beim Start
nicht instanziiert und erscheint mit seinem konkreten Feldfehler unter `inactive_devices` im
Status. Der Formular-Startwert `0` für `technical_maximum` ist absichtlich ungültig: die reale
Obergrenze muss eingetragen werden, bevor ein neu angelegtes Gerät gespeichert werden kann.

Liefert der konfigurierte Ist-Sensor später keinen numerischen Wert, verwendet der Zyklus `0 W`;
anders als beim globalen Überschuss-Sensor entsteht dadurch kein Hard-Lockout.

## Über Namenskonvention gelesene HA-Helfer

Alle Helfer sind optional. Ein **gültiger** HA-State hat immer Vorrang; fehlt er, ist er
`unknown`/`unavailable` oder unbrauchbar, greift der in der Tabelle genannte Ersatzwert. Die
Ursache steht je Entität in `entity_diagnostics`, siehe
[Doppelte Auflösung](global.md#doppelte-auflösung-von-ha-entitäten).

| Entität | Einheit | Ersatzwert bei fehlendem/ungültigem State | Funktion |
|---|---|---|---|
| `input_number.ems_<prefix>_min_technisch_<u>` | W oder A | Add-on-Feld `technical_minimum` | Untere technische Grenze; Werte darunter rasten auf `0` oder auf das Minimum |
| `input_number.ems_<prefix>_max_technisch_<u>` | W oder A | Add-on-Feld `technical_maximum` | Obere technische Grenze; mit `0` kann das Gerät keine Leistung erhalten |
| `input_number.ems_<prefix>_hoch_regelzeit_s` | s | Add-on-Feld `increase_delay_s` | Mindestabstand beim Erhöhen des Sollwerts |
| `input_number.ems_<prefix>_runter_regelzeit_s` | s | Add-on-Feld `decrease_delay_s` | Mindestabstand beim normalen Absenken; bei Defizit wird sofort abgesenkt |
| `input_number.ems_<prefix>_max_anderung_pro_schritt_<u>` | W oder A | Add-on-Feld `maximum_step_change` | Maximale Sollwertänderung je Regelzyklus |
| `input_number.ems_<prefix>_min_anderung_pro_schritt_<u>` | W oder A | Add-on-Feld `minimum_step_change` | Totband; kleinere Änderungen werden nicht geschrieben |
| `input_number.ems_<prefix>_geschutzte_mindestleistung_<u>` | W oder A | intern `0` | Reservierter Sockel vor der normalen Überschussverteilung |
| `input_number.ems_<prefix>_reserve_w` | W | intern `0` | Gerätespezifischer Zusatzpuffer; auch im Ampere-Modus immer Watt |
| `input_number.ems_<prefix>_min_umschaltzeit_s` | s | Add-on-Feld `phase_switch_delay_s`, sonst intern `30` | Sperrzeit zwischen Phasenwechseln; nur bei `phases: "1,3"` gelesen |

Ein negativer Wert ist in allen Feldern oben ungültig und löst den Ersatzwert aus. Ein gültiger
Wert `0` ist dagegen ein Wert und wird nie ersetzt — auch nicht bei `min_umschaltzeit_s`.

Die vier [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer) werden ebenfalls gelesen.

## Externe, nur gelesene Entitäten

| Add-on-Feld | Pflicht | Erwarteter Wert | Funktion |
|---|---:|---|---|
| `actual_power_entity` | ja | Leistung in W, negativ wird auf `0` geklemmt | Tatsächliche Leistungsaufnahme und Pool-Rückrechnung |
| `voltage_l1_entity` | nein | `180 < U < 260 V` | Umrechnung A → W für L1 |
| `voltage_l2_entity` | nein | `180 < U < 260 V` | Umrechnung A → W für L2 |
| `voltage_l3_entity` | nein | `180 < U < 260 V` | Umrechnung A → W für L3 |

Ein fehlender oder unplausibler Spannungssensor wird einzeln durch `230 V` ersetzt und in der
Diagnose als `invalid` geführt — ein Wert außerhalb des Fensters ist kein Messwert, sondern ein
Sensorfehler.

## Gelesene und geschriebene HA-Helfer

| Entität | Wann erforderlich | Richtung | Funktion |
|---|---|---|---|
| `input_number.ems_<prefix>_anforderung_leistung_w` | `output_unit: watt` | lesen und schreiben | Aktueller und neuer Sollwert in Watt; `last_changed` steuert das Rampen-Timing |
| `input_number.ems_<prefix>_anforderung_leistung_a` | `output_unit: ampere` | lesen und schreiben | Sollwert in ganzen Ampere; intern rechnet das HEMS in Watt |
| `input_number.ems_<prefix>_anzahl_phase` | nur bei `phases: "1,3"` | lesen und schreiben | Zuletzt angeforderte und neu gewählte Phasenzahl `1` oder `3` |

Diese Schreibziele haben **keinen** Fallback — ein Sollwert lässt sich nicht erfinden. Fehlt einer,
ist er `unavailable` oder hat er die falsche Domain, wird das Gerät als
[zur Laufzeit inaktiv](global.md#schreibziele-und-inaktive-geräte) gekennzeichnet.

Das HEMS schreibt den Leistungssollwert nur bei einer wirksamen Änderung. Dadurch bleibt
`last_changed` als Zeitbasis der Rampe nutzbar. Eine HA-Automation oder Geräteintegration muss den
Helferwert auf das reale Gerät übertragen.

## Energy-Pilot-Vorschläge

Zusätzlich zu `sensor.ep_<prefix>_freigabe_vorschlag` und
`sensor.ep_<prefix>_prio_vorschlag` liest ein Watt-Gerät:

```text
sensor.ep_<prefix>_geschutzte_mindestleistung_w_vorschlag
```

Im Ampere-Modus wird dieser Watt-Vorschlag nicht übernommen. Für alle Vorschläge gelten der
[Commit-Vertrag und der Fallback auf die HA-Helfer](global.md#energy-pilot-vertrag).

## Pflicht für eine funktionsfähige Instanz

- Add-on-Felder `name`, `class: controllable`, `actual_power_entity` und die sechs Fallbackfelder
- alle [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer)
- der zur Ausgabeeinheit passende `anforderung_leistung_*`-Helfer
- bei `phases: "1,3"` zusätzlich `anzahl_phase`
- eine Automation oder Integration, die den Anforderungshelfer auf das reale Gerät überträgt

Die klassenspezifischen Eingangshelfer sind dagegen optional: ohne sie regelt das Gerät mit den
Add-on-Werten weiter, statt still auf `0` zu fallen.

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
    technical_minimum: 6
    technical_maximum: 16
    increase_delay_s: 60
    decrease_delay_s: 60
    maximum_step_change: 2
    minimum_step_change: 1
```
