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
| `charge_power_entity` | zusammen mit `discharge_power_entity` in Variante A | – | Ist-Ladeleistung in W, immer ≥ `0` |
| `discharge_power_entity` | zusammen mit `charge_power_entity` in Variante A | – | Ist-Entladeleistung in W, immer ≥ `0` |
| `power_entity` | anstelle von Variante A | – | Ein signierter Ist-Leistungssensor für beide Richtungen |
| `power_sign` | nur zusammen mit `power_entity` sinnvoll | `positiv_laden` | `positiv_laden` oder `positiv_entladen` beschreibt das Vorzeichen von `power_entity` |
| `available_charge_power_entity` | ja | nicht begrenzt | Optionales momentanes WR-Ladelimit; ein gültiger Wert hat Vorrang vor dem HA-Maximum |
| `available_discharge_power_entity` | ja | nicht begrenzt | Optionales momentanes WR-Entladelimit; ein gültiger Wert hat Vorrang vor dem HA-Maximum |
| `capacity_kwh` | nein | `0` | Nutzbare Kapazität, ausschließlich für Energieanzeige und kapazitätsgewichteten SoC |

Es muss genau eine Leistungssensor-Variante vollständig konfiguriert sein:

- **Variante A:** `charge_power_entity` und `discharge_power_entity`
- **Variante B:** `power_entity`, optional mit `power_sign`

Fehlen `soc_entity` oder eine vollständige Leistungsvariante, wird der Geräteeintrag beim Start
übersprungen. Werden beide Varianten angegeben, verwendet der aktuelle Code `power_entity`; eine
doppelte Konfiguration sollte deshalb vermieden werden.

## Über Namenskonvention gelesene HA-Helfer

### Freigaben und Richtung

| Entität | Werte | Pflicht | Fehlender/ungültiger State | Funktion |
|---|---|---:|---|---|
| `input_select.ems_<prefix>_betriebsart` | `auto`, `nur_laden`, `nur_entladen`, `standby` | ja | `standby` | Legt fest, welche Richtung das HEMS grundsätzlich verwenden darf |
| `input_boolean.ems_<prefix>_laden_erlaubt` | `on`, `off` | nein | `on` | Zusätzliche Freigabe des Ladepfads |
| `input_boolean.ems_<prefix>_entladen_erlaubt` | `on`, `off` | nein | `on` | Zusätzliche Freigabe des Entladepfads |

### Prioritäten und Leistungsgrenzen

| Entität | Einheit | Pflicht | Fehlender/ungültiger State | Funktion | Kommentar von Admin|
|---|---|---:|---|---|---|
| `input_number.ems_<prefix>_entlade_prioritat` | – | ja | `50` | Unabhängige Entladereihenfolge; kleinere Zahl entlädt zuerst |
| `input_number.ems_<prefix>_max_ladeleistung_w` | W | ja | `0` | Maximale Ladeleistung vor SoC-Taper und optionalem WR-Derating | -> wird gelöscht und wird durch `available_charge_power_entity`ersetzt (Addon/App Config)
| `input_number.ems_<prefix>_min_ladeleistung_w` | W | nein | `0` | Untere Ladegrenze; kleinere Anforderungen rasten auf `0` |
| `input_number.ems_<prefix>_max_entladeleistung_w` | W | ja | `0` | Maximale Entladeleistung vor SoC-Taper und optionalem WR-Derating | -> wird gelöscht und wird durch `available_discharge_power_entity`ersetzt (Addon/App Config)
| `input_number.ems_<prefix>_min_entladeleistung_w` | W | nein | `0` | Untere Entladegrenze; kleinere Anforderungen rasten auf `0` |

### SoC-Grenzen

| Entität | Einheit | Pflicht | Fehlender/ungültiger State | Funktion | Kommentar durch Admin |
|---|---|---:|---|---|---|
| `input_number.ems_<prefix>_soc_min_prozent` | % | nein | `10` | Tiefentladeschutz | 
| `input_number.ems_<prefix>_soc_max_prozent` | % | nein | `100` | Ladeschluss |
| `input_number.ems_<prefix>_soc_reserve_prozent` | % | ja | `0` | Notstromreserve; maßgeblich ist das Maximum aus Minimum und Reserve | -> Wird gelöscht und Wert/Funktion dahinter nicht weiter verwendet
| `input_number.ems_<prefix>_soc_taper_band_prozent` | % | ja | `5` | Drosselband vor oberer beziehungsweise unterer SoC-Grenze | -> Wird gelöscht und Wert/Funktion dahinter nicht weiter verwendet
| `input_number.ems_<prefix>_soc_max_hysterese_prozent` | % | ja | `2` | Abstand unter `soc_max`, bevor Laden nach Erreichen des Maximums wieder freigegeben wird | -> muss als Pflichtfelder in der App/Addon Config für AC Speicher hinzugefügt werden, als default schon mit 2% vorbelegen

### Regelverhalten

| Entität | Einheit | Pflicht | Fehlender/ungültiger State | Funktion | Kommentar durch Admin
|---|---|---:|---|---|---|
| `input_number.ems_<prefix>_geschutzte_mindestleistung_w` | W | ja | `0` | Reservierter Ladesockel gegenüber binären Geräten |
| `input_number.ems_<prefix>_reserve_w` | W | nein | 50 | Gerätespezifischer Zusatzpuffer beim Laden |
| `input_number.ems_<prefix>_hoch_regelzeit_s` | s | ja | `0` | Mindestabstand beim Erhöhen von Lade- oder Entladeleistung; muss mindestens den Sensorversatz abdecken |
| `input_number.ems_<prefix>_runter_regelzeit_s` | s | ja | `0` | Mindestabstand beim normalen Absenken der Ladeleistung |
| `input_number.ems_<prefix>_max_anderung_pro_schritt_w` | W | nein | Keine Begrenzung | Maximale Änderung je Regelzyklus |
| `input_number.ems_<prefix>_min_anderung_pro_schritt_w` | W | ja | `0` | Schreib-Totband |
| `input_number.ems_<prefix>_entlade_sofort_schwelle_w` | W | ja | `300` | Ab dieser Entladeabsenkung wird ein echter Lastabwurf sofort umgesetzt | ->Brauch ich eine genau erklärung und dann nachfragen was damit passieren soll (behalten, löschen, ersetzten, fallback etc.)
| `input_number.ems_<prefix>_umschalt_totzone_w` | W | ja | `100` | Nettoanforderungen innerhalb der Totzone führen zu `standby` |
| `input_number.ems_<prefix>_min_umschaltzeit_s` | s | ja |  | Sperrzeit nach einem Richtungswechsel; währenddessen wird `standby` angefordert | -> Muss als Addon/App Config Feld für AC Speicher, soll mit 5s vorbelegt werden

Die vier [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer) werden ebenfalls gelesen.
`prioritat` ist dabei ausschließlich die Ladepriorität.

`input_number.ems_<prefix>_min_technisch_w` und
`input_number.ems_<prefix>_max_technisch_w` werden wegen der Vererbung technisch abgefragt, danach
aber sofort durch die Ladegrenzen ersetzt. Sie haben für `battery` keine Wirkung, gehören nicht
zum Speichervertrag und müssen nicht angelegt werden.

## Externe, nur gelesene Entitäten

| Add-on-Feld | Erwarteter Wert | Ausfallverhalten |
|---|---|---|
| `soc_entity` | SoC in Prozent | Fehlend, `unknown` oder `unavailable`: Speicher geht auf `0 W` und `standby` |
| `charge_power_entity` | Ladeleistung ≥ `0 W` | Einer der beiden Sensoren ungültig: Speicher geht in den sicheren Zustand |
| `discharge_power_entity` | Entladeleistung ≥ `0 W` | Einer der beiden Sensoren ungültig: Speicher geht in den sicheren Zustand |
| `power_entity` | signierte Leistung gemäß `power_sign` | Ungültiger State: Speicher geht in den sicheren Zustand |
| `available_charge_power_entity` | momentanes Limit ≥ `0 W` | Ungültiger State: optionales Limit wird ignoriert |
| `available_discharge_power_entity` | momentanes Limit ≥ `0 W` | Ungültiger State: optionales Limit wird ignoriert |

Ein ungültiger Speicher blockiert nicht die übrigen Speicher.

## Gelesene und geschriebene HA-Helfer

| Entität | Richtung | Werte | Funktion |
|---|---|---|---|
| `input_number.ems_<prefix>_anforderung_leistung_w` | lesen und schreiben | positiv = laden, negativ = entladen, `0` = aus | Ein gemeinsamer signierter Sollwert; `last_changed` ist die Zeitbasis der Rampen |
| `input_select.ems_<prefix>_anforderung_betriebsart` | lesen und schreiben | `laden`, `entladen`, `standby` | Explizite Betriebsart für die nachgelagerte Geräteautomation |

Der Zahlenhelfer muss ein ausreichend negatives Minimum besitzen. Mit `min: 0` klemmt Home
Assistant jede Entladeanforderung auf `0`. Die Geräteautomation muss die beiden Ausgaben in der
vom Wechselrichter verlangten Reihenfolge nach Modbus, MQTT oder eine andere Schnittstelle
übersetzen.

## Fallbacks und interne Defaults

- Für keinen speicherspezifischen HA-Helfer gibt es einen Wert in der Add-on-Konfiguration.
- `capacity_kwh` ist ein statischer Anzeigewert und ersetzt keinen SoC- oder Leistungssensor.
- Ein ungültiges optionales WR-Limit fällt auf das jeweilige HA-Maximum
  `max_ladeleistung_w` beziehungsweise `max_entladeleistung_w` zurück.
- `entity_prefix` fällt auf `name`, `power_sign` auf `positiv_laden` und `capacity_kwh` auf `0`
  zurück.
- Fehlende Freigaben werden sicher als `off`, fehlende Maximalleistungen als `0 W` behandelt.
  Damit bleibt der Speicher aus; die Defaults ersetzen keine Pflicht-Helfer.

## Reservierte Netzlade-Helfer: nicht aktivieren

Der aktuelle Code liest außerdem:

```text
input_boolean.ems_<prefix>_netzladen_aktiv
input_number.ems_<prefix>_netzlade_leistung_w
```

Diese Schnittstelle ist noch nicht freigegeben. Entgegen der früheren Dokumentation ist sie nicht
hart auf AUS geklemmt: `netzladen_aktiv: on` kann den Leistungspfad aktivieren, obwohl SoC-Ziel,
Preislogik und vollständige Sicherheitsbegrenzung fehlen. Beide Helfer müssen bis zur Behebung von
[B-4](../bekannte-luecken.md#offene-bugs) auf `off` beziehungsweise `0 W` bleiben oder dürfen ganz
fehlen.

`input_number.ems_<prefix>_netzlade_soc_ziel_prozent` stammt nur aus dem Entwurf und wird vom
aktuellen Code nicht gelesen.

## Energy-Pilot-Vorschläge

Im EP-Modus liest ein Speicher diese Vorschläge:

```text
sensor.ep_<prefix>_freigabe_vorschlag
sensor.ep_<prefix>_prio_vorschlag
sensor.ep_<prefix>_geschutzte_mindestleistung_w_vorschlag
sensor.ep_<prefix>_entlade_prio_vorschlag
sensor.ep_<prefix>_soc_ziel_prozent_vorschlag
sensor.ep_<prefix>_soc_min_prozent_vorschlag
sensor.ep_<prefix>_lade_max_w_vorschlag
sensor.ep_<prefix>_entlade_max_w_vorschlag
sensor.ep_<prefix>_betriebsart_vorschlag
```

Für alle gelten der [Commit-Vertrag und der Fallback auf die HA-Helfer](global.md#energy-pilot-vertrag).
Die technische Freigabe und gültige Messwerte bleiben harte Gates. Die nach einer möglichen
EP-Übernahme wirksamen SoC-Grenzen und WR-Limits werden weiterhin durchgesetzt.

## Global zusätzlich erforderlich

```text
input_number.ems_ac_speicher_entlade_abschlag_w
```

Die einmalige, systemweite Funktion dieses Helfers sowie die Option
`speicher_in_residual_enthalten` stehen in [global.md](global.md#globale-ha-helfer).

## Pflicht für eine funktionsfähige Instanz

- Add-on-Felder `name`, `class: battery` und `soc_entity`
- entweder beide Felder `charge_power_entity` und `discharge_power_entity` oder `power_entity`
- alle [gemeinsamen HA-Helfer](global.md#gemeinsame-ha-helfer)
- alle unterstützten speicherspezifischen Eingangshelfer aus den Tabellen oben
- beide Anforderungshelfer mit negativem Minimum des Leistungssollwerts
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
    capacity_kwh: 12.8
```
