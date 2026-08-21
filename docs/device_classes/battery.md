# AC-Speicher (`class: battery`)

Ein AC-Speicher kann als einziges HEMS-Gerät Leistung aufnehmen und abgeben. Laden konkurriert in
der normalen Prioritätsreihenfolge um PV-Überschuss. Entladen deckt ausschließlich normalen
Hausverbrauch und wird getrennt über `entlade_prioritat` verteilt.

Zusätzlich zu den hier beschriebenen Feldern und Entitäten gelten die
[gemeinsamen Gerätefelder und HA-Helfer](global.md#gemeinsame-felder-in-devices).

## Felder in der Add-on-Konfiguration

| Feld | Pflicht | Default | Funktion beziehungsweise zugehörige Entität |
|---|---:|---|---|
| `soc_entity` | ja | – | Vollständige Entity-ID des Ladezustandssensors in Prozent |
| `available_charge_power_entity` | ja | – | Momentan verfügbare **Ladeleistung** des Wechselrichters in Watt |
| `available_discharge_power_entity` | ja | – | Momentan verfügbare **Entladeleistung** des Wechselrichters in Watt |
| `charge_power_entity` | Variante A | – | Ist-Ladeleistung in W, immer ≥ `0` |
| `discharge_power_entity` | Variante A | – | Ist-Entladeleistung in W, immer ≥ `0` |
| `power_entity` | Variante B | – | Ein signierter Ist-Leistungssensor für beide Richtungen |
| `power_sign` | nur mit `power_entity` | `positiv_laden` | `positiv_laden` oder `positiv_entladen` |
| `capacity_kwh` | nein | `0` | Nutzbare Kapazität, ausschließlich Anzeige |
| `soc_max_hysteresis_percent` | ja, mit Default | `2` | Abstand unter `soc_max`, bevor Laden wieder freigegeben wird |
| `direction_switch_delay_s` | ja, mit Default | `5` | Sperrzeit in Sekunden nach einem Richtungswechsel |

Es muss **genau eine** Leistungssensor-Variante vollständig konfiguriert sein:

- **Variante A:** `charge_power_entity` **und** `discharge_power_entity`
- **Variante B:** `power_entity`, dazu passend `power_sign`

Beide Varianten gleichzeitig sind ungültig — welche gilt, wäre nicht mehr eindeutig. Fehlen
`soc_entity`, eine vollständige Leistungsvariante oder einer der beiden `available_*`-Sensoren,
wird der Geräteeintrag beim Start nicht instanziiert und erscheint als
[inaktives Gerät](global.md#ungültige-geräteeinträge).

`soc_max_hysteresis_percent` und `direction_switch_delay_s` ersetzen die entfallenen HA-Helfer
`soc_max_hysterese_prozent` und `min_umschaltzeit_s`. Fehlen sie in einer Bestandskonfiguration,
greift der Default; der Speicher wird davon **nicht** inaktiv.

## Die beiden `available_*`-Sensoren

Sie sind die **alleinigen physischen Maximalgrenzen** des Speichers. Es gibt daneben keinen
konfigurierten Maximalwert und kein zweites Drosselband mehr:

- Jede Richtung wird **getrennt** ausgewertet. Ein fehlender, `unavailable`/`unknown` oder
  unbrauchbarer Ladesensor sperrt ausschließlich den **Ladepfad** auf `0 W`; der Entladepfad läuft
  weiter — und umgekehrt.
- Ein **gültiger Wert `0`** sperrt die Richtung bewusst. Er ist kein Fehler und wird deshalb auch
  nicht durch einen Ersatzwert überschrieben.
- Innerhalb der SoC-Grenzen ist das momentane Limit maßgeblich, an der Grenze wird die Richtung
  `0`. Ein lineares SoC-Taper gibt es nicht mehr: die CV-Phase regelt der Wechselrichter selbst,
  und genau das meldet er über diese Sensoren. Ein zweites Drosselband im HEMS regelte dagegen.
- Sinkt ein gültiges Limit, gilt das **sofort**. Die Rampe darf ein Ziel bremsen, aber nach der
  Rampenrechnung liegt der Sollwert nie über der momentanen physischen Grenze.

Welcher Fall vorliegt, steht in `entity_diagnostics` und in den Sperrgründen: `limit_sensor` heißt
„Sensor unbrauchbar", `wr_derating` heißt „gültige Grenze ist 0".

## Über Namenskonvention gelesene HA-Helfer

Alle Helfer sind optional. Ein **gültiger** HA-State hat Vorrang; sonst gilt der Ersatzwert.

### Freigaben und Richtung

| Entität | Werte | Fehlende Entität | Ausgefallener/ungültiger State | Funktion |
|---|---|---|---|---|
| `input_select.ems_<prefix>_betriebsart` | `auto`, `nur_laden`, `nur_entladen`, `standby` | `standby` | `standby` | Legt fest, welche Richtung das HEMS grundsätzlich verwenden darf |
| `input_boolean.ems_<prefix>_laden_erlaubt` | `on`, `off` | **erlaubt** | **gesperrt** | Zusätzliche Freigabe des Ladepfads |
| `input_boolean.ems_<prefix>_entladen_erlaubt` | `on`, `off` | **erlaubt** | **gesperrt** | Zusätzliche Freigabe des Entladepfads |

Die Freigaben sind der einzige Fall, in dem „Entität gar nicht angelegt" und „Entität ausgefallen"
verschieden behandelt werden: wer den Schalter nie angelegt hat, will keine zusätzliche Sperre —
ein *ausgefallener* Schalter ist dagegen kein Grund, weiterzuregeln.

### Prioritäten und Leistungsgrenzen

| Entität | Einheit | Ersatzwert | Funktion |
|---|---|---|---|
| `input_number.ems_<prefix>_entlade_prioritat` | – | intern `50` | Unabhängige Entladereihenfolge; kleinere Zahl entlädt zuerst |
| `input_number.ems_<prefix>_min_ladeleistung_w` | W | intern `0` | Untere Ladegrenze; kleinere Anforderungen rasten auf `0` |
| `input_number.ems_<prefix>_min_entladeleistung_w` | W | intern `0` | Untere Entladegrenze; kleinere Anforderungen rasten auf `0` |

### SoC-Grenzen

| Entität | Einheit | Ersatzwert | Funktion |
|---|---|---|---|
| `input_number.ems_<prefix>_soc_min_prozent` | % | intern `10` | Tiefentladeschutz und **einziger** Entladeboden |
| `input_number.ems_<prefix>_soc_max_prozent` | % | intern `100` | Ladeschluss |

### Regelverhalten

| Entität | Einheit | Ersatzwert | Funktion |
|---|---|---|---|
| `input_number.ems_<prefix>_geschutzte_mindestleistung_w` | W | intern `0` | Reservierter Ladesockel gegenüber binären Geräten |
| `input_number.ems_<prefix>_reserve_w` | W | intern `50` | Gerätespezifischer Zusatzpuffer beim Laden; eine vorhandene Entität mit gültiger `0` setzt ihn bewusst ab |
| `input_number.ems_<prefix>_hoch_regelzeit_s` | s | intern `0` | Mindestabstand beim Erhöhen von Lade- oder Entladeleistung |
| `input_number.ems_<prefix>_runter_regelzeit_s` | s | intern `0` | Mindestabstand beim normalen Absenken der Ladeleistung |
| `input_number.ems_<prefix>_max_anderung_pro_schritt_w` | W | **keine Begrenzung** | Maximale Änderung je Regelzyklus; ohne gültigen Wert wird das Ziel unmittelbar erreicht |
| `input_number.ems_<prefix>_min_anderung_pro_schritt_w` | W | intern `0` | Schreib-Totband |
| `input_number.ems_<prefix>_umschalt_totzone_w` | W | intern `100` | Nettoanforderungen innerhalb der Totzone führen zu `standby` |

Die vier [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer) werden ebenfalls gelesen.
`prioritat` ist dabei ausschließlich die Ladepriorität.

`min_technisch_w` und `max_technisch_w` werden für den Speicher **nicht** gelesen: die Basisklasse
bekommt ihre Grenzen aus `min_ladeleistung_w` und dem momentanen Ladelimit.

### Entfallene Helfer

Diese Entitäten werden nicht mehr gelesen und haben keine Wirkung mehr. Sie dürfen gelöscht werden:

```text
input_number.ems_<prefix>_max_ladeleistung_w
input_number.ems_<prefix>_max_entladeleistung_w
input_number.ems_<prefix>_soc_reserve_prozent
input_number.ems_<prefix>_soc_taper_band_prozent
input_number.ems_<prefix>_soc_max_hysterese_prozent
input_number.ems_<prefix>_entlade_sofort_schwelle_w
input_number.ems_<prefix>_min_umschaltzeit_s
```

Die Maximalleistungen ersetzen die beiden `available_*`-Sensoren. Notstromreserve
(`soc_reserve_prozent`), Drosselband (`soc_taper_band_prozent`) und Entlade-Sofort-Schwelle
(`entlade_sofort_schwelle_w`) **entfallen ersatzlos**; Hysterese und Umschaltsperre sind jetzt
statische Add-on-Felder.

## Externe, nur gelesene Entitäten

| Add-on-Feld | Erwarteter Wert | Ausfallverhalten |
|---|---|---|
| `soc_entity` | SoC in Prozent | Fehlend, `unknown` oder `unavailable`: Speicher geht auf `0 W` und `standby` |
| `charge_power_entity` | Ladeleistung ≥ `0 W` | Einer der beiden Sensoren ungültig: Speicher geht in den sicheren Zustand |
| `discharge_power_entity` | Entladeleistung ≥ `0 W` | Einer der beiden Sensoren ungültig: Speicher geht in den sicheren Zustand |
| `power_entity` | signierte Leistung gemäß `power_sign` | Ungültiger State: Speicher geht in den sicheren Zustand |
| `available_charge_power_entity` | Ladelimit ≥ `0 W` | Ungültig: **nur** der Ladepfad wird auf `0 W` gesperrt |
| `available_discharge_power_entity` | Entladelimit ≥ `0 W` | Ungültig: **nur** der Entladepfad wird auf `0 W` gesperrt |

Ein ungültiger Speicher blockiert nicht die übrigen Speicher.

## Gelesene und geschriebene HA-Helfer

| Entität | Richtung | Werte | Funktion |
|---|---|---|---|
| `input_number.ems_<prefix>_anforderung_leistung_w` | lesen und schreiben | positiv = laden, negativ = entladen, `0` = aus | Ein gemeinsamer signierter Sollwert; `last_changed` ist die Zeitbasis der Rampen |
| `input_select.ems_<prefix>_anforderung_betriebsart` | lesen und schreiben | `laden`, `entladen`, `standby` | Explizite Betriebsart für die nachgelagerte Geräteautomation |

Beide sind [Schreibziele ohne Fallback](global.md#schreibziele-und-inaktive-geräte): fehlt einer,
ist er `unavailable`, hat er die falsche Domain, fehlen dem Auswahlhelfer Optionen oder erlaubt der
Zahlenhelfer keinen negativen Wert, wird der Speicher als zur Laufzeit inaktiv gekennzeichnet und
fährt nur noch `0 W` und `standby`.

Der Zahlenhelfer muss ein ausreichend **negatives Minimum** besitzen. Mit `min: 0` klemmt Home
Assistant jede Entladeanforderung auf `0`. Der Auswahlhelfer braucht genau die drei Optionen
`laden`, `entladen` und `standby`. Die Geräteautomation muss die beiden Ausgaben in der vom
Wechselrichter verlangten Reihenfolge nach Modbus, MQTT oder eine andere Schnittstelle übersetzen.

## Rampen und Sofort-Klemmen

Erhöhungen und normale Absenkungen laufen ausschließlich über
`max_anderung_pro_schritt_w`. Eine eigene Sofort-Schwelle für den Lastabwurf gibt es nicht mehr —
die Fälle, die wirklich unverzüglich auf `0 W` müssen, greifen ohnehin vor der Rampe:

- sicherer Standby (nicht freigegeben, Lockout, Betriebsart `standby`),
- ein ungültiger SoC- oder Ist-Leistungssensor,
- ein Richtungswechsel innerhalb der Umschaltsperre,
- ein Netzdefizit auf der Ladeseite.

## Reservierte Netzlade-Helfer: nicht aktivieren

Der aktuelle Code liest außerdem:

```text
input_boolean.ems_<prefix>_netzladen_aktiv
input_number.ems_<prefix>_netzlade_leistung_w
```

Diese Schnittstelle ist noch nicht freigegeben und nicht hart auf AUS geklemmt:
`netzladen_aktiv: on` kann den Leistungspfad aktivieren, obwohl SoC-Ziel, Preislogik und
vollständige Sicherheitsbegrenzung fehlen. Beide Helfer müssen bis zur Behebung von
[B-4](../bekannte-luecken.md#offene-bugs) auf `off` beziehungsweise `0 W` bleiben oder dürfen ganz
fehlen.

## Energy-Pilot-Vorschläge

Im EP-Modus liest ein Speicher diese Vorschläge:

```text
sensor.ep_<prefix>_freigabe_vorschlag
sensor.ep_<prefix>_prio_vorschlag
sensor.ep_<prefix>_geschutzte_mindestleistung_w_vorschlag
sensor.ep_<prefix>_entlade_prio_vorschlag
sensor.ep_<prefix>_soc_ziel_prozent_vorschlag
sensor.ep_<prefix>_soc_min_prozent_vorschlag
sensor.ep_<prefix>_betriebsart_vorschlag
```

`lade_max_w` und `entlade_max_w` gehören **nicht** mehr dazu und werden ignoriert: der Energy Pilot
darf physische Grenzen des Wechselrichters nicht überschreiben.

Für alle übrigen gelten der [Commit-Vertrag und der Fallback auf die HA-Helfer](global.md#energy-pilot-vertrag).
Die technische Freigabe und gültige Messwerte bleiben harte Gates.

## Global zusätzlich erforderlich

```text
input_number.ems_ac_speicher_entlade_abschlag_w
```

Der Abschlag ist eine **Systemgröße**: er wird einmal vom gesamten Hausdefizit abgezogen, bevor
dieses nach `entlade_prioritat` auf alle entladebereiten Speicher verteilt wird — kein Wert je
Speicher. Details und die Option `speicher_in_residual_enthalten` stehen in
[global.md](global.md#globale-ha-helfer).

## Pflicht für eine funktionsfähige Instanz

- Add-on-Felder `name`, `class: battery`, `soc_entity`, beide `available_*`-Sensoren
- entweder beide Felder `charge_power_entity` und `discharge_power_entity` oder `power_entity`
- alle [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer)
- beide Anforderungshelfer: negatives Minimum beim Sollwert, drei Optionen bei der Betriebsart
- globaler Entlade-Abschlag und korrekt geprüfte Option `speicher_in_residual_enthalten`
- eine Geräteautomation sowie ein unabhängiger Watchdog, der bei ausbleibenden HEMS-Aktualisierungen
  `0 W` und `standby` setzt

Für diese Anlage darf das Präfix nicht `speicher` sein, weil `ems_speicher_*` bereits zur
vorhandenen E3DC-Regelung gehört. Der geplante Präfix lautet `acspeicher1`; der E3DC selbst wird
nicht als `battery` eingetragen.

## Beispiel

```yaml
speicher_in_residual_enthalten: true

devices:
  - name: acspeicher1
    label: "AC-Speicher"
    class: battery
    entity_prefix: acspeicher1
    allowed_modes: "manuell,nur_heizen,nur_laden"
    soc_entity: sensor.acspeicher1_soc
    charge_power_entity: sensor.acspeicher1_ladeleistung
    discharge_power_entity: sensor.acspeicher1_entladeleistung
    available_charge_power_entity: sensor.acspeicher1_verfugbare_ladeleistung
    available_discharge_power_entity: sensor.acspeicher1_verfugbare_entladeleistung
    capacity_kwh: 12.8
    soc_max_hysteresis_percent: 2
    direction_switch_delay_s: 5
```
