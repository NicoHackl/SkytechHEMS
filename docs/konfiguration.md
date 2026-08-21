# Konfiguration

Das Add-on kennt zwei Konfigurationsebenen: die **Add-on-Optionen** in Home Assistant
(`config.yaml` → `options`, zur Laufzeit unter `/data/options.json`) und die **HA-Helfer**, über
die im Betrieb geregelt wird. Die Helfer stehen in [datenmodell.md](datenmodell.md).

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `SUPERVISOR_TOKEN` | ja (im Add-on) | — | Wird vom Supervisor automatisch injiziert. Keine weitere Authentifizierung nötig. |
| `HA_URL` | nein | `http://supervisor/core` | Nur für die lokale Entwicklung außerhalb des Add-on-Containers. |
| `HA_TOKEN` | nein | Wert von `SUPERVISOR_TOKEN` | Long-Lived Access Token für die lokale Entwicklung. |

Gelesen werden sie ausschließlich in [`app/ha_client.py`](../app/ha_client.py). Eine `.env` gibt es
nicht — im Add-on-Betrieb kommt alles vom Supervisor, lokal werden die beiden Variablen exportiert.

## Add-on-Optionen

| Option | Typ | Default | Beschreibung |
|---|---|---|---|
| `interval_s` | int (1–300) | `30` | Zyklusintervall in Sekunden. |
| `log_level` | `debug` / `info` / `warning` / `error` | `info` | Log-Level des Add-ons. |
| `post_cycle_script` | string? | — | Optional `script.<name>`, wird nach jedem Zyklus ausgelöst. Schlägt der Aufruf fehl, wird nur gewarnt — der Zyklus gilt weiter als erfolgreich. |
| `residual_power_entity` | string? | `sensor.verfugbare_leistung_fur_uberschussverbraucher` | HA-Sensor für den verfügbaren PV-Überschuss in Watt. Wichtigster Eingangswert, Semantik siehe unten. |
| `speicher_in_residual_enthalten` | bool? | `true` | Ob die Lade- und Entladeleistung der HEMS-Speicher im Überschuss-Sensor **enthalten** ist. Siehe unten. |
| `devices` | Liste | vier Beispielgeräte | Alle vom EMS verwalteten Verbraucher. |

Zusätzliches Zyklus-Logging wird zur Laufzeit über den Helfer
`input_boolean.ems_pyems_debug_output` geschaltet — ohne Add-on-Neustart und **unabhängig** vom
`log_level`.

### Semantik des Überschuss-Sensors

Der Pool wird als `residual_w + Σ current_w` der aktuell vom EMS angeforderten Geräte berechnet.
Der Sensor muss deshalb den **Netz-Überschuss liefern, in dem die bereits vom EMS geschalteten
Lasten noch enthalten (also abgezogen) sind**: positiver Wert = Einspeisung, negativer =
Netzbezug. Liefert er stattdessen den bereits um die EMS-Lasten bereinigten freien Überschuss,
kommt es zu Doppelzählung und Aufschwingen.

`unavailable`, `unknown` oder ein Wert ≤ −50 000 W lösen den Hard-Lockout aus: alle Verbraucher
werden abgeschaltet. Der Lockout prüft bewusst den **Rohwert** — er ist eine
Sensor-Plausibilitätsprüfung, keine Regelgröße, und eine Bereinigung würde einen defekten Sensor
kaschieren.

### `speicher_in_residual_enthalten`

Ein AC-gekoppelter Speicher hängt mit eigenem Wechselrichter am Hausnetz; seine Lade- und
Entladeleistung erscheint am Netzübergabepunkt und damit im Überschuss-Sensor. Genau daraus
entsteht die Hauptgefahr: entlädt der Speicher mit 3 kW, steigt der Sensorwert um 3 kW, das HEMS
liest das als Überschuss und schaltet zu — der Netzbezug steigt, der Speicher entlädt mehr.

- `true` (Default) → `residual_bereinigt_w = residual_w − Σ gemessene Entladung`
- `false` → der Sensor rechnet den Speicher bereits heraus, es wird nichts abgezogen

**Vor der Inbetriebnahme prüfen** — ein Fehler hier *ist* die Aufschaukelung. Prüfrezept: HEMS
deaktivieren, den Speicher von Hand auf 1 kW Entladung zwingen, beobachten ob der Sensor um 1 kW
steigt. Steigt er → `true`.

> Speicher, die **nicht** vom HEMS geregelt werden und sich selbst auf Eigenverbrauch fahren,
> sind davon nicht betroffen: ihre Leistung steckt schon im Sensor, und weil sie kein HEMS-Gerät
> sind, wird sie auch nicht abgezogen. Wer sie als `battery` einträgt, zieht sie zweimal ab.

### Geräteliste (`devices`)

| Feld | Pflicht | Beschreibung |
|---|---|---|
| `name` | ja | Technischer Bezeichner und zugleich Entitätspräfix. Nur Kleinbuchstaben, Ziffern, Unterstriche. Beispiel: `heizstab` → `input_boolean.ems_heizstab_freigabe`. |
| `label` | nein | Anzeigename in der Oberfläche, darf Umlaute und Leerzeichen enthalten. Ohne Einfluss auf Entitätsnamen. |
| `class` | ja | `controllable` (stufenlos regelbar), `binary` (AN/AUS) oder `battery` (AC-Speicher). |
| `actual_power_entity` | ja bei `controllable` | HA-Sensor mit der Ist-Leistung in Watt. |
| `switch_entity` | ja bei `binary` | Realer Schalter des Geräts; daraus werden `actual_on` und die Schaltdauer gelesen. |
| `entity_prefix` | nein | Überschreibt den Entitätspräfix, wenn die Helfer anders heißen als `name`. |
| `allowed_modes` | nein (Default `manuell`) | Kommagetrennte globale Regelmodi, in denen das Gerät mitwirkt: `manuell`, `nur_heizen`, `nur_laden`. Ein Alt-Wert `auto` wird beim Start auf `manuell` abgebildet. |
| `output_unit` | nein (Default `watt`, nur `controllable`) | `watt` → Helfer mit `_w`-Suffix; `ampere` → Helfer mit `_a`-Suffix und Sollwert in ganzen Ampere (abgerundet). Intern rechnet das EMS immer in Watt. |
| `phases` | nein (Default `"1"`, nur `controllable` + `ampere`) | `"1"`, `"3"` oder `"1,3"` für automatische Phasenumschaltung. |
| `phase_switch_delay_s` | nein (Default `300`) | Sperrzeit zwischen zwei Phasenwechseln. Verhindert Oszillation. |
| `voltage_l1_entity` / `_l2_` / `_l3_` | nein | HA-Sensoren für die Phasenspannungen in Volt. Plausibel ist `180 < U < 260`; sonst gilt der Fallback 230 V. |
| `soc_entity` | ja bei `battery` | HA-Sensor mit dem Ladezustand in Prozent. Fehlt er oder liefert er `unavailable`, fällt dieser Speicher aus der Regelung. |
| `charge_power_entity` / `discharge_power_entity` | bei `battery`: beide, oder `power_entity` | Ist-Lade- und Ist-Entladeleistung in Watt, **beide ≥ 0**. |
| `power_entity` | Alternative bei `battery` | Eine signierte Entität für beide Richtungen. |
| `power_sign` | nein (Default `positiv_laden`) | Vorzeichenkonvention von `power_entity`: `positiv_laden` oder `positiv_entladen`. |
| `available_charge_power_entity` / `available_discharge_power_entity` | nein | Momentanes Lade- bzw. Entladelimit des Geräts (Temperatur- oder Zell-Derating). Hat Vorrang vor den konfigurierten Maxima. |
| `capacity_kwh` | nein | Nutzbare Kapazität in kWh. Nur für die Anzeige (`energie_kwh`, kapazitätsgewichteter SoC-Schnitt) — sie ändert sich nie im Betrieb und liegt deshalb hier statt in einem Helfer. |

Beispiel:

```yaml
devices:
  - name: heizstab
    label: "Heizstab"
    class: controllable
    actual_power_entity: sensor.elwa_modbus_istleistung
    allowed_modes: "manuell,nur_heizen"

  - name: wallbox_1
    label: "Wallbox"
    class: controllable
    actual_power_entity: sensor.wallbox_1_istleistung
    entity_prefix: wallbox
    allowed_modes: "manuell,nur_laden"
    output_unit: "ampere"
    phases: "1,3"
    phase_switch_delay_s: 300

  - name: heizlufter_1
    label: "Heizlüfter 1"
    class: binary
    switch_entity: switch.heizlufter
    allowed_modes: "manuell,nur_heizen"

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

> **Präfix bewusst nicht `speicher`.** Der Namensraum `ems_speicher_*` ist in dieser Anlage
> bereits von einer eigenen HA-Automation für den vorhandenen E3DC belegt.
>
> **`allowed_modes` beim Speicher:** damit er in allen Betriebsmodi mitläuft, alle
> Nicht-`aus`-Modi auflisten. Ein Alt-Wert `auto` wird beim Start auf `manuell` abgebildet.

Geräte werden ausschließlich hier verwaltet — für ein neues Gerät genügen ein Eintrag, die
zugehörigen HA-Helfer und ein Add-on-Neustart. Ungültige Einträge (fehlendes `name`, unbekannte
`class`) werden mit einer Fehlermeldung im Log übersprungen; die übrigen Geräte bleiben aktiv.

> Da das Schema eine Objektliste enthält, zeigt Home Assistant die Optionen als YAML-Editor an.
> Die Feldbeschreibungen aus `translations/*.yaml` erscheinen in diesem Modus nicht — maßgeblich
> ist diese Datei.

## Konfigurationsdateien

| Datei | Zweck | Eingecheckt |
|---|---|---|
| `config.yaml` | Add-on-Manifest: Version, Optionen, Schema, Ingress | ja |
| `repository.yaml` | Manifest des Custom-Repositories | ja |
| `translations/de.yaml`, `translations/en.yaml` | Feldbeschreibungen der Optionen | ja |
| `/data/options.json` | Vom Supervisor erzeugte Laufzeitkonfiguration | nein (nicht im Repo) |

## Secrets

- Zugangsdaten kommen ausschließlich aus Umgebungsvariablen — nie aus dem Code, nie aus einer
  eingecheckten Datei.
- Der Token taucht nie in Logs, Fehlermeldungen oder Commit-Messages auf.
- Fehlt der Token, schlägt der erste HA-Aufruf mit einer Fehlermeldung im Log fehl und der Zyklus
  wird als fehlerhaft markiert; geschaltet wird nichts.
- Weitergehende Regeln: [sicherheit-datenschutz.md](sicherheit-datenschutz.md).
