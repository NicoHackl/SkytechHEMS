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

Das Add-on-Manifest fordert für die drei Schreibaktionen `hassio_role: manager` an. Eine bereits
installierte ältere Version mit `hassio_role: default` kann die Optionen zwar lesen, bekommt beim
Speichern aber `HTTP 403`. In diesem Fall muss das Add-on auf den korrigierten Stand aktualisiert
oder neu gebaut und danach neu gestartet werden; ein bloßes Neuladen der Ingress-Seite ändert die
vom Supervisor vergebene Rolle nicht.

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

### Hausleistungsbilanz für AC-Speicher

Sobald mindestens ein AC-Speicher (`class: battery`) konfiguriert ist, ist
`battery_residual_power_entity` ein Pflichtfeld. Dieser zweite Sensor steuert ausschließlich die
**Entladung** der AC-Speicher. Das Laden und die Verteilung an alle Verbraucher verwenden weiterhin
`residual_power_entity`.

Sein Vorzeichenvertrag ist:

- **negativ:** Netzbezug beziehungsweise Unterdeckung;
- **positiv:** Netzeinspeisung.

In dieser Anlage enthält die Bilanz die Leistung am Netzübergabepunkt und die Leistung der
selbstregelnden E3DC-Batterie. Für die verwendeten E3DC-Entitäten lautet die Template-Formel:

```text
hausleistungsbilanz_w = −e3dc_leistung_netz
                        + e3dc_leistung_batterie_laden
                        − e3dc_leistung_batterie_entladen
```

Dabei liefert `sensor.e3dc_leistung_netz` positiv den Netzbezug. Die vollständige, mit
`availability` abgesicherte Vorlage steht in
[`erweiterungen/zusatz_sensor_für_speicher_null_einspeisung/ueberschusssensor_von_ha.yaml`](../erweiterungen/zusatz_sensor_für_speicher_null_einspeisung/ueberschusssensor_von_ha.yaml).

| Situation bei PV `0 W` | Hausleistungsbilanz | HEMS-Entladeziel vor Abschlag |
|---|---:|---:|
| Hauslast `700 W`, E3DC entlädt `700 W`, AC-Speicher steht | `−700 W` | `700 W` |
| Hauslast `700 W`, AC-Speicher entlädt bereits `700 W` | `0 W` | `700 W` |
| Hauslast `700 W`, AC-Speicher lädt bereits `700 W` | `−1400 W` | `700 W` |

Das HEMS rechnet die eigene AC-Entladung heraus und die gemessenen HEMS-Lasten zurück:

```text
battery_residual_bereinigt_w = battery_residual_w − Σ netz_support_w
entlade_basis_w               = battery_residual_bereinigt_w + Σ gemessene_last_w
hausdefizit_w                 = max(−entlade_basis_w, 0)
```

Danach zieht es `input_number.ems_ac_speicher_entlade_abschlag_w` **einmal systemweit** vom
gesamten Entladeziel ab und verteilt den Rest nach `entlade_prioritat`. Der Abschlag ist kein Wert
pro Speicher.

Der E3DC ist absichtlich kein HEMS-Gerät. Erkennt das HEMS bei einer E3DC-Entladung einen
negativen Bilanzwert, fordert es den AC-Speicher an; der E3DC regelt anschließend selbst zurück.
Die Betriebsannahme dieser Anlage ist eine E3DC-Reaktion in unter zwei Sekunden bei einem
HEMS-Zyklus von drei Sekunden. Reagiert die Anlage langsamer oder oszilliert sie, müssen
`hoch_regelzeit_s` und die Schrittbegrenzung entsprechend größer gewählt werden.

Ein ausgefallener Bilanzsensor löst **keinen** Hard-Lockout der gesamten Anlage aus. Stattdessen
schreibt das HEMS für alle AC-Speicher aktiv `0 W` und `standby`; die Überschussverbraucher laufen
weiter über den primären Überschuss-Sensor. `speicher_in_residual_enthalten` betrifft nur diesen
primären Sensor und hat auf die Hausleistungsbilanz keine Wirkung.

### Formel statt Einzel-Entität

Wer Rohsensoren erst kombinieren muss (wie in der obigen Hausleistungsbilanz-Formel), muss das
nicht zwingend außerhalb des Add-ons als HA-Template pflegen: Der Bereich **Sensoren** im
Ingress-Panel (Tabs „Überschuss" und „Hausbilanz") erlaubt dieselbe Kombination direkt im Add-on
(D-045, [ADR](adr/D-045-formel-basierte-sensorwerte.md)).

Pro Tab werden beliebig viele Zeilen aus Variablenname und HA-Entität gepflegt
(`residual_formula_variables` bzw. `battery_residual_formula_variables`), darunter ein
eingeschränkter Python-Ausdruck (`residual_formula_code` bzw. `battery_residual_formula_code`), der
diese Namen verwendet und der Variable `ueberschuss` bzw. `hausbilanz` einen Wert zuweisen muss. Für
jede Zeile `<name>` stehen im Code sowohl `<name>` (der Wert, oder `None` wenn die Entität gerade
nichts Brauchbares liefert) als auch `<name>_valid` (`True`/`False`) zur Verfügung — eine Formel
sollte `_valid` prüfen, bevor sie mit dem Wert rechnet, z. B. `ueberschuss = pv if pv_valid else 0`.

**Vorrang:** Die Formel wird vor der oben konfigurierten Einzel-Entität ausgewertet. Liefert sie
einen gültigen, endlichen Wert, ersetzt dieser die Entität vollständig — für den gesamten
restlichen Regelzyklus verhält sich das exakt so, als stünde der berechnete Wert im Sensor. Ist der
Code leer, syntaktisch ungültig, verwendet ein nicht erlaubtes Konstrukt oder wirft zur Laufzeit
einen Fehler (z. B. Division durch 0, oder eine ungeprüfte `_valid`-Referenz), greift **unverändert**
der bisherige Pfad über die konfigurierte Entität — ein Zyklus bricht an einer kaputten Formel nie
ab. Welche Quelle gerade wirkt, steht als `residual_source`/`battery_residual_source`
(`"ha"`/`"formula"`/…) in `/api/status` und wird im Sensoren-Formular sowie auf der Status-Seite
angezeigt (Lehre aus D-041: ein zweiter Mechanismus für denselben Wert muss sichtbar sein, welcher
gerade greift).

Der Code läuft über einen selbstgebauten, eingeschränkten Interpreter (`app/formula.py`) — keine
Schleifen, Funktionsdefinitionen, Imports oder Attributzugriffe, siehe
[sicherheit-datenschutz.md](sicherheit-datenschutz.md#nutzerdefinierte-sensor-formeln-d-045). Ein
„Testen"-Knopf im Formular (`POST /api/config/sensors/test`,
[api-referenz.md](api-referenz.md#post-apiconfigsensorstest)) führt den Entwurf live gegen den
aktuellen HA-Schnappschuss aus, bevor gespeichert wird.

Beide Formel-Felder sind vollständig optional und standardmäßig leer — ohne gepflegte Formel ist das
Verhalten jeder Bestandsanlage unverändert.

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

„Beim Start übersprungen“ beschreibt dabei immer den Stand des **laufenden Prozesses**. Ein im
Entwurf korrigiertes Gerät wird erst nach erfolgreichem Speichern und Neustart instanziiert. In der
Geräteliste trägt ein fehlerfreier, noch nicht gespeicherter Eintrag deshalb „Gültiger Entwurf“;
die Statusseite bleibt bis zum Neustart beim tatsächlichen Laufzeitstand.

> Das Schema in `config.yaml` markiert die klassenspezifischen Felder bewusst als **optional**.
> Eine gemischte Objektliste kann keine bedingten Pflichtfelder ausdrücken — eine Pflichtmarkierung
> für `switch_entity` machte jedes `controllable`-Gerät ungültig. Autoritativ ist deshalb die
> Anwendung, und sie liefert Oberfläche und Regelung dieselbe Antwort.

> Da das Schema eine Objektliste enthält, zeigt Home Assistant die Optionen als YAML-Editor an.
> Die Feldbeschreibungen aus `translations/*.yaml` erscheinen in diesem Modus nicht — maßgeblich
> ist die Referenz unter [`device_classes/`](device_classes/global.md).

### Flow Card (`flow_*`)

Anzeigeoptionen der **Skytech Power Flow Card** (D-046). Sie beeinflussen die Regelung nicht:
keiner der Schlüssel steht in `GLOBAL_KEYS_FORCING_SHUTDOWN`, und die drei Gerätefelder sind
zusätzlich vom Abschaltvergleich ausgenommen (D-048) — ein geändertes Icon schaltet keinen
Heizstab ab.

Gepflegt wird das im Panel unter „Flow Card". Die Geräte kennt die Karte bereits aus der
Geräteliste; hier stehen nur die Anlagenwerte, die das HEMS sonst nirgends braucht.

| Schlüssel | Typ | Default | Bedeutung |
|---|---|---|---|
| `flow_publish` | bool | `false` | Veröffentlichung ein/aus. Aus heißt: es wird keine einzige Entität geschrieben |
| `flow_title` | str | `"Leistungsfluss"` | Überschrift der Karte. Leer = keine Überschrift |
| `flow_watt_threshold` | int (0…100000) | `1000` | Ab diesem Betrag zeigt die Karte kW statt W |
| `flow_animation` | bool | `true` | Wandernde Punkte auf den Flusslinien |
| `flow_house_node` | bool | `true` | Hausknoten zeichnen |
| `flow_pv_power_entities` | `[{entity, in_summe}]` | `[]` | PV-Leistungssensoren. Leer = kein Erzeugungsknoten |
| `flow_pv_label` | str | `"Photovoltaik"` | Anzeigename des Erzeugungsknotens |
| `flow_grid_power_entity` | str | `""` | Signierter Netzsensor |
| `flow_grid_power_sign` | list | `"positiv_bezug"` | `positiv_bezug` \| `positiv_einspeisung` |
| `flow_grid_import_entity` | str | `""` | Alternative: getrennter Bezugssensor |
| `flow_grid_export_entity` | str | `""` | Alternative: getrennter Einspeisesensor |
| `flow_grid_label` | str | `"Netz"` | Anzeigename des Netzknotens |
| `flow_house_power_entity` | str | `""` | Hausleistung. Leer = die Karte rechnet die Bilanz |
| `flow_house_label` | str | `"Haus"` | Anzeigename des Hausknotens |
| `flow_battery_label` | str | `""` | Anzeigename des Batterieknotens. Leer und ohne SoC = kein Knoten |
| `flow_battery_soc_entity` | str | `""` | Ladestand in Prozent |

Eine Kapazität wird **nicht** gepflegt. Der Vertrag kennt das Feld
`standard.batterie.capacity_kwh` weiterhin, das HEMS befüllt es aber nicht: es braucht die
Kapazität für nichts. Als Option mit dem Default `null` hatte sie den Add-on-Start blockiert —
die Schemaprüfung des Supervisors sieht einen Schlüssel ohne Wert und verlangt eine Eingabe,
obwohl das Feld als optional markiert ist. **Keine Option unter `options:` darf deshalb `null`
sein**; ein Test wacht darüber.
| `flow_battery_power_entity` | str | `""` | Variante A: ein signierter Sensor |
| `flow_battery_power_sign` | list | `"positiv_laden"` | `positiv_laden` \| `positiv_entladen` |
| `flow_battery_charge_power_entity` | str | `""` | Variante B: Ladesensor |
| `flow_battery_discharge_power_entity` | str | `""` | Variante B: Entladesensor |
| `flow_nav_pv`, `flow_nav_grid`, `flow_nav_house`, `flow_nav_battery`, `flow_nav_rest` | str | `""` | Navigationsziel je Knoten, z. B. `/dashboard-pv/pv` |

Je Gerät kommen drei Felder dazu — sie gehören zum Gerät, damit sie ein Umsortieren der Liste
überleben: `flow_show` (bool, Default `true`), `flow_icon` (mdi-Name, leer = die Karte wählt nach
Geräteklasse) und `flow_color` (CSS-Farbe als Override, leer = Skytech-Akzent). Siehe
[Gemeinsame Felder in `devices[]`](device_classes/global.md#gemeinsame-felder-in-devices).

**Erzeugung: Summe oder Aufschlüsselung.** Eine Anlage hat oft einen Sensor für die
Systemleistung **und** je einen für die einzelnen Strings. Beides zu summieren verdoppelte die
Erzeugung. Je Zeile legt `in_summe` deshalb fest, ob sie zählt (Default `true`, damit
Bestandskonfigurationen sich unverändert verhalten) oder nur als Aufschlüsselung unter dem
Erzeugungsknoten erscheint. Der Publisher trennt beides in `standard.pv_power_entities` und
`standard.pv_detail_entities` — die Karte summiert die zweite Gruppe **nie**.

**Navigationsziele.** Je Knoten lässt sich eine Dashboard-Ansicht hinterlegen, auf die ein Klick
springt: `flow_nav_pv`, `flow_nav_grid`, `flow_nav_house`, `flow_nav_battery`, `flow_nav_rest` und
je Gerät `flow_navigation`. Leer heißt: der Klick öffnet wie bisher den More-Info-Dialog. Im Panel
unter „Flow Card" steht dafür ein Auswahlfeld; die Liste holt das Add-on über
`GET api/flow/dashboards` (D-049).

Zulässig ist ausschließlich ein Pfad innerhalb dieser Instanz — beginnend mit `/`, nicht mit `//`,
ohne Doppelpunkt und ohne Leerraum. Das schließt `http://…` und `javascript:…` aus. Geprüft wird
die **Form**, nicht die Existenz: eine gelöschte Ansicht darf die Konfiguration nicht ungültig
machen.

Wie die drei Anzeigefelder ist auch `flow_navigation` vom Abschaltvergleich ausgenommen (D-048).

**Prüfregeln.** Beim Netz gilt entweder der signierte Sensor **oder** das Paar aus Bezug und
Einspeisung, nie beides; analog bei der Batterie. Wird die Batterie überhaupt gezeichnet (Label
oder SoC gesetzt), ist genau eine Leistungsvariante Pflicht. `flow_publish: true` verlangt
mindestens einen Anlagenwert. Jede PV-Zeile braucht eine Entität, Duplikate sind ein Feldfehler.
`flow_icon` muss mit `mdi:` beginnen. Eine Entität, die bereits als Netzsensor eingetragen ist,
darf nicht zusätzlich als Erzeugung dienen — Netzleistung ist keine Erzeugung, und die Karte
rechnet die Hausbilanz daraus. Leere Werte sind sonst überall gültig — die Karte kommt mit
fehlenden Knoten zurecht.

**Empfehlung `recorder`.** Beide veröffentlichten Entitäten gehören in die Ausschlussliste,
solange keine Historie gewünscht ist: `sensor.skytech_hems_flow_status` ändert sich jeden Zyklus.

```yaml
recorder:
  exclude:
    entities:
      - sensor.skytech_hems_flow_config
      - sensor.skytech_hems_flow_status
```

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
