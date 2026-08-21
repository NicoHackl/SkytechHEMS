# Konfiguration

Das Add-on kennt zwei Konfigurationsebenen: die **Add-on-Optionen** in Home Assistant
(`config.yaml` → `options`, zur Laufzeit unter `/data/options.json`) und die **HA-Helfer**, über
die im Betrieb geregelt wird.

Die Add-on-Optionen lassen sich an zwei Stellen bearbeiten — der nativen Add-on-Seite von Home
Assistant und dem Bereich **Konfiguration** im Ingress-Panel. Beide schreiben über die
Supervisor-API **dieselbe** Quelle; es gibt keine zweite Konfigurationsdatei und kein direktes
Schreiben nach `/data/options.json`. Ein Revisions-Hash über die rohen gespeicherten Optionen
erkennt eine zwischenzeitliche Änderung an der jeweils anderen Stelle und verhindert, dass sie
überschrieben wird. Eine gespeicherte Änderung wird erst nach einem **Neustart** des Add-ons
wirksam; die Endpunkte dazu stehen in [api-referenz.md](api-referenz.md#konfigurations-endpunkte). Die vollständigen Felder, Pflichtangaben, Entitäten und Fallbacks
stehen in der Referenz [Geräteklassen](device_classes/global.md).

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `SUPERVISOR_TOKEN` | ja (im Add-on) | — | Wird vom Supervisor automatisch injiziert. Keine weitere Authentifizierung nötig. |
| `HA_URL` | nein | `http://supervisor/core` | Nur für die lokale Entwicklung außerhalb des Add-on-Containers. |
| `HA_TOKEN` | nein | Wert von `SUPERVISOR_TOKEN` | Long-Lived Access Token für die lokale Entwicklung. |
| `SUPERVISOR_URL` | nein | `http://supervisor` | Nur für Tests und lokale Entwicklung. |
| `HEMS_OPTIONS_PATH` | nein | `/data/options.json` | Nur für die lokale Entwicklung: von wo die Add-on-Optionen **gelesen** werden. |

Gelesen werden sie in [`app/ha_client.py`](../app/ha_client.py) (HA-Zugriff),
[`app/supervisor_client.py`](../app/supervisor_client.py) (`SUPERVISOR_TOKEN`, `SUPERVISOR_URL`) und
[`app/main.py`](../app/main.py) (`HEMS_OPTIONS_PATH`). Eine `.env` gibt es nicht — im Add-on-Betrieb
kommt alles vom Supervisor, lokal werden die Variablen exportiert.

Fehlt `SUPERVISOR_TOKEN`, läuft das Add-on außerhalb von Home Assistant: die Konfigurationsseite
schaltet dann sichtbar in einen **Nur-Lese-Modus**. Es wird niemals vorgetäuscht, ein
Supervisor-Schreibvorgang sei erfolgreich gewesen.

## Add-on-Optionen

Die kanonische Tabelle aller globalen Optionen und Laufzeit-Defaults steht unter
[Globale Add-on-Optionen](device_classes/global.md#globale-add-on-optionen). Die
klassenspezifischen Felder stehen hier:

| Geräteklasse | Referenz |
|---|---|
| `controllable` | [Regelbares Gerät](device_classes/controllable.md#felder-in-der-add-on-konfiguration) |
| `binary` | [Binäres Gerät](device_classes/binary.md#felder-in-der-add-on-konfiguration) |
| `battery` | [AC-Speicher](device_classes/battery.md#felder-in-der-add-on-konfiguration) |

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

### `available_modes`

Legt fest, welche der drei normalen Regelmodi (`manuell`, `nur_heizen`, `nur_laden`) in dieser
Anlage überhaupt verwendet werden; Default sind alle drei. `devices[].allowed_modes` muss eine
Teilmenge davon sein. Die Sondermodi `auto` (Energy Pilot) und `aus` gehören nicht in die Liste und
bleiben immer unterstützt.

Meldet `input_select.ems_regelmodus` einen normalen Modus, der hier nicht aktiviert ist, bleibt der
Zyklus sicher inaktiv — Einzelheiten in
[Normale Modi und Sondermodi](device_classes/global.md#normale-modi-und-sondermodi).

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

Die Felder `name`, `class`, `label`, `entity_prefix` und `allowed_modes` gelten für jede Klasse und
sind unter [Gemeinsame Felder in `devices[]`](device_classes/global.md#gemeinsame-felder-in-devices)
beschrieben. Vollständige Beispiele stehen auf den drei Klassenseiten.

Geräte werden ausschließlich hier verwaltet — für ein neues Gerät genügen ein Eintrag, die
zugehörigen HA-Helfer und ein Add-on-Neustart.

Ungültige Einträge werden beim Start **nicht instanziiert**, verschwinden aber nicht mehr im Log:
sie erscheinen als `inactive_devices` in `/api/status`, mit Geräte-ID, Klasse, Label und den
konkreten Feldfehlern. Die übrigen Geräte bleiben aktiv. Welche Felder je Klasse Pflicht sind,
steht auf den drei Klassenseiten; geprüft wird in
[`app/configuration.py`](../app/configuration.py).

> Das Schema in `config.yaml` markiert die klassenspezifischen Felder bewusst als **optional**.
> Eine gemischte Objektliste kann keine bedingten Pflichtfelder ausdrücken — eine Pflichtmarkierung
> für `switch_entity` machte jedes `controllable`-Gerät ungültig. Autoritativ ist deshalb die
> Anwendung, und sie liefert Oberfläche und Regelung dieselbe Antwort.

> Da das Schema eine Objektliste enthält, zeigt Home Assistant die Optionen als YAML-Editor an.
> Die Feldbeschreibungen aus `translations/*.yaml` erscheinen in diesem Modus nicht — maßgeblich
> ist die Referenz unter [`device_classes/`](device_classes/global.md).

## Konfigurationsdateien

| Datei | Zweck | Eingecheckt |
|---|---|---|
| `config.yaml` | Add-on-Manifest: Version, Optionen, Schema, Ingress | ja |
| `repository.yaml` | Manifest des Custom-Repositories | ja |
| `translations/de.yaml`, `translations/en.yaml` | Feldbeschreibungen der Optionen | ja |
| `/data/options.json` | Vom Supervisor erzeugte Laufzeitkonfiguration; wird nur **gelesen** | nein (nicht im Repo) |

## Secrets

- Zugangsdaten kommen ausschließlich aus Umgebungsvariablen — nie aus dem Code, nie aus einer
  eingecheckten Datei.
- Der Token taucht nie in Logs, Fehlermeldungen oder Commit-Messages auf.
- Fehlt der Token, schlägt der erste HA-Aufruf mit einer Fehlermeldung im Log fehl und der Zyklus
  wird als fehlerhaft markiert; geschaltet wird nichts.
- Weitergehende Regeln: [sicherheit-datenschutz.md](sicherheit-datenschutz.md).
