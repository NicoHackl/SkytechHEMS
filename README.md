# Skytech HEMS

PV-Überschuss-Energiemanagementsystem als Home-Assistant-Add-on. Verteilt den PV-Überschuss zyklisch und nach Priorität auf regelbare Verbraucher (z. B. Heizstab, Wallbox) und binäre Verbraucher (z. B. Heizlüfter), unter Berücksichtigung von Zeitschutz, Hysterese, Rampenbegrenzung und Notabschaltung.

Die Konfiguration und Bedienung erfolgt vollständig über Home-Assistant-Helfer-Entitäten (`input_boolean`, `input_select`, `input_number`) – das Add-on bringt keine eigene Persistenz mit, sondern liest und schreibt ausschließlich in den HA-State.

---

## Inhalt

- [Funktionsumfang](#funktionsumfang)
- [Architektur](#architektur)
- [Installation](#installation)
- [Konfiguration des Add-ons](#konfiguration-des-add-ons)
- [Regelablauf eines Zyklus](#regelablauf-eines-zyklus)
- [HA-Helper-Namenskonvention](#ha-helper-namenskonvention)
  - [Globale Helfer](#globale-helfer)
  - [Pro Gerät: gemeinsame Helfer](#pro-gerät-gemeinsame-helfer)
  - [Regelbare Geräte (`ControllableDevice`)](#regelbare-geräte-controllabledevice)
  - [Binäre Geräte (`BinaryDevice`)](#binäre-geräte-binarydevice)
  - [Externe Entitäten](#externe-entitäten)
- [Geräte hinzufügen oder entfernen](#geräte-hinzufügen-oder-entfernen)
- [Web-UI](#web-ui)
- [REST-Endpunkte](#rest-endpunkte)
- [Lokale Entwicklung](#lokale-entwicklung)
- [Repository-Layout](#repository-layout)

---

## Funktionsumfang

- **Zyklische Regelung** des PV-Überschusses in einstellbarem Intervall (1 – 300 s).
- **Pool-basierte Verteilung**: aus dem aktuellen Überschuss plus aktuell genutzter Leistung wird ein „Pool" berechnet, der nach Priorität auf die Geräte verteilt wird.
- **Prioritätskaskade**: niedriger priorisierte Verbraucher werden zuerst abgeschaltet; höher priorisierte werden bei Bedarf zwangsweise gehalten.
- **Globale und gerätespezifische Freigabe / Modi** (`auto`, `nur_heizen`, `nur_laden`, `aus`).
- **Hysterese** für binäre Verbraucher über `einschaltreserve_w` (global und pro Gerät).
- **Zeitschutz** für binäre Verbraucher: Mindestlaufzeit, Mindestauszeit, Abschaltverzögerung. Die Mindestlaufzeit schützt das Gerät auch bei Notabschaltung.
- **One-Change-Limit**: pro Zyklus wird höchstens ein binäres Gerät geschaltet (außer bei Notabschaltung).
- **Rampenbegrenzung** für regelbare Geräte: Hoch-/Runter-Regelzeit, max. Änderung pro Schritt, Deadband.
- **Schutzleistung** pro regelbarem Gerät (`geschützte Mindestleistung + reserve_w + globaler Puffer`), die vor der binären Pool-Verteilung reserviert wird.
- **Hard-Lockout** bei ungültigem oder stark negativem Überschuss-Sensor (`≤ −50 000 W`): alle Verbraucher werden abgeschaltet.
- **Sofortabschaltung** binärer Verbraucher, sobald das Netzdefizit größer ist als das, was regelbare Geräte abregeln können.
- **Ampere-Ausgabe** für regelbare Geräte (z. B. Wallbox): Das EMS regelt intern in Watt; bei `output_unit=ampere` werden Grenzwerte in Ampere (`_a`-Suffix) konfiguriert und der Sollwert vor dem Schreiben in ganzzahlige Ampere umgerechnet (immer abgerundet, optionaler Live-Spannungssensor).
- **Automatische Phasenumschaltung**: Wallboxen können mit `phases: "1,3"` konfiguriert werden. Das EMS wählt dann jede Runde die höchst mögliche Phasenanzahl, für die der PV-Pool das Minimum erreicht, und schreibt die Phasenauswahl in eine separate HA-Entität (`anzahl_phase`). Eine konfigurierbare Hysterese-Sperrzeit (`phase_switch_delay_s`, Standard 300 s) verhindert schnelles Hin- und Herschalten.
- **Config-driven Devices**: Geräte werden ausschließlich in den Add-on-Optionen (`config.yaml`) definiert – kein Python-Code muss für neue Geräte angefasst werden.
- **Optionales Post-Cycle-Skript**: nach jedem Zyklus kann ein beliebiges HA-Script aufgerufen werden (z. B. zur Benachrichtigung oder zum Schreiben in einen externen Speicher).
- **Web-UI als HA-Ingress-Panel** mit zwei Tabs (Status / Steuerung) zum Beobachten und Verändern aller relevanten Helfer-Entitäten.

## Architektur

```
app/
├── main.py             aiohttp-Webserver + asynchroner EMS-Scheduler
├── ha_client.py        REST-Client für HA (/api/states, /api/services/*)
├── ems/
│   ├── controller.py   EMSController – orchestriert einen Zyklus, Geräte-Registry
│   ├── devices.py      Device / ControllableDevice / BinaryDevice (ABCs + Implementierungen)
│   └── state.py        StateProxy + safe_float / parse_ts Helfer
└── templates/index.html  Web-UI (Status- und Steuerungs-Tab)
```

- **`EMSController`** wird einmal beim Start aus den Add-on-Optionen gebaut; die Geräte-Objekte leben über alle Zyklen hinweg – dadurch bleiben interne Timer (z. B. `_off_since_ts`) ohne zusätzliche HA-Helfer erhalten.
- **`Device`** ist die abstrakte Basis. Geräteinstanzen werden in `controller._build_devices()` automatisch aus der Konfigurationsliste `devices` aufgebaut. Ein neuer Gerätetyp braucht nur eine neue Subklasse und einen Eintrag dort – sonst muss nichts angefasst werden.

## Installation

Als Home-Assistant-Add-on über ein Custom-Repository:

1. In HA: **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Repository-URL `https://github.com/nicohackl/SkytechHEMS` eintragen.
3. „Skytech HEMS" installieren und starten.
4. Ingress-Panel „HEMS" in der Seitenleiste öffnen.

Beim Add-on-Start steht der `SUPERVISOR_TOKEN` automatisch zur Verfügung – es ist keine zusätzliche HA-Authentifizierung nötig.

## Konfiguration des Add-ons

In den Add-on-Optionen (YAML-Editor in HA):

### Allgemeine Optionen

| Option              | Typ                                     | Default | Beschreibung                                                       |
|---------------------|-----------------------------------------|---------|--------------------------------------------------------------------|
| `interval_s`        | int (1 – 300)                           | `30`    | Zyklusintervall in Sekunden.                                       |
| `log_level`         | `debug` / `info` / `warning` / `error` | `info`  | Log-Level des Add-ons.                                             |
| `post_cycle_script` | string?                                 | –       | Optional: `script.<name>`, wird nach jedem Zyklus aufgerufen.      |
| `residual_power_entity` | string?                             | `sensor.verfugbare_leistung_fur_uberschussverbraucher` | HA-Sensor für den verfügbaren PV-Überschuss in Watt (wichtigster Eingangswert). Zur Semantik siehe [Externe Entitäten](#externe-entitäten). |

Zusätzliches Debug-Logging zur Regelentscheidung wird über den HA-Helfer `input_boolean.ems_pyems_debug_output` aktiviert (Laufzeit-Schalter, kein Add-on-Neustart nötig).

### Geräteliste (`devices`)

Die `devices`-Liste definiert alle vom EMS verwalteten Verbraucher. Das Add-on baut daraus beim Start automatisch die internen Geräteobjekte und leitet alle Entitätsnamen aus der Namenskonvention ab.

| Feld                  | Pflicht                            | Beschreibung |
|-----------------------|------------------------------------|--------------|
| `name`                | ja                                 | Technischer Bezeichner – wird direkt als Entitätspräfix verwendet. Nur Kleinbuchstaben, Ziffern, Unterstriche. Beispiel: `heizstab` → `input_boolean.ems_heizstab_freigabe` usw. |
| `label`               | nein                               | Anzeigename in der Web-UI (darf Umlaute, Leerzeichen und Sonderzeichen enthalten). Hat keinen Einfluss auf Entitätsnamen. |
| `class`               | ja                                 | `controllable` für stufenlos regelbare Geräte (Heizstab, Wallbox) oder `binary` für AN/AUS-Geräte (Heizlüfter, Pumpe). |
| `actual_power_entity` | ja (nur `controllable`)            | HA-Sensor-Entität für die aktuelle Ist-Leistung in Watt. Beispiel: `sensor.elwa_modbus_istleistung`. |
| `switch_entity`       | ja (nur `binary`)                  | HA-Schalter-Entität des realen Geräts. Das EMS liest daraus `actual_on` und die Schaltdauer. Beispiel: `switch.heizlufter`. |
| `entity_prefix`       | nein                               | Überschreibt den Entitätspräfix wenn er vom `name` abweicht. Nötig wenn die HA-Helfer bereits mit einem anderen Präfix angelegt wurden. Beispiel: `name=wallbox_1`, Helfer heißen `ems_wallbox_*` → `entity_prefix: wallbox`. |
| `allowed_modes`       | nein (Standard: `auto`)            | Kommagetrennte Liste der globalen EMS-Modi, in denen das Gerät aktiv ist. Mögliche Werte: `auto`, `nur_heizen`, `nur_laden`. |
| `output_unit`           | nein (Standard: `watt`, nur `controllable`) | `watt` schreibt Watt in die Anforderungs-Entität; Helfer-Entitäten verwenden `_w`-Suffix. `ampere` konvertiert den Sollwert in ganze Ampere (immer abgerundet); Helfer-Entitäten verwenden `_a`-Suffix. Intern rechnet das EMS immer in Watt. |
| `phases`                | nein (Standard: `"1"`, nur `controllable` + `ampere`) | Kommagetrennte Phasenkonfiguration: `"1"` (einphasig), `"3"` (dreiphasig) oder `"1,3"` (automatische Phasenumschaltung). Bei `"1,3"` wählt das EMS die höchste mögliche Phasenanzahl, für die `floor(pool ÷ (phases × U)) ≥ min_technisch_a` gilt. Umrechnungsformel: `I = floor(P / (phases × U_phase))`. |
| `phase_switch_delay_s`  | nein (Standard: `300`, nur `controllable` + `ampere` + `phases="1,3"`) | Hysterese-Sperrzeit in Sekunden zwischen zwei Phasenwechseln. Verhindert Oszillation bei Leistungsschwankungen. Empfehlung: 300 s. |
| `voltage_l1_entity`     | nein (nur `controllable` + `ampere`) | Optionaler HA-Sensor für die Phasenspannung L1-N in Volt (z. B. `sensor.wallbox_spannung_l1`). Plausibilitätsbereich 180 – 260 V; außerhalb oder bei fehlendem Wert wird 230 V verwendet. Bei 1-phasigem Betrieb wird ausschließlich dieser Sensor herangezogen. |
| `voltage_l2_entity`     | nein (nur `controllable` + `ampere`) | Optionaler HA-Sensor für die Phasenspannung L2-N. Fallback 230 V. Nur bei 3-phasigem Betrieb relevant. |
| `voltage_l3_entity`     | nein (nur `controllable` + `ampere`) | Optionaler HA-Sensor für die Phasenspannung L3-N. Fallback 230 V. Nur bei 3-phasigem Betrieb relevant. |

**Beispiel-Konfiguration:**

```yaml
devices:
  - name: heizstab
    label: "Heizstab"
    class: controllable
    actual_power_entity: sensor.elwa_modbus_istleistung
    allowed_modes: "auto,nur_heizen"

  - name: wallbox_1
    label: "Wallbox"
    class: controllable
    actual_power_entity: sensor.wallbox_1_istleistung
    entity_prefix: wallbox
    allowed_modes: "auto,nur_laden"
    output_unit: "ampere"
    phases: "1,3"               # automatische Phasenumschaltung
    phase_switch_delay_s: 300   # 5 min Hysterese zwischen Phasenwechseln
    voltage_l1_entity: ""       # leer → Fallback 230 V
    voltage_l2_entity: ""
    voltage_l3_entity: ""

  - name: heizlufter_1
    label: "Heizlüfter 1"
    class: binary
    switch_entity: switch.heizlufter
    allowed_modes: "auto,nur_heizen"
```

> **Hinweis:** Da das Schema eine Liste von Objekten enthält, zeigt HA die gesamte Konfiguration als YAML-Editor an – Feldbeschreibungen aus `translations/*.yaml` werden in diesem Modus nicht angezeigt. Diese README ist die maßgebliche Dokumentation aller Felder.

## Regelablauf eines Zyklus

Pro Zyklus führt `EMSController.run_cycle()` der Reihe nach aus:

1. **Globale Eingaben** aus HA lesen (Freigabe, Modus, Puffer, Einschaltreserve, Überschuss-Sensor, Debug-Schalter).
2. **Eligibility** je Gerät bestimmen (globaler Modus muss in `allowed_modes` liegen und `freigabe`/`modus` des Geräts müssen aktiv sein).
3. **Pool** berechnen: `residual_w + Σ current_w` der Geräte, oder `0` bei Lockout/EMS aus.
4. **Phasenauswahl** für regelbare Geräte mit `output_unit=ampere` und `phases="1,3"`: Das EMS wählt die höchste Phasenanzahl, für die `floor(pool_w / (phases × U)) ≥ min_technisch_a` gilt. Bei einem Phasenwechsel wird `anzahl_phase` in HA geschrieben und der Ramp-Timer zurückgesetzt. Die Hysterese `phase_switch_delay_s` verhindert Oszillation.
5. **Defizit** ermitteln und prüfen, ob die regelbaren Geräte das Defizit allein abregeln können (`binary_immediate_off`).
6. **Pool nach Priorität verteilen**:
   - Regelbare Geräte reservieren ihre Schutzleistung.
   - Binäre Geräte ermitteln ihre Hysterese-basierte Wunschvorgabe.
7. **Kandidat** der binären Geräte unter Berücksichtigung von Mindestlaufzeit, Abschaltverzögerung und Mindestauszeit bestimmen. Die Mindestlaufzeit gilt auch bei `binary_immediate_off`.
8. **Prioritätskaskade** anwenden (Demotion / Promotion) und **One-Change-Limit** durchsetzen.
9. **Allocation regelbarer Geräte** aus dem verbleibenden Pool.
10. **Rampenbegrenzung** der regelbaren Sollwerte (oder sofortiger Run-down bei Defizit).
11. **Write-Ops** sammeln: Sollwerte werden bei `output_unit=ampere` von Watt in ganze Ampere umgerechnet (Floor-Rounding), dann gegen die HA-REST-API ausgeführt. Optional Post-Cycle-Skript triggern.

## HA-Helper-Namenskonvention

Alle vom Add-on gelesenen oder geschriebenen Helfer-Entitäten folgen einem festen Schema. Voraussetzung: die Helfer existieren in Home Assistant – das Add-on legt sie nicht selbst an.

> **Grundregel**
>
> ```
> <domain>.ems_<prefix>_<suffix>
> ```
>
> - `<domain>` ist eine der HA-Domains `input_boolean`, `input_select`, `input_number`.
> - `<prefix>` ist entweder leer/spezifisch (global) oder der Geräte-Prefix (gerätebezogen).
> - `<suffix>` benennt den konkreten Parameter (siehe Tabellen unten).

Per Default entspricht `<prefix>` dem `name`-Feld des Geräts in der Konfiguration. Weicht das HA-Namensschema davon ab, kann es über das Feld `entity_prefix` in den Add-on-Optionen überschrieben werden (Beispiel: `name=wallbox_1` → `entity_prefix=wallbox`, damit der Helfer `input_boolean.ems_wallbox_freigabe` und nicht `…ems_wallbox_1_freigabe` heißt).

### Globale Helfer

| Entität                                              | Domain          | Werte / Einheit                              | Pflicht | Funktion                                                                 |
|------------------------------------------------------|-----------------|----------------------------------------------|---------|--------------------------------------------------------------------------|
| `input_boolean.ems_pv_regelung_aktiv`                | `input_boolean` | `on` / `off`                                 | ja      | Globaler EIN/AUS-Schalter für die gesamte EMS-Regelung.                  |
| `input_select.ems_regelmodus`                        | `input_select`  | `auto`, `nur_heizen`, `nur_laden`, `aus`     | ja      | Globaler Regelmodus. Muss in `allowed_modes` jedes Geräts vorkommen.     |
| `input_number.ems_globaler_puffer_w`                 | `input_number`  | Watt                                         | ja      | Zusätzlich reservierte Leistung pro regelbarem Gerät vor binärer Verteilung. |
| `input_number.ems_einschaltreserve_global_w`         | `input_number`  | Watt                                         | ja      | Hysterese-Aufschlag, der für *alle* binären Geräte beim Einschalten gilt. |
| `input_boolean.ems_pyems_debug_output`               | `input_boolean` | `on` / `off`                                 | nein    | Schaltet ausführliches Zyklus-Logging zur Laufzeit an/aus.               |

### Pro Gerät: gemeinsame Helfer

Die folgenden Helfer existieren für *jedes* Gerät (regelbar **und** binär). `<prefix>` ist das `name`-Feld bzw. der überschriebene `entity_prefix`.

| Entität                                       | Domain          | Werte                                                  | Funktion                                                                       |
|-----------------------------------------------|-----------------|--------------------------------------------------------|--------------------------------------------------------------------------------|
| `input_boolean.ems_<prefix>_freigabe`         | `input_boolean` | `on` / `off`                                           | Gerätespezifische Freigabe. Ohne `on` ist das Gerät nicht eligible.            |
| `input_select.ems_<prefix>_modus`             | `input_select`  | mindestens `auto` (weitere Optionen werden ignoriert)  | Nur bei `auto` wirkt das Gerät am EMS mit. Andere Optionen = manuell/aus.      |
| `input_number.ems_<prefix>_prioritat`         | `input_number`  | int (kleiner = höher priorisiert)                      | Sortierreihenfolge bei Pool-Verteilung und Kaskade.                            |

### Regelbare Geräte (`ControllableDevice`)

Für stufenlos regelbare Verbraucher (Heizstab, Wallbox). Zusätzlich zu den gemeinsamen Helfern:

**`output_unit=watt`** – alle Grenzwert-Entitäten verwenden `_w`-Suffix, Werte in Watt:

| Suffix (`input_number.ems_<prefix>_…`)     | Einheit | Funktion                                                                                          |
|--------------------------------------------|---------|---------------------------------------------------------------------------------------------------|
| `min_technisch_w`                          | W       | Untere technische Leistungsgrenze. Sollwerte zwischen `0` und `min_technisch_w` werden auf `0` oder `min_technisch_w` gerastet. |
| `max_technisch_w`                          | W       | Obere technische Leistungsgrenze (Cap für `alloc_w` und Sollwert).                                 |
| `geschutzte_mindestleistung_w`             | W       | Garantiert reservierte Leistung dieses Geräts (Teil von `schutz_w`).                              |
| `reserve_w`                                | W       | Zusätzliche Pufferleistung des Geräts (Teil von `schutz_w`). Immer in Watt, auch bei Ampere-Modus. |
| `hoch_regelzeit_s`                         | s       | Mindestabstand zwischen Hoch-Regelschritten.                                                      |
| `runter_regelzeit_s`                       | s       | Mindestabstand zwischen Runter-Regelschritten (bei Defizit wird sofort heruntergeregelt).         |
| `max_anderung_pro_schritt_w`               | W       | Maximale Änderung des Sollwerts in einem Zyklus.                                                  |
| `min_anderung_pro_schritt_w`               | W       | Deadband – kleinere Änderungen werden nicht geschrieben.                                          |
| `anforderung_leistung_w` **(Ausgabe)**     | W       | Vom EMS geschriebener Sollwert in Watt. Entität endet auf `_w` (Watt-Modus).                      |

**`output_unit=ampere`** – Grenzwert-Entitäten verwenden `_a`-Suffix, Werte in Ampere:

| Suffix (`input_number.ems_<prefix>_…`)     | Einheit | Funktion                                                                                          |
|--------------------------------------------|---------|---------------------------------------------------------------------------------------------------|
| `min_technisch_a`                          | A       | Untere technische Stromstärkengrenze.                                                             |
| `max_technisch_a`                          | A       | Obere technische Stromstärkengrenze.                                                              |
| `geschutzte_mindestleistung_a`             | A       | Garantiert reservierter Mindestladestrom (Teil von `schutz_w` nach Umrechnung).                   |
| `reserve_w`                                | W       | Zusätzliche Pufferleistung in Watt (immer `_w`, auch im Ampere-Modus).                            |
| `hoch_regelzeit_s`                         | s       | Mindestabstand zwischen Hoch-Regelschritten.                                                      |
| `runter_regelzeit_s`                       | s       | Mindestabstand zwischen Runter-Regelschritten (bei Defizit wird sofort heruntergeregelt).         |
| `max_anderung_pro_schritt_a`               | A       | Maximale Änderung der Stromstärke in einem Zyklus.                                                |
| `min_anderung_pro_schritt_a`               | A       | Deadband – kleinere Änderungen werden nicht geschrieben.                                          |
| `min_umschaltzeit_s` *(optional)*          | s       | Mindestwartezeit in Sekunden zwischen zwei Phasenwechseln (Hysterese). Überschreibt den Wert aus `phase_switch_delay_s` in der App-Config. Ist die Entität nicht vorhanden oder `unavailable`, gilt der Config-Wert; fehlt dieser ebenfalls, wird 30 s verwendet. Nur bei `phases="1,3"` relevant. |
| `anforderung_leistung_a` **(Ausgabe)**     | A       | Vom EMS geschriebener Sollwert in ganzen Ampere (abgerundet).                                       |
| `anzahl_phase` **(Ausgabe, `phases="1,3"`)** | 1 oder 3 | Vom EMS gewählte Phasenanzahl. Nur bei `phases="1,3"` vorhanden; wird jedes Mal aktualisiert wenn sich die Phasenauswahl ändert. |

Außerdem benötigt jedes regelbare Gerät einen externen Ist-Leistungs-Sensor (`sensor.…`), der im Config-Feld `actual_power_entity` angegeben wird.

**Beispiel Heizstab** (`name: heizstab`, `output_unit: watt`):

```
input_boolean.ems_heizstab_freigabe
input_select.ems_heizstab_modus
input_number.ems_heizstab_prioritat
input_number.ems_heizstab_min_technisch_w
input_number.ems_heizstab_max_technisch_w
input_number.ems_heizstab_geschutzte_mindestleistung_w
input_number.ems_heizstab_reserve_w
input_number.ems_heizstab_hoch_regelzeit_s
input_number.ems_heizstab_runter_regelzeit_s
input_number.ems_heizstab_max_anderung_pro_schritt_w
input_number.ems_heizstab_min_anderung_pro_schritt_w
input_number.ems_heizstab_anforderung_leistung_w     ← Sollwert-Ausgabe (Watt)
sensor.elwa_modbus_istleistung                       ← Ist-Leistung (extern)
```

**Beispiel Wallbox** (`name: wallbox_1`, `entity_prefix: wallbox`, `output_unit: ampere`, `phases: "1,3"`):

```
input_boolean.ems_wallbox_freigabe
input_select.ems_wallbox_modus
input_number.ems_wallbox_prioritat
input_number.ems_wallbox_min_technisch_a             ← Mindest-Ladestrom in A (z. B. 6)
input_number.ems_wallbox_max_technisch_a             ← Max-Ladestrom in A (z. B. 16)
input_number.ems_wallbox_geschutzte_mindestleistung_a
input_number.ems_wallbox_reserve_w                   ← Reserve immer in Watt
input_number.ems_wallbox_hoch_regelzeit_s
input_number.ems_wallbox_runter_regelzeit_s
input_number.ems_wallbox_max_anderung_pro_schritt_a
input_number.ems_wallbox_min_anderung_pro_schritt_a
input_number.ems_wallbox_min_umschaltzeit_s          ← (optional) Phasenwechsel-Hysterese in s
input_number.ems_wallbox_anforderung_leistung_a      ← Sollwert-Ausgabe (Ampere, z. B. 10)
input_number.ems_wallbox_anzahl_phase                ← Phasenwahl-Ausgabe (1 oder 3)
sensor.wallbox_1_istleistung                         ← Ist-Leistung (extern, in Watt)
sensor.wallbox_spannung_l1                           ← (optional) Spannung L1-N
sensor.wallbox_spannung_l2                           ← (optional) Spannung L2-N
sensor.wallbox_spannung_l3                           ← (optional) Spannung L3-N
```

### Binäre Geräte (`BinaryDevice`)

Für AN/AUS-Verbraucher mit Zeitschutz (z. B. Heizlüfter). Zusätzlich zu den gemeinsamen Helfern:

| Suffix (`input_number.ems_<prefix>_…`)        | Einheit | Funktion                                                                                                 |
|-----------------------------------------------|---------|----------------------------------------------------------------------------------------------------------|
| `leistung_w`                                  | W       | Angenommene Leistung des Geräts im EIN-Zustand (für Pool und Defizit).                                   |
| `einschaltreserve_w`                          | W       | Pro-Gerät-Hysterese (zusätzlich zur globalen Einschaltreserve).                                          |
| `mindestlaufzeit_s`                           | s       | Solange `actual_on=true` und das Gerät jünger als `mindestlaufzeit_s` ist, darf es nicht abschalten – auch nicht bei Notabschaltung (`binary_immediate_off`). |
| `mindestauszeit_s`                            | s       | Solange `actual_on=false` jünger als `mindestauszeit_s` ist, darf das Gerät nicht einschalten.           |
| `abschaltverzogerung_s`                       | s       | Verzögert das Ausschalten: erst nach Ablauf wird der Aus-Befehl freigegeben. Gilt **immer** – auch bei Notabschaltung (`binary_immediate_off`) und unabhängig von der Prioritäts-Kaskade. |

Ausgabe und externer Schalter:

| Entität                                        | Domain          | Funktion                                                                                              |
|-----------------------------------------------|-----------------|-------------------------------------------------------------------------------------------------------|
| `input_boolean.ems_<prefix>_anforderung_an`   | `input_boolean` | Vom EMS geschriebenes Anforderungs-Flag. Eine HA-Automation übersetzt es in das Schalten des realen Geräts. |
| `switch.<…>` (extern)                         | `switch`        | Tatsächlicher Schalter des Geräts; wird im Config-Feld `switch_entity` angegeben und gelesen, um `actual_on` und `_switch_age_s` zu bestimmen. |

**Beispiel Heizlüfter 1** (`name: heizlufter_1`):

```
input_boolean.ems_heizlufter_1_freigabe
input_select.ems_heizlufter_1_modus
input_number.ems_heizlufter_1_prioritat
input_number.ems_heizlufter_1_leistung_w
input_number.ems_heizlufter_1_einschaltreserve_w
input_number.ems_heizlufter_1_mindestlaufzeit_s
input_number.ems_heizlufter_1_mindestauszeit_s
input_number.ems_heizlufter_1_abschaltverzogerung_s
input_boolean.ems_heizlufter_1_anforderung_an       ← Anforderung-Ausgabe
switch.heizlufter                                   ← realer Schalter (extern)
```

### Externe Entitäten

Diese Entitäten werden vom EMS *gelesen*, aber nicht angelegt oder geschrieben:

| Entität                                                       | Funktion                                                                                                                 |
|---------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| Überschuss-Sensor (konfiguriert via `residual_power_entity`, Standard `sensor.verfugbare_leistung_fur_uberschussverbraucher`) | **Pflicht.** Aktueller PV-Überschuss in Watt. `unavailable` / `unknown` oder ≤ −50 000 W löst Hard-Lockout aus. Zur erwarteten Semantik siehe Hinweis unten. |
| `sensor.<gerät>_istleistung` (konfiguriert via `actual_power_entity`) | Ist-Leistung des jeweiligen regelbaren Geräts in Watt.                                                         |
| `switch.<gerät>` (konfiguriert via `switch_entity`)           | Tatsächlicher Schaltzustand des jeweiligen binären Geräts.                                                               |
| `sensor.<…>` (konfiguriert via `voltage_l1_entity` / `voltage_l2_entity` / `voltage_l3_entity`, optional) | Phasenspannungen L1/L2/L3 in Volt für die W↔A-Umrechnung bei Wallboxen o. Ä. (Fallback je 230 V).        |

> **Hinweis zur Semantik des Überschuss-Sensors (wichtig für korrekte Regelung):**
> Der Pool wird als `residual_w + Σ current_w` der aktuell vom EMS geschalteten
> Geräte berechnet (siehe Regelablauf). Der Sensor muss daher den **Netz-Überschuss
> liefern, in dem die bereits vom EMS geschalteten Lasten noch enthalten (also
> abgezogen) sind** – ein positiver Wert bedeutet Einspeisung, ein negativer
> Netzbezug. Liefert der Sensor stattdessen bereits den um die EMS-Lasten
> *bereinigten* freien Überschuss, käme es zu Doppelzählung und Aufschwingen.
> Der Sensorname ist über die Add-on-Option `residual_power_entity` frei
> konfigurierbar; der Standardname ist ASCII-slugifiziert, da Home Assistant
> Umlaute umsetzt (ü→u, ö→o, ä→a, ß→ss).

## Geräte hinzufügen oder entfernen

Geräte werden ausschließlich über die Add-on-Optionen verwaltet – kein Python-Code muss angefasst werden:

1. In den Add-on-Optionen einen neuen Eintrag in der `devices`-Liste hinzufügen (oder entfernen).
2. Die in den Tabellen oben gelisteten HA-Helfer für den gewählten `name` / `entity_prefix` in Home Assistant anlegen.
3. Add-on neu starten.

Das Add-on leitet beim Start alle Entitätsnamen automatisch aus dem `name`-Feld und der Namenskonvention ab. Ungültige Einträge (fehlendes `name`, unbekannte `class`, leere Pflichtfelder) werden mit einer Fehlermeldung im Log übersprungen – der Rest der Geräte bleibt aktiv.

Für einen komplett neuen Gerätetyp (jenseits von `controllable` und `binary`): eine neue Klasse von `Device` ableiten (`app/ems/devices.py`) und in `_build_devices()` registrieren.

## Web-UI

Erreichbar über das Ingress-Panel **HEMS** in der HA-Seitenleiste (Port `8099`). Zwei Tabs:

- **Status** – Live-Anzeige von EMS-Modus, Überschuss, Pool, Defizit, Notabschaltung und je Gerät:
  - *Regelbare Geräte*: Eligibility, Ist-Leistung, aktueller Sollwert, Allokation, Schutzleistung. Bei `output_unit=ampere` werden Anforderung und Sollwert in Ampere (+ Watt in Klammern) angezeigt sowie die verwendete Phasenspannung.
  - *Binäre Geräte*: `actual_on / desired_on / candidate_on / final_on` sowie Timing-Status (verbleibende Mindestlaufzeit oder Mindestauszeit mit Fortschrittsanzeige).
  - Aktualisiert alle 5 s.
- **Steuerung** – aufklappbare Karten pro Gerät (und „Global"), die alle relevanten Helfer-Entitäten als Toggle / Number / Select direkt editierbar machen (Schreiben über `POST /api/set`). Das Steuerschema wird dynamisch aus der aktuellen Gerätekonfiguration geladen.

## REST-Endpunkte

| Methode | Pfad                         | Zweck                                                                                |
|---------|------------------------------|--------------------------------------------------------------------------------------|
| GET     | `/`                          | Web-UI (Single-Page).                                                                |
| GET     | `/api/status`                | Letzter Zyklus-Snapshot (Status pro Gerät, Pool, Defizit, Zyklenzähler, Fehler).     |
| GET     | `/api/controls`              | Alle `input_boolean.ems_*`, `input_select.ems_*`, `input_number.ems_*` Entitäten.    |
| GET     | `/api/device_controls_schema`| Steuerschema (Gruppen + Entitäten) für den Steuerungs-Tab, abgeleitet aus der aktuellen Gerätekonfiguration. |
| POST    | `/api/set`                   | Body `{"entity_id": "...", "value": ...}` – setzt einen Helfer (Toggle/Set/Select).  |

## Lokale Entwicklung

Außerhalb von Home Assistant kann das Add-on lokal gegen eine bestehende HA-Instanz laufen:

```bash
export HA_URL=http://homeassistant.local:8123
export HA_TOKEN=<long-lived-access-token>

cd app
pip install -r requirements.txt
python main.py
```

Web-UI dann unter `http://localhost:8099`.

Build des Add-on-Containers:

```bash
docker build -t skytech-hems .
docker run --rm -p 8099:8099 \
  -e HA_URL=http://homeassistant.local:8123 \
  -e HA_TOKEN=<token> \
  skytech-hems
```

## Repository-Layout

```
.
├── Dockerfile                 Add-on-Image (Python 3.11 Alpine, aiohttp)
├── config.yaml                Add-on-Manifest (Version, Optionen, Ingress)
├── repository.yaml            Custom-Repository-Manifest
├── translations/
│   ├── de.yaml                Deutsche Feldbeschreibungen (HA Add-on Config)
│   └── en.yaml                Englische Feldbeschreibungen (HA Add-on Config)
├── .github/workflows/
│   └── bump-version.yaml      Patch-Version-Bump bei Push auf main
└── app/
    ├── main.py                Entry-Point: Scheduler + Webserver + API-Routen
    ├── ha_client.py           HA-REST-Client
    ├── requirements.txt
    ├── ems/
    │   ├── __init__.py
    │   ├── controller.py      EMSController + config-driven Geräte-Registry
    │   ├── devices.py         Device / ControllableDevice / BinaryDevice
    │   └── state.py           StateProxy, safe_float, parse_ts
    └── templates/
        └── index.html         Web-UI (Status- und Steuerungs-Tab)
```
