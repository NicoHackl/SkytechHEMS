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

- **Zyklische Regelung** des PV-Überschusses in einstellbarem Intervall (5 – 300 s).
- **Pool-basierte Verteilung**: aus dem aktuellen Überschuss plus aktuell genutzter Leistung wird ein „Pool" berechnet, der nach Priorität auf die Geräte verteilt wird.
- **Prioritätskaskade**: niedriger priorisierte Verbraucher werden zuerst abgeschaltet; höher priorisierte werden bei Bedarf zwangsweise gehalten.
- **Globale und gerätespezifische Freigabe / Modi** (`auto`, `nur_heizen`, `nur_laden`, `aus`).
- **Hysterese** für binäre Verbraucher über `einschaltreserve_w` (global und pro Gerät).
- **Zeitschutz** für binäre Verbraucher: Mindestlaufzeit, Mindestauszeit, Abschaltverzögerung.
- **One-Change-Limit**: pro Zyklus wird höchstens ein binäres Gerät geschaltet (außer bei Notabschaltung).
- **Rampenbegrenzung** für regelbare Geräte: Hoch-/Runter-Regelzeit, max. Änderung pro Schritt, Deadband.
- **Schutzleistung** pro regelbarem Gerät (`geschützte Mindestleistung + reserve_w + globaler Puffer`), die vor der binären Pool-Verteilung reserviert wird.
- **Hard-Lockout** bei ungültigem oder stark negativem Überschuss-Sensor (`≤ −50 000 W`): alle Verbraucher werden abgeschaltet.
- **Sofortabschaltung** binärer Verbraucher, sobald das Netzdefizit größer ist als das, was regelbare Geräte abregeln können.
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

- **`EMSController`** wird einmal beim Start gebaut, die Geräte-Objekte leben über alle Zyklen hinweg – dadurch bleiben interne Timer (z. B. `_off_since_ts`) ohne zusätzliche HA-Helfer erhalten.
- **`Device`** ist die abstrakte Basis. Geräteinstanzen werden in `controller._build_devices()` zentral registriert. Ein neuer Gerätetyp braucht nur eine neue Subklasse und einen Eintrag dort – sonst muss nichts angefasst werden.

## Installation

Als Home-Assistant-Add-on über ein Custom-Repository:

1. In HA: **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Repository-URL `https://github.com/nicohackl/SkytechHEMS` eintragen.
3. „Skytech HEMS" installieren und starten.
4. Ingress-Panel „HEMS" in der Seitenleiste öffnen.

Beim Add-on-Start steht der `SUPERVISOR_TOKEN` automatisch zur Verfügung – es ist keine zusätzliche HA-Authentifizierung nötig.

## Konfiguration des Add-ons

In den Add-on-Optionen (`config.yaml`):

| Option              | Typ           | Default | Beschreibung                                                       |
|---------------------|---------------|---------|--------------------------------------------------------------------|
| `interval_s`        | int (5 – 300) | `30`    | Zyklusintervall in Sekunden.                                       |
| `log_level`         | `debug` / `info` / `warning` / `error` | `info` | Log-Level des Add-ons. |
| `post_cycle_script` | string?       | –       | Optional: `script.<name>`, wird nach jedem Zyklus aufgerufen.      |

Zusätzliches Debug-Logging zur Regelentscheidung wird über den HA-Helfer `input_boolean.ems_pyems_debug_output` aktiviert (Laufzeit-Schalter, kein Add-on-Neustart nötig).

## Regelablauf eines Zyklus

Pro Zyklus führt `EMSController.run_cycle()` der Reihe nach aus:

1. **Globale Eingaben** aus HA lesen (Freigabe, Modus, Puffer, Einschaltreserve, Überschuss-Sensor, Debug-Schalter).
2. **Eligibility** je Gerät bestimmen (globaler Modus muss in `allowed_modes` liegen und `freigabe`/`modus` des Geräts müssen aktiv sein).
3. **Pool** berechnen: `residual_w + Σ current_w` der Geräte, oder `0` bei Lockout/EMS aus.
4. **Defizit** ermitteln und prüfen, ob die regelbaren Geräte das Defizit allein abregeln können (`binary_immediate_off`).
5. **Pool nach Priorität verteilen**:
   - Regelbare Geräte reservieren ihre Schutzleistung.
   - Binäre Geräte ermitteln ihre Hysterese-basierte Wunschvorgabe.
6. **Kandidat** der binären Geräte unter Berücksichtigung von Mindestlaufzeit, Abschaltverzögerung und Mindestauszeit bestimmen.
7. **Prioritätskaskade** anwenden (Demotion / Promotion) und **One-Change-Limit** durchsetzen.
8. **Allocation regelbarer Geräte** aus dem verbleibenden Pool.
9. **Rampenbegrenzung** der regelbaren Sollwerte (oder sofortiger Run-down bei Defizit).
10. **Write-Ops** sammeln und gegen die HA-REST-API ausführen; optional Post-Cycle-Skript triggern.

## HA-Helper-Namenskonvention

Alle vom Add-on gelesenen oder geschriebenen Helfer-Entitäten folgen einem festen Schema. Voraussetzung: die Helfer existieren in Home Assistant – das Add-on legt sie nicht selbst an.

> **Grundregel**
>
> ```
> <domain>.ems_<prefix>_<suffix>
> ```
>
> - `<domain>` ist eine der HA-Domains `input_boolean`, `input_select`, `input_number`.
> - `<prefix>` ist entweder leer/spezifisch (global) oder die Geräte-ID (gerätebezogen).
> - `<suffix>` benennt den konkreten Parameter (siehe Tabellen unten).

Per Default ist `<prefix>` gleich der `id` des Geräts in `controller._build_devices()`. Weicht das HA-Namensschema davon ab, kann es über das Argument `entity_prefix=` der Geräteklasse überschrieben werden (Beispiel: `id="wallbox_1"` → `entity_prefix="wallbox"`, damit der Helfer `input_boolean.ems_wallbox_freigabe` und nicht `…ems_wallbox_1_freigabe` heißt).

### Globale Helfer

| Entität                                              | Domain          | Werte / Einheit                              | Pflicht | Funktion                                                                 |
|------------------------------------------------------|-----------------|----------------------------------------------|---------|--------------------------------------------------------------------------|
| `input_boolean.ems_pv_regelung_aktiv`                | `input_boolean` | `on` / `off`                                 | ja      | Globaler EIN/AUS-Schalter für die gesamte EMS-Regelung.                  |
| `input_select.ems_regelmodus`                        | `input_select`  | `auto`, `nur_heizen`, `nur_laden`, `aus`     | ja      | Globaler Regelmodus. Muss in `allowed_modes` jedes Geräts vorkommen.     |
| `input_number.ems_globaler_puffer_w`                 | `input_number`  | Watt                                         | ja      | Zusätzlich reservierte Leistung pro regelbarem Gerät vor binärer Verteilung. |
| `input_number.ems_einschaltreserve_global_w`         | `input_number`  | Watt                                         | ja      | Hysterese-Aufschlag, der für *alle* binären Geräte beim Einschalten gilt. |
| `input_boolean.ems_pyems_debug_output`               | `input_boolean` | `on` / `off`                                 | nein    | Schaltet ausführliches Zyklus-Logging zur Laufzeit an/aus.               |

### Pro Gerät: gemeinsame Helfer

Die folgenden Helfer existieren für *jedes* Gerät (regelbar **und** binär). `<prefix>` ist die Geräte-ID bzw. der überschriebene Prefix.

| Entität                                       | Domain          | Werte                                                  | Funktion                                                                       |
|-----------------------------------------------|-----------------|--------------------------------------------------------|--------------------------------------------------------------------------------|
| `input_boolean.ems_<prefix>_freigabe`         | `input_boolean` | `on` / `off`                                           | Gerätespezifische Freigabe. Ohne `on` ist das Gerät nicht eligible.            |
| `input_select.ems_<prefix>_modus`             | `input_select`  | mindestens `auto` (weitere Optionen werden ignoriert)  | Nur bei `auto` wirkt das Gerät am EMS mit. Andere Optionen = manuell/aus.      |
| `input_number.ems_<prefix>_prioritat`         | `input_number`  | int (kleiner = höher priorisiert)                      | Sortierreihenfolge bei Pool-Verteilung und Kaskade.                            |

### Regelbare Geräte (`ControllableDevice`)

Für stufenlos regelbare Verbraucher (Heizstab, Wallbox). Zusätzlich zu den gemeinsamen Helfern:

| Suffix (`input_number.ems_<prefix>_…`)    | Einheit | Funktion                                                                                          |
|-------------------------------------------|---------|---------------------------------------------------------------------------------------------------|
| `min_technisch_w`                         | W       | Untere technische Leistungsgrenze. Sollwerte zwischen `0` und `min_technisch_w` werden auf `0` oder `min_technisch_w` gerastet. |
| `max_technisch_w`                         | W       | Obere technische Leistungsgrenze (Cap für `alloc_w` und Sollwert).                                 |
| `geschutzte_mindestleistung_w`            | W       | Garantiert reservierte Leistung dieses Geräts (Teil von `schutz_w`).                              |
| `reserve_w`                               | W       | Zusätzliche Pufferleistung des Geräts (Teil von `schutz_w`).                                       |
| `hoch_regelzeit_s`                        | s       | Mindestabstand zwischen Hoch-Regelschritten.                                                      |
| `runter_regelzeit_s`                      | s       | Mindestabstand zwischen Runter-Regelschritten (bei Defizit wird sofort heruntergeregelt).         |
| `max_anderung_pro_schritt_w`              | W       | Maximale Änderung des Sollwerts in einem Zyklus.                                                  |
| `min_anderung_pro_schritt_w`              | W       | Deadband – kleinere Änderungen werden nicht geschrieben.                                          |
| `anforderung_leistung_w` **(Ausgabe)**    | W       | Vom EMS geschriebener Sollwert. Wird typischerweise von einer separaten Integration (Modbus o. Ä.) ans Gerät übertragen. |

Außerdem benötigt jedes regelbare Gerät einen externen Ist-Leistungs-Sensor (`sensor.…`), der bei der Registrierung in `controller._build_devices()` als `entity_actual_w=` übergeben wird.

**Beispiel Heizstab** (id `heizstab`, kein Prefix-Override):

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
input_number.ems_heizstab_anforderung_leistung_w     ← Sollwert-Ausgabe
sensor.elwa_modbus_istleistung                       ← Ist-Leistung (extern)
```

**Beispiel Wallbox 1** (id `wallbox_1`, `entity_prefix="wallbox"`):

```
input_boolean.ems_wallbox_freigabe
input_select.ems_wallbox_modus
input_number.ems_wallbox_prioritat
input_number.ems_wallbox_min_technisch_w
input_number.ems_wallbox_max_technisch_w
input_number.ems_wallbox_geschutzte_mindestleistung_w
input_number.ems_wallbox_reserve_w
input_number.ems_wallbox_hoch_regelzeit_s
input_number.ems_wallbox_runter_regelzeit_s
input_number.ems_wallbox_max_anderung_pro_schritt_w
input_number.ems_wallbox_anforderung_leistung_w      ← Sollwert-Ausgabe
sensor.wallbox_1_istleistung                         ← Ist-Leistung (extern)
```

### Binäre Geräte (`BinaryDevice`)

Für AN/AUS-Verbraucher mit Zeitschutz (z. B. Heizlüfter). Zusätzlich zu den gemeinsamen Helfern:

| Suffix (`input_number.ems_<prefix>_…`)        | Einheit | Funktion                                                                                                 |
|-----------------------------------------------|---------|----------------------------------------------------------------------------------------------------------|
| `leistung_w`                                  | W       | Angenommene Leistung des Geräts im EIN-Zustand (für Pool und Defizit).                                   |
| `einschaltreserve_w`                          | W       | Pro-Gerät-Hysterese (zusätzlich zur globalen Einschaltreserve).                                          |
| `mindestlaufzeit_s`                           | s       | Solange `actual_on` und das Gerät jünger als `mindestlaufzeit_s` ist, darf es nicht abschalten.          |
| `mindestauszeit_s`                            | s       | Solange `actual_on=off` jünger als `mindestauszeit_s` ist, darf das Gerät nicht einschalten.             |
| `abschaltverzogerung_s`                       | s       | Verzögert das Ausschalten: erst nach Ablauf wird der Aus-Befehl freigegeben.                             |

Ausgabe und externer Schalter:

| Entität                                        | Domain          | Funktion                                                                                              |
|-----------------------------------------------|-----------------|-------------------------------------------------------------------------------------------------------|
| `input_boolean.ems_<prefix>_anforderung_an`   | `input_boolean` | Vom EMS geschriebenes Anforderungs-Flag. Eine HA-Automation o. Ä. übersetzt es in das Schalten des realen Geräts. |
| `switch.<…>` (extern)                         | `switch`        | Tatsächlicher Schalter des Geräts; wird in `controller._build_devices()` als `entity_switch=` registriert und gelesen, um `actual_on` und `_switch_age_s` zu bestimmen. |

**Beispiel Heizlüfter 1** (id `heizlufter_1`):

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
| `sensor.verfugbare_leistung_fur_uberschusverbraucher`         | **Pflicht.** Aktueller PV-Überschuss in Watt (positiv = Einspeisung). `unavailable` / `unknown` oder ≤ −50 000 W löst Hard-Lockout aus. |
| `sensor.<gerät>_istleistung` (z. B. `sensor.elwa_modbus_istleistung`, `sensor.wallbox_1_istleistung`) | Ist-Leistung des jeweiligen regelbaren Geräts.                                                                            |
| `switch.<gerät>` (z. B. `switch.heizlufter`, `switch.heizlufter2`) | Tatsächlicher Schaltzustand des jeweiligen binären Geräts.                                                               |

## Geräte hinzufügen oder entfernen

Die einzige Stelle, die für das Aktivieren / Deaktivieren oder Erweitern um Geräte angefasst werden muss, ist `app/ems/controller.py::_build_devices()`. Schritte:

1. In `_build_devices()` einen neuen `ControllableDevice(…)` oder `BinaryDevice(…)` eintragen (oder vorhandene auskommentierte Einträge aktivieren).
2. Die in den Tabellen oben gelisteten HA-Helfer für den gewählten `id`/`entity_prefix` in Home Assistant anlegen.
3. Add-on neu starten.

Für einen komplett neuen Gerätetyp: eine neue Klasse von `Device` ableiten (`app/ems/devices.py`) und – wenn das Namensschema abweicht – `_device_eligible()` / `update_from_ha()` entsprechend überschreiben.

## Web-UI

Erreichbar über das Ingress-Panel **HEMS** in der HA-Seitenleiste (Port `8099`). Zwei Tabs:

- **Status** – Live-Anzeige von EMS-Modus, Überschuss, Pool, Defizit, Notabschaltung und je Gerät: Eligibility, Ist-/Soll-Leistung, Allokation, Schutzleistung sowie für binäre Geräte `actual_on / desired_on / candidate_on / final_on`. Aktualisiert alle 5 s.
- **Steuerung** – aufklappbare Karten pro Gerät (und „Global"), die alle relevanten Helfer-Entitäten als Toggle / Number / Select direkt editierbar machen (Schreiben über `POST /api/set`).

## REST-Endpunkte

| Methode | Pfad             | Zweck                                                                                |
|---------|------------------|--------------------------------------------------------------------------------------|
| GET     | `/`              | Web-UI (Single-Page).                                                                |
| GET     | `/api/status`    | Letzter Zyklus-Snapshot (Status pro Gerät, Pool, Defizit, Zyklenzähler, Fehler).     |
| GET     | `/api/controls`  | Alle `input_boolean.ems_*`, `input_select.ems_*`, `input_number.ems_*` Entitäten.     |
| POST    | `/api/set`       | Body `{"entity_id": "...", "value": ...}` – setzt einen Helfer (Toggle/Set/Select).  |

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
├── .github/workflows/
│   └── bump-version.yaml      Patch-Version-Bump bei Push auf main
└── app/
    ├── main.py                Entry-Point: Scheduler + Webserver
    ├── ha_client.py           HA-REST-Client
    ├── requirements.txt
    ├── ems/
    │   ├── __init__.py
    │   ├── controller.py      EMSController + Geräte-Registry
    │   ├── devices.py         Device / ControllableDevice / BinaryDevice
    │   └── state.py           StateProxy, safe_float, parse_ts
    └── templates/
        └── index.html         Web-UI (Status- und Steuerungs-Tab)
```
