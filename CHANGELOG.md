# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jedem Merge nach `main` automatisch
um eine Patch-Stelle erhöht (siehe `.github/workflows/bump-version.yaml`).

## [Unreleased]

### Behoben

- **Die Power Flow Card nennt jetzt die Freigabe, die tatsächlich fehlt.** Unter einem gesperrten
  Überschussverbraucher stand bisher immer „Technische Freigabe aus" — auch dann, wenn die
  technische Freigabe an war und nur die Bedienfreigabe fehlte. Sind beide aus, steht „Freigabe
  aus": der Schalter, den man selbst umlegt, wird zuerst genannt. Gilt für regelbare, binäre und
  Speichergeräte gleichermaßen.

### Hinzugefügt

- **Navigationsziele für die Power Flow Card.** Je Knoten — Erzeugung, Netz, Haus, Übriges Haus,
  Batterie und je Gerät — lässt sich eine Dashboard-Ansicht hinterlegen, auf die ein Klick auf der
  Karte springt. Ohne Ziel öffnet der Klick wie bisher den More-Info-Dialog.
  - Im Panel unter „Flow Card" steht dafür ein **Auswahlfeld** mit allen Dashboards und ihren
    Ansichten. Die Liste holt das Add-on über den neuen Endpunkt `GET api/flow/dashboards`.
  - Dafür spricht das Add-on erstmals **WebSocket** mit Home Assistant (D-049): die
    Lovelace-Konfiguration gibt es nur über `lovelace/dashboards/list` und `lovelace/config`,
    einen REST-Endpunkt dafür gibt es nicht. Die Abfrage liegt außerhalb des Regelpfads und wirft
    nie; fällt sie aus, wird das Feld ein Textfeld.
  - Strategie-Dashboards und YAML-Dashboards liefern keine Ansichtsliste. Sie erscheinen mit einer
    Warnung; ein Pfad lässt sich dort von Hand eintragen.
  - Zulässig ist nur ein Pfad innerhalb dieser Instanz. `http://…` und `javascript:…` werden
    abgelehnt — geprüft im Add-on **und** noch einmal in der Karte.

### Behoben

- **Das Add-on ließ sich ohne einen Wert für die Batteriekapazität der Flow Card nicht starten.**
  Die Option hatte als einzige im Manifest den Default `null`; die Schemaprüfung des Supervisors
  sieht darin einen Schlüssel ohne Wert und verlangt eine Eingabe, obwohl das Feld optional ist.
  Die Option entfällt ersatzlos — die Kapazität wurde für nichts gebraucht und war reine Anzeige,
  die die Karte nie gezeichnet hat. Bestehende Konfigurationen dürfen den Schlüssel behalten, er
  wird ignoriert. Ein Test stellt sicher, dass künftig **keine** Option den Wert `null` trägt.

### Hinzugefügt

- **Erzeugung: Systemleistung und einzelne Strings nebeneinander.** Jede Zeile unter „Erzeugung"
  hat neu den Schalter „In Summe". Nur gehakte Zeilen zählen in die Erzeugungsleistung; die
  übrigen erscheinen auf der Karte als Aufschlüsselung unter dem Knoten. Damit lassen sich der
  Sensor für die Anlagenleistung **und** die Sensoren der einzelnen Strings eintragen, ohne dass
  beides zusammengezählt wird — das zeigte sonst die doppelte Erzeugung. Bestehende Zeilen ohne
  den Schalter zählen weiter mit, das Verhalten ändert sich für sie nicht.
- Eine Entität, die bereits als Netzsensor eingetragen ist, wird als Erzeugung nun abgelehnt.
  Netzleistung ist keine Erzeugung; die Karte rechnet daraus die Hausbilanz und kam auf Unsinn.
- **Kartendaten für die Skytech Power Flow Card (D-046, D-047).** Ist die Veröffentlichung
  eingeschaltet, schreibt das Add-on nach jedem Regelzyklus zwei Anzeige-Sensoren nach Home
  Assistant. Aus ihnen baut sich die Lovelace-Karte vollständig selbst auf — im Dashboard genügt
  `type: custom:skytech-power-flow-card`, es wird dort keine einzige Entität verdrahtet. Ein im
  HEMS neu angelegtes Gerät erscheint innerhalb eines Zyklus auf der Karte, ein umbenanntes
  behält seine Position.
  - `sensor.skytech_hems_flow_config` trägt Layout, Anlagenwerte und die Geräteliste als reine
    **Verweise** auf HA-Entitäten. Die Karte löst sie selbst auf und aktualisiert dadurch im Takt
    von Home Assistant statt im Regelintervall. Geschrieben wird nur bei geänderter Revision oder
    wenn die Entität nach einem HA-Neustart fehlt.
  - `sensor.skytech_hems_flow_status` trägt die Kennzahlen des letzten Zyklus und je Gerät einen
    Rückfallwert, falls ein Direktsensor ausfällt. Ein unbrauchbarer Messwert wird nie zu `0` —
    eine fehlende Messung sieht sonst aus wie ein ausgeschaltetes Gerät.
  - Neue Anlagenwerte unter `flow_*`: PV-Sensoren (werden summiert), Netz wahlweise signiert oder
    als getrennte Sensoren, optional die Hausleistung sowie der Hausspeicher mit Ladestand und
    Kapazität. Dazu die Anzeigeoptionen Überschrift, W/kW-Schwelle, Animation und Hausknoten.
  - Je Gerät neu: `flow_show`, `flow_icon` und `flow_color`. Sie ändern ausschließlich die
    Darstellung; ein geändertes Icon schaltet kein Gerät ab (D-048).
  - Neuer Diagnoseendpunkt `GET api/flow/preview` zeigt beide Nutzlasten und je Verweis, ob er
    gerade trägt.
  - Die Konfigurationsentität trägt zusätzlich das Regelintervall. Ohne diesen Wert könnte die
    Karte nicht beurteilen, ab wann ihre Statusdaten veraltet sind — die Regel stand im Vertrag,
    die Größe dazu fehlte. Additiv, ohne Sprung der Schemaversion.
  - Neuer Sidebar-Bereich „Flow Card" im Panel: Veröffentlichung ein- und ausschalten, Erzeugung,
    Netz, Haus und Batterie pflegen, je Gerät Sichtbarkeit, Symbol und Farbe setzen, dazu die
    Anzeigeoptionen. Die Vorschau zeigt auf Knopfdruck, welcher Verweis gerade trägt und welcher
    nicht.
  - Rein additiv: ohne `flow_publish: true` wird keine einzige Entität geschrieben, und eine
    Bestandsanlage ohne `flow_*`-Optionen verhält sich unverändert. Empfehlung: beide Entitäten
    vom `recorder` ausschließen, solange keine Historie gewünscht ist.
- **Formel-basierte Sensorwerte für Überschuss und Hausleistungsbilanz (D-045).** Neuer
  Sidebar-Bereich „Sensoren" mit den Tabs „Überschuss" und „Hausbilanz": beliebig viele benannte
  HA-Entitäten kombinieren und in einem eingeschränkten Python-Ausdruck zu `ueberschuss` bzw.
  `hausbilanz` verrechnen. Ein „Testen"-Button führt den Entwurf live gegen den aktuellen
  HA-Schnappschuss aus, bevor gespeichert wird.
  - Liefert die Formel einen gültigen Wert, ersetzt sie die konfigurierte Einzel-Entität
    vollständig; sonst greift unverändert der bisherige Sensor. Welche Quelle gerade wirkt, steht
    neu als `residual_source`/`battery_residual_source` in `/api/status` und wird im
    Sensoren-Formular sowie auf der Status-Seite angezeigt.
  - Ausführung über einen selbstgebauten AST-Whitelist-Interpreter (`app/formula.py`, reine
    Stdlib, keine neue Abhängigkeit) — keine Schleifen, Imports, Funktionsdefinitionen oder
    Attributzugriffe möglich; ein Fehler in der Formel bricht einen Regelzyklus nie ab.
  - Rein additiv: ohne gepflegte Formel ist das Verhalten jeder Bestandsanlage unverändert, keine
    Migration nötig. Ergänzt die externe HA-Vorlage aus D-044, ersetzt sie nicht.
- **Optionaler Ist-Leistungssensor bei binären Geräten.** Neues Add-on-Feld `power_actual_entity`
  (`class: binary`): Entity-ID eines Sensors mit der tatsächlichen Ist-Leistung. Rein optional und
  ohne jede Wirkung auf Pool-Reservierung, Hysterese oder Zeitschutz — reine Datenquelle für
  spätere Ausbaustufen. Ist der Sensor konfiguriert und liefert er einen gültigen Wert, erscheint
  er zusätzlich als `power_actual_w` in `/api/status`.

## [2.0.0] - 22.08.2026

### Behoben

- **Speichern aus der Ingress-Konfiguration scheiterte mit `HTTP 403`.** Das Manifest verwendete
  `hassio_role: default`, obwohl diese Rolle nur Supervisor-Informationsaufrufe erlaubt. Das Add-on
  fordert jetzt die für Optionsvalidierung, Speichern und Neustart erforderliche Manager-Rolle an.
  Ein 403 erklärt außerdem verständlich, dass eine ältere Installation aktualisiert oder neu
  gebaut werden muss. Bereits beim Start übersprungene Geräte bleiben bis zum erfolgreichen
  Speichern und Neustart bewusst als Laufzeitstatus sichtbar.

### Migration bestehender Anlagen

1. **Regelbare Geräte** brauchen sechs neue Felder: `technical_minimum`, `technical_maximum`,
   `increase_delay_s`, `decrease_delay_s`, `maximum_step_change` und `minimum_step_change` — in der
   zu `output_unit` passenden Einheit, also bei einer Wallbox in **Ampere**. `technical_maximum`
   muss größer als `0` sein.
2. **Binäre Geräte** brauchen fünf neue Felder: `power_w` (größer als `0`), `on_reserve_w`,
   `min_runtime_s`, `min_offtime_s` und `off_delay_s`.
3. **AC-Speicher** brauchen die direkten Wattwerte `available_charge_power_w` und
   `available_discharge_power_w` (jeweils mindestens `0`). Die zuvor geplanten Felder
   `available_charge_power_entity` und `available_discharge_power_entity` entfallen. Optional,
   aber empfohlen: `soc_max_hysteresis_percent` (Default `2`) und
   `direction_switch_delay_s` (Default `5`). Neue Speicherformulare lassen die beiden
   Leistungswerte bewusst leer und markieren sie bis zur Eingabe als Pflichtfehler.
4. Ein Gerät ohne diese Felder wird beim Start **nicht registriert**. Es verschwindet nicht:
   `/api/status` führt es unter `inactive_devices` samt Feldfehlern auf, und die Konfigurationsseite
   zeigt sie direkt am betroffenen Feld.
5. **Löschbar** sind danach die sieben entfallenen Speicher-Helfer (siehe „Entfernt"). Beim
   regelbaren Gerät bleibt `min_umschaltzeit_s` als Phasenwechsel-Sperre erhalten.
6. Die Add-on-Optionen lassen sich jetzt im Ingress-Panel unter **Konfiguration** pflegen —
   dieselbe Quelle, die auch die native Add-on-Seite schreibt.
7. **AC-Speicher** brauchen zusätzlich `battery_residual_power_entity`: eine `sensor.<name>`-
   Entity für die signierte Hausleistungsbilanz (negativ = Unterdeckung, positiv = Einspeisung).
   Der Sensor muss Netzleistung und E3DC-Batterieleistung zusammenführen. Ohne ihn bleiben
   AC-Speicher nach dem Neustart sicher in `standby`; Laden und übrige Verbraucher verwenden
   weiterhin `residual_power_entity`.

### Hinzugefügt
- **Separate Hausleistungsbilanz für AC-Speicher (D-044).** Die globale Add-on-Option
  `battery_residual_power_entity` steuert ausschließlich die Entladeplanung: negativ =
  Netzbezug/Unterdeckung, positiv = Einspeisung. Sie führt Netzleistung und E3DC-Batterieleistung
  zusammen, während der bestehende Überschuss-Sensor unverändert für PV-Laden und Verbraucher
  bleibt.
  - Das HEMS zieht die bereits gemessene AC-Entladung aus der Bilanz heraus, rechnet gemessene
    HEMS-Lasten zurück und zieht `input_number.ems_ac_speicher_entlade_abschlag_w` einmal für die
    gesamte Speicherflotte ab.
  - Ein fehlender, `unknown`, `unavailable` oder nicht numerischer Bilanzwert schickt alle
    AC-Speicher aktiv auf `0 W` und `standby`, löst aber keinen Hard-Lockout der Verbraucher aus.
  - Ingress-Konfiguration, native Add-on-Übersetzungen, Statusvertrag und Steuerungsschema
    zeigen die zusätzliche Entity und ihren Zustand. Die HA-Template-Vorlage und die Tests
    bilden die drei geprüften `700-W`-Fälle für E3DC und AC-Speicher ab.
- **Doppelte Fallback-Auflösung mit Ursache und Quelle.** `StateProxy` kann jetzt zwischen
  `missing` (Entity-ID im HA-Schnappschuss nicht vorhanden), `unavailable` (Entität da, State
  `unknown`/`unavailable`/`null`), `invalid` (State da, aber falscher Typ, nicht endlich oder
  außerhalb eines zwingenden Bereichs) und `valid` unterscheiden. Jeder aufgelöste Wert meldet
  zusätzlich seine Quelle: `ha`, `addon` oder `internal`. Die neuen Methoden `has()`,
  `availability()`, `resolve_number()`, `resolve_bool()` und `resolve_select()` sind ab sofort der
  einzige Weg, einen HA-State in einen Regelwert zu verwandeln.
  - **Ein gültiger Wert `0` wird nie mehr verworfen.** Wahrheitswert-Ausdrücke wie
    `wert or fallback` konnten eine ausdrücklich eingetragene Null nicht von „kein Wert"
    unterscheiden. Zahlen laufen zusätzlich durch `math.isfinite`, damit `NaN` und `±inf` nicht als
    Regelgröße in die Anlage gelangen.
  - **Fehlend und ausgefallen sind trennbar.** `resolve_bool()` kennt dafür einen eigenen
    `missing_fallback` — eine gar nicht angelegte Freigabe darf anders behandelt werden als eine
    ausgefallene.
- **Status- und Steuerungsseite zeigen die neuen Diagnosen.**
  - Die Statusseite unterscheidet jetzt sichtbar drei Fälle: keine Freigabe (`eligible`),
    technisch nicht regelbar (`runtime_active`, mit dem Grund im Klartext und der bereinigten
    Schreibfehlermeldung) und beim Start übersprungen. Übersprungene Einträge stehen in einem
    eigenen Abschnitt mit ihren Feldfehlern — ausdrücklich **ohne** erfundene Leistungs-, SoC-
    oder Schaltwerte.
  - Ein global nicht aktivierter Regelmodus wird als solcher benannt, statt wie ein normaler
    Modus auszusehen.
  - Der SoC-Balken der Speicherkarte trägt nur noch Minimum und Ladeschluss; die Limit-Zeile
    zeigt die statischen Wattgrenzen aus der Add-on-Konfiguration.
  - Die Steuerungsseite markiert je Helfer, ob gerade der HA-Wert, der Add-on-Wert oder ein
    interner Default wirkt. Bei einem Helfer mit Add-on-Fallback war das vorher nicht erkennbar.
  - Der Energy Pilot zeigt `lade_max_w` und `entlade_max_w` nicht mehr an. Die HA-Entitäten
    dürfen in einer Bestandsanlage weiterleben; sie anzuzeigen behauptete aber, sie wirkten noch.
- **Neuer Bereich „Konfiguration" in der Oberfläche.** Globale Einstellungen und Geräte lassen
  sich jetzt bedienbar pflegen, statt nur im YAML-Editor der Add-on-Seite.
  - **Geräteliste** mit Klasse, Name, Präfix, erlaubten Modi, Validität, Laufzeitstatus,
    Bearbeiten, Löschen und Hoch/Runter. Die Reihenfolge bleibt erhalten — sie entscheidet bei
    gleicher Priorität.
  - **Ein Formular für Anlegen und Bearbeiten**, mit bedingten Abschnitten je Geräteklasse. Ein
    leeres `allowed_modes` wird als **Nur Energy Pilot** gekennzeichnet, Pflichtfelder sind am
    Label markiert, und Server-Feldfehler stehen direkt am betroffenen Feld.
  - **Entitätsauswahl mit Suche** aus dem laufenden HA-Schnappschuss, gefiltert nach Domain. Ein
    gespeicherter Wert, den es gerade nicht gibt, wird mit Warnung angezeigt statt gelöscht.
  - **Abgeleitete HA-Helfer mit Zustand:** vorhanden, fehlt, nicht verfügbar, ungültig oder
    Schreiben fehlgeschlagen — dazu, ob gerade der HA-Wert, der Add-on-Wert oder ein interner
    Default wirkt.
  - **Drei getrennte Aktionen** in einer klebrigen Leiste: Speichern, Neu starten sowie als
    einzige Primäraktion Speichern und neu starten. Ungespeicherte Änderungen sind sichtbar, warnen
    vor Navigation und Neuladen und werden vor einem Neustart erst nach Bestätigung verworfen.
    Nach reinem Speichern bleibt sichtbar, dass die laufende Regelung erst nach einem Neustart
    wechselt.
  - Wird ein globaler Regelmodus deaktiviert, nennt die Oberfläche die betroffenen Geräte und
    entfernt ihn erst nach Bestätigung aus deren `allowed_modes`.
- **Add-on-Optionen sind jetzt aus dem Ingress-Panel heraus pflegbar.** Neue Endpunkte
  `GET /api/config`, `GET /api/config/entities`, `POST /api/config/validate`, `PUT /api/config`,
  `POST /api/config/restart` und `POST /api/config/save-and-restart`. Geschrieben wird
  ausschließlich über die Supervisor-API (`http://supervisor/addons/self/…`) — **dieselbe Quelle**,
  die die native Add-on-Seite bedient. Es gibt keine zweite Konfigurationsdatei und kein direktes
  Schreiben nach `/data/options.json`; die Datei wird nur noch gelesen.
  - **Revisionsschutz.** Ein Hash über die **rohen** gespeicherten Optionen erkennt auch eine
    Änderung an einem Feld, das diese Oberfläche gar nicht anzeigt. Wurde zwischenzeitlich an
    anderer Stelle gespeichert, antwortet der Server mit `409` statt die fremde Änderung zu
    überschreiben. Beim Speichern werden die bekannten Felder in die **frisch gelesenen** rohen
    Optionen gemischt, damit unbekannte künftige Top-Level-Felder erhalten bleiben.
  - **Speichern und Neustarten sind getrennt.** Speichern startet nie neu; `restart_required`
    zeigt an, dass die laufende Regelung noch mit dem alten Stand arbeitet. Vor einem Neustart
    werden geänderte oder gelöschte Altgeräte über ihre **alten** Schreibziele sicher deaktiviert
    (`controllable` → `0`, `binary` → `off`, `battery` → erst `0 W`, dann `standby`). Schlägt das
    fehl, wird **nicht** neu gestartet — bei „Speichern und neu starten" bleibt die Konfiguration
    dann gespeichert, und die Antwort benennt diesen Teilstatus ausdrücklich.
  - **`instance_id` in `/api/status`.** Eine je Prozessstart neue Kennung; erst eine andere
    `instance_id` gilt als abgeschlossener Neustart. Eine sehr kurze Unterbrechung sähe sonst wie
    ein erfolgreicher Neustart aus.
  - **Nur-Lese-Modus ohne Supervisor.** Läuft das Add-on außerhalb von Home Assistant, ist die
    Konfiguration weiterhin sichtbar, `can_save` und `can_restart` sind `false` und die Oberfläche
    erklärt warum. Es wird nie vorgetäuscht, ein Schreibvorgang sei gelungen.
  - `config.yaml` erhält dafür `hassio_api: true`, ausdrücklich `hassio_role: manager` für die
    Supervisor-Schreibaufrufe und `panel_admin: true`.
- **Zentrales Konfigurationsmodell `app/configuration.py`.** Normalisierung, Validierung mit
  Feldpfaden (`devices[2].technical_maximum`) und deutschen Meldungen, stabiler Parser und
  Serializer für Modus-Listen, Eindeutigkeitsprüfung von Gerätename und Präfix, kanonischer
  Revisions-Hash über die rohen Optionen und der Diff, der vor einem Neustart sagt, welche alten
  Geräte sicher zu deaktivieren sind. Die gemischte Objektliste im Supervisor-Schema kann keine
  bedingten Pflichtfelder je Geräteklasse ausdrücken — die Anwendung ist deshalb die autoritative
  Validierung, und Oberfläche wie Controller bekommen dieselbe Antwort auf „ist dieser Eintrag
  gültig".
- **Verpflichtende Add-on-Fallbacks für `controllable` und `binary`.** Ein regelbares Gerät bringt
  jetzt `technical_minimum`, `technical_maximum`, `increase_delay_s`, `decrease_delay_s`,
  `maximum_step_change` und `minimum_step_change` mit, ein binäres `power_w`, `on_reserve_w`,
  `min_runtime_s`, `min_offtime_s` und `off_delay_s`. Die gleichnamigen HA-Helfer bleiben optional
  und haben bei einem gültigen State weiterhin Vorrang; fehlt der Helfer, fällt oder ist er
  unbrauchbar, greift der konfigurierte Wert. Bisher lief ein Gerät ohne seine Helfer still mit
  Nullwerten weiter — ein binäres Gerät mit `leistung_w = 0` machte die Pool-Rechnung fachlich
  unbrauchbar, ohne dass irgendwo etwas zu sehen war.
  - Die Werte eines Ampere-Geräts liegen in **Ampere**, nicht in Watt; die Umrechnung über
    Phasenzahl × Spannung erfolgt erst danach.
  - `phase_switch_delay_s` behält seine eigene Kette HA → Add-on → intern, verwirft aber keine
    gültige `0` mehr: sie bedeutet jetzt „keine Sperrzeit" statt „nimm den Default".
- **Globale Option `available_modes`.** Sie legt fest, welche der drei normalen Regelmodi
  (`manuell`, `nur_heizen`, `nur_laden`) in dieser Anlage überhaupt verwendet werden; Default sind
  alle drei, Bestandsanlagen verhalten sich also unverändert. `devices[].allowed_modes` muss eine
  Teilmenge davon sein. Meldet `input_select.ems_regelmodus` einen normalen, nicht aktivierten
  Modus, bleibt der Zyklus sicher inaktiv; der rohe HA-State bleibt als `global_mode` sichtbar und
  `global_mode_configured: false` nennt die Ursache. Die Optionen des HA-Helfers legt oder ändert
  das Add-on weiterhin nicht.
- **Ein leeres `allowed_modes` ist ein unterstütztes Gerät.** Es bedeutet **Nur Energy Pilot**:
  normale Nutzerregeln aktivieren das Gerät nie, der Energy Pilot erreicht es weiterhin. Fehlt das
  Feld ganz, gilt wie bisher `manuell`.
- **`inactive_devices` im Status.** Geräteeinträge mit fehlenden oder unbrauchbaren Pflichtfeldern
  werden beim Start nicht instanziiert, verschwinden aber nicht mehr in einer Log-Zeile: sie stehen
  mit Geräte-ID, Klasse, Label und konkreten Feldfehlern in `/api/status`. Für sie werden
  ausdrücklich **keine** Ist-, SoC- oder Schaltwerte erfunden, und sie beeinflussen den Pool nicht.
- **`entity_diagnostics` je Gerät.** `{entity_id: {role, state, source}}` beantwortet je gelesener
  Entität, welcher Wert gerade wirkt und warum nicht der aus Home Assistant.

- **Geräteklassen-Referenz unter `docs/device_classes/`.** Je eine Seite für `controllable`,
  `binary`, `battery` und globale Werte dokumentiert den tatsächlichen HA-Lese-/Schreibvertrag,
  Pflichtfelder der Add-on-Konfiguration, externe Entitätszuordnungen, Defaults und echte
  Add-on-Fallbacks. Die Prüfung hat außerdem B-4 sichtbar gemacht: Die reservierte
  Netzlade-Schnittstelle ist entgegen der bisherigen Dokumentation nicht hart gesperrt und muss
  bis zur vollständigen Implementierung deaktiviert bleiben.
- **AC-gekoppelte Speicher als eigene Geräteklasse (D-040, 1.1.0 → 1.2.0).** Mit
  `class: battery` verwaltet das HEMS jetzt auch Batteriespeicher: geladen wird aus
  PV-Überschuss und in derselben Prioritätsreihenfolge wie jeder andere Verbraucher, entladen
  wird zur Deckung des **normalen Hausverbrauchs** — ausdrücklich nicht für Heizstab, Wallbox
  oder Heizlüfter. Der Heizstab läuft damit nie aus der Batterie.
  - **Der Pool wird bereinigt, bevor er verteilt wird.** Ein Speicher ist der erste Teilnehmer,
    der den Messwert verfälscht, auf dem das HEMS aufbaut: seine Entladung erhöht den
    Überschuss-Sensor, ist aber kein Überschuss. `residual_bereinigt_w` zieht die gemessene
    Entladung ab; erst darauf laufen Pool und Verbraucher-Defizit. Ohne das läse das HEMS die eigene
    Entladung als Überschuss, schaltete Verbraucher zu — und der Speicher wäre in einem Zyklus
    leer.
  - **Das Hausdefizit stammt aus der separaten Bilanz.** `gemessene_last_w` rechnet alle
    HEMS-Lasten zurück; ein von Hand eingeschalteter Heizstab bleibt damit Überschussverbraucher
    und wird vom Speicher nicht gedeckt. Pool und Hausdefizit können diagnostisch gleichzeitig
    positiv sein; ein einzelner signierter Sollwert verhindert trotzdem gleichzeitiges Laden und
    Entladen.
  - **Getrennte Lade- und Entladepriorität.** `prioritat` gilt fürs Laden,
    `entlade_prioritat` fürs Entladen. „Lade mich zuletzt, entlade mich zuerst" ist damit
    konfigurierbar — mit einer Zahl wäre es nicht ausdrückbar.
  - **Ausgabe: ein signierter Sollwert plus Betriebsart.**
    `input_number.ems_<prefix>_anforderung_leistung_w` trägt „+ laden / − entladen",
    `input_select.ems_<prefix>_anforderung_betriebsart` die Betriebsart. Die Übersetzung nach
    Modbus oder MQTT macht eine HA-Automation, nicht das Add-on. **Der Zahlen-Helfer braucht ein
    negatives Minimum**, sonst klemmt Home Assistant jede Entladeanforderung auf 0.
  - **SoC-Grenzen mit Drosselband und Hysterese**, statische Leistungsgrenzen in der
    Add-on-Konfiguration, Totzone um Null, Sperrzeit nach Richtungswechsel und
    eine asymmetrische Entladerampe: ein echter Lastabwurf wird sofort zurückgenommen, eine
    kleine Abweichung gedämpft — sonst wird aus Sensor-Versatz ein Grenzzyklus.
  - **Der sichere Zustand wird aktiv geschrieben.** Bei Lockout, fehlender Freigabe oder
    unbrauchbaren Messwerten schreibt das HEMS `0 W` und `standby`, statt den letzten Sollwert
    stehen zu lassen. Ein Speicher ohne gültigen Leistungsmesswert fällt aus der Regelung, die
    übrigen laufen weiter.
  - **Neue Statuskacheln und eine Speicherkarte** in der Oberfläche: Speicher netto,
    kapazitätsgewichteter SoC-Schnitt und Hausdefizit, dazu ein Ladezustandsbalken mit Markern
    für Minimum, Notstromreserve und Ladeschluss. Läuft ein HEMS-Gerät fremdgesteuert, benennt
    die Hausdefizit-Kachel den ausgenommenen Betrag — sonst sähe das im Energiedashboard wie ein
    Regelfehler aus.
  - **Ohne konfigurierten Speicher bleibt das Verhalten unverändert.** `netz_support_w` ist
    dann 0, die Bereinigung eine Identitätsoperation und die Entladeplanung läuft über eine
    leere Liste. Abgesichert durch `test_pool_ohne_speicher_unveraendert` und die Property P7.
  - Neue Add-on-Optionen `speicher_in_residual_enthalten` (Default `an`) und
    `battery_residual_power_entity`; die zweite ist bei AC-Speichern ein Pflichtfeld.
- **Versionierter Gerätevertrag für den Energy Pilot (D-039, 1.0.25 → 1.1.0).**
  `/api/device_controls_schema` bleibt in seiner bisherigen Listen-/Gruppenform kompatibel und
  ergänzt Geräteklasse, Entitätspräfix, Einheit, erlaubte Modi, Überschuss-Regelprinzip,
  Istleistungs- beziehungsweise Schaltentität und HEMS-Anforderung. Jedes `ems_*`-Item trägt nun
  einen stabilen Schlüssel, Datentyp, Einheit, semantische Rolle und die Angabe, ob es für die
  Planung relevant ist. Damit muss Energy Pilot keine Entity-Suffixe mehr erraten und kann
  Regelparameter aus dem KI-Kontext heraushalten.
- **Atomare, ablaufende EP-Vorschläge.** HEMS akzeptiert einen `sensor.ep_*_vorschlag` nur noch,
  wenn `sensor.ep_plan_commit` dieselbe `plan_id` und ein aktuelles Zeitfenster bestätigt.
  Fehlende, fehlerhafte, teilweise geschriebene oder abgelaufene Vorschläge fallen feldweise
  auf den Nutzerwert zurück. `/api/status` zeigt je Gerät den Diagnosewert
  `ep_proposal_status`; die bestehende Moduslogik bleibt unverändert.

### Geändert
- **Der Speichervertrag ist deutlich schmaler (BRECHEND).** Die physische Grenze eines AC-Speichers
  kommt jetzt ausschließlich aus den beiden verpflichtenden Wattwerten
  `available_charge_power_w` und `available_discharge_power_w` in der Add-on-Konfiguration.
  Dafür werden keine HA-Sensoren gelesen.
  - **Getrennte Grenzen.** Ein Wert `0` sperrt nur die jeweilige Richtung bewusst. Fehlende,
    negative oder nicht endliche Werte machen den Geräteeintrag ungültig.
  - **Harte Obergrenze.** Die Rampe darf einen Sollwert nie über den konfigurierten Wert führen.
  - **Kein SoC-Taper mehr.** Innerhalb der SoC-Grenzen ist allein der konfigurierte Wert
    maßgeblich, an der Grenze wird die Richtung `0`.
- **`max_anderung_pro_schritt_w` beim Speicher ist optional.** Ohne gültigen Wert gibt es keine
  Schrittbegrenzung und das Ziel wird unmittelbar erreicht. Intern ist das ein echtes „kein Limit",
  kein magischer Großwert — im Status steht deshalb nirgends `Infinity`.
- **Speicher-Reserve fällt auf 50 W statt 0 W.** Eine vorhandene Entität mit gültiger `0` setzt den
  Puffer weiterhin bewusst ab.
- **`laden_erlaubt` und `entladen_erlaubt` trennen fehlend von ausgefallen.** Eine gar nicht
  angelegte Freigabe heißt „erlaubt" — wer den Schalter nie angelegt hat, will keine zusätzliche
  Sperre. Eine vorhandene Entität mit `unknown`, `unavailable` oder unbrauchbarem State heißt
  dagegen „gesperrt": ein ausgefallener Schalter ist kein Grund weiterzuregeln.
- **Gerätename und effektives Entitätspräfix müssen eindeutig sein.** Zwei Geräte mit demselben
  Präfix schrieben bisher unbemerkt auf dieselben HA-Helfer.
- **`/api/status` liefert die Zwischengrößen der Pool-Rechnung mit.** Neu sind
  `residual_bereinigt_w`, `netz_support_w`, `hems_last_w`, `hems_last_gemessen_w`, `pool_roh_w`,
  `entlade_basis_w` und `hausdefizit_w`. Rein additiv — bestehende Felder ändern weder Namen noch
  Bedeutung. Für Planer wichtig: Regelentscheidungen beziehen sich jetzt auf
  `residual_bereinigt_w`, nicht mehr auf `residual_w`.
- **`current_deficit_w` rechnet gegen den bereinigten Überschuss.** Ohne diese Änderung
  verschwände das Defizit, sobald ein Speicher die Hauslast deckt — und die Verbraucher liefen
  faktisch aus der Batterie. Ohne Speicher ist der Wert unverändert.
- **Neue Weboberfläche (React + TypeScript + Vite).** Die Bedienung ist dieselbe
  geblieben, nur besser: Aus den drei Tabs sind drei Seiten mit eigener Adresse
  geworden (Status, Steuerung, Energy Pilot), die Navigation sitzt links und
  fährt auf schmalen Bildschirmen als Menü aus. **Neu ist ein sichtbarer
  Schalter zwischen Hell- und Dunkel-Modus**; die Wahl bleibt über das Neuladen
  hinweg erhalten, voreingestellt ist die Systemvorgabe. Es gibt keine
  Funktionseinbuße: Live-Zähler für Mindestlauf-/Mindestauszeit,
  Abschaltverzögerung und Phasenwechsel-Sperre laufen weiterhin sekündlich
  herunter, Zahlenfelder speichern wie bisher verzögert (700 ms) und beim
  Verlassen des Felds, die Vorschläge des Energy Pilot werden weiterhin um
  verwaiste Altwerte bereinigt. Neu ist außerdem, dass ein fehlgeschlagenes
  Speichern als Meldung erscheint statt nur als Zeichen in der Zeile.
- **Rückmeldung zum letzten Zyklus in deutschem Zeitformat.**
  `/api/status.last_cycle_at` liefert jetzt `TT.MM.JJJJ hh:mm:ss` in Berliner
  Zeit. Das bisherige Maschinenformat bleibt zusätzlich erhalten und steht neu
  in `last_cycle_at_iso` — bestehende Auswertungen lesen unverändert weiter.
- **Beschreibung des Log-Levels korrigiert.** Der Helfer
  `input_boolean.ems_pyems_debug_output` schaltet das zusätzliche
  Regelentscheidungs-Logging, nicht den Log-Level. Die Add-on-Optionen sagten
  bisher etwas anderes.

### Hinzugefügt
- **Roher Schutz-Sockel im Gerätestatus (`geschuetzte_mindestleistung_w`/`_a`).**
  `ControllableDevice.to_status_dict` liefert jetzt zusätzlich zum effektiven Schutz
  `schutz_w`/`schutz_a` auch den **rohen**, vom User gepflegten Sockel
  `geschuetzte_mindestleistung_w` (Watt) bzw. `geschuetzte_mindestleistung_a` (Ampere).
  Hintergrund: `schutz_w = geschützte Mindestleistung + reserve_w + global_puffer_w`
  (geklemmt) ist der effektive Schutz und NICHT die vom User eingetragene geschützte
  Mindestleistung. Der Energy-Pilot verglich in der Plan-Rückkopplung fälschlich gegen
  `schutz_w` und zeigte so z.B. 900 W statt der eingetragenen 600 W. Rein additiv –
  `schutz_w`/`schutz_a` bleiben unverändert erhalten (weiter für die Regelung genutzt).
- **Energy-Pilot-Tab in der Weboberfläche (Anzeige der EP-Daten).** Neuer Tab
  „Energy Pilot" spiegelt die vom Energy Pilot gelieferten Daten – EP schreibt
  seine KI-Vorschläge und Statuswerte als HA-`sensor.ep_*`-Entitäten, HEMS liest
  sie wie den Rest über die HA-REST-API (neuer Endpunkt `GET /api/ep`, filtert
  `sensor.ep_*`) und stellt sie dar: Plan-Status (Label, Gültigkeits-Countdown,
  Zeitfenster, Abweichungen aus `sensor.ep_plan_status`), EP↔HEMS-Verbindung
  (online/offline, letzter Zyklus, Modus aus `sensor.ep_hems_verbindung`) sowie
  die Vorschläge je Gerät (Freigabe/Priorität/geschützte Mindestleistung/Extras,
  aus `sensor.ep_<gerät>_*_vorschlag`). **Rein additiv/Anzeige** – kein direkter
  Add-on-zu-Add-on-Aufruf, keine Änderung am Regelzyklus.
  - **Verwaiste Vorschläge werden ausgeblendet.** HEMS spiegelt nur und löscht keine
    HA-Entitäten; tauscht man in EP einen Quellsensor, schreibt EP eine neue
    `entity_id`, während die alte mit eingefrorenem Wert in HA verbleibt. Der EP-Tab
    blendet solche Altwerte aus: (1) abgelaufene Vorschläge (`valid_until` in der
    Vergangenheit) werden nicht angezeigt, (2) bei doppeltem Feld je Gerät wird nur
    der frischere (späteres `valid_until`) behalten – ohne Kopplung an die
    Publish-Reihenfolge von `sensor.ep_plan_status`.
- **Steuermodus-abhängige Energy-Pilot-Übernahme (EP → HEMS, D-033).** Der
  Regelmodus entscheidet pro Gerät, ob die Regelung die Nutzer-Helfer (`ems_*`)
  oder die KI-Vorschläge (`sensor.ep_*_vorschlag`) verwendet. Neuer Wert
  `manuell` in `input_select.ems_regelmodus`. Semantik überall: **auto = KI,
  manuell = normale Regeln, aus = aus**.
  - `regelmodus = auto` → alle Geräte folgen dem EP-Vorschlag.
  - `regelmodus = manuell` / `nur_heizen` / `nur_laden` → normale Regeln; pro
    Gerät über `input_select.ems_<gerät>_modus` verfeinerbar (`auto` = EP für
    dieses Gerät und überspringt das Typ-Gate, `manuell` = normale Regeln,
    `aus` = Gerät aus – gilt auch als Kill-Switch bei `regelmodus = auto`).
  - Übernommen werden **Priorität** (`ep_<p>_prio_vorschlag` → `prioritat`),
    **Freigabe** (`ep_<p>_freigabe_vorschlag` → `freigabe`) und **geschützte
    Mindestleistung** (`ep_<p>_geschutzte_mindestleistung_w_vorschlag`, nur
    Watt-Geräte). Die technische Freigabe (`ems_<p>_technische_freigabe`) bleibt
    in jedem Modus hartes Gate; harte Grenzen (min/max, Lockout) gelten weiter.
  - **Fallback:** Fehlt/stört ein `sensor.ep_*_vorschlag`, greift der Nutzerwert
    (KI-Ausfall blockiert die Anlage nie). Gerätestatus (`/api/status`) enthält
    neu das Feld `source` (`aus`/`user`/`ep`).
  - **Migration:** Bestandskonfigurationen mit `allowed_modes: "auto"` werden auf
    `manuell` abgebildet. Anlagen, die zuvor `regelmodus = auto` als normale
    Regelung nutzten, müssen auf `manuell` wechseln.
- **Responsive Darstellung (Handy/Tablet).** Die Ingress-Oberfläche passt sich an kleine
  Bildschirme an – **kein horizontales Scrollen mehr, nur vertikal**: Gerät- und Steuerungs-
  Kacheln werden am Handy (≤480 px) einspaltig (kein `minmax`-Überlauf schmaler Raster), die
  Tab-Leiste bricht um statt seitlich zu scrollen, Werte/Namen brechen um, größere Touch-Ziele.
  Tablet-Breakpoint (≤900 px). **Rein visuell/additiv** – Karten, IDs und `app.js` unverändert.
- **`/api/status` liefert für Ampere-Geräte zusätzlich `schutz_a`.** Der effektive
  Mindestleistungs-Schutz (`schutz_w`, Watt) wird über Phasenanzahl × Spannung nach Ampere
  umgerechnet und im Gerätestatus mitgegeben – analog zum bestehenden `new_a`. Ohne dieses
  Feld konnten Ampere-Konsumenten (Energy Pilot) den Schutz nicht einheitengleich mit ihrem
  Ampere-Vorschlag (`geschutzte_mindestleistung_a_vorschlag`) vergleichen: Watt-Geräte hatten
  `schutz_w`, Ampere-Geräte (Wallbox) gar kein Pendant, sodass die Plan-Rückkopplung dort
  „unbekannt" statt eines Vergleichs zeigte.

### Behoben
- **Ungültige Geräteeinträge erreichten den Status nicht.** `main.py` reichte nur die bereits
  gefilterten, gültigen Einträge an den Controller weiter — der fand darin folgerichtig nichts
  Ungültiges mehr, und `inactive_devices` blieb im Status immer leer. Der Controller bekommt
  jetzt die vollständige Liste und ist die eine autoritative Validierung.
- **Fehlgeschlagene Schreiboperationen verschwinden nicht mehr im Log (B-2).** Bisher wurde ein
  Nicht-2xx-Status nur geloggt, der Zyklus galt danach als erfolgreich (`error: ""`) und in der
  Oberfläche war nichts zu sehen — ein vertippter Helfername schlug jeden Zyklus still fehl. Jede
  Operation trägt jetzt ihr verursachendes Gerät mit; `HAClient.execute_write_ops()` meldet je
  Operation Erfolg oder bereinigten Fehler zurück, und der Controller ordnet ihn zu.
- **Schreibziele werden vor der Zuteilung geprüft.** Existenz, Verfügbarkeit, Domain, die nötigen
  `input_select`-Optionen und beim signierten Speicher-Sollwert das negative Minimum. Fehlt oder
  taugt eines davon, wird **nur dieses** Gerät `runtime_active: false`: keine Zuteilung, keine
  Pool-Reservierung — aber weiterhin der sichere Zustand (`0`, `off` beziehungsweise `0 W` und
  `standby`), und zwar bedingungslos, damit eine reparierte Entität ohne Add-on-Neustart wieder
  eingefangen wird. Die übrigen Geräte regeln unverändert weiter, und der Zyklus gilt nicht als
  fehlgeschlagen.
  - Neu im Status je Gerät: `runtime_active`, `inactive_reasons` und `write_error`; global
    `devices_inactive_runtime`.
  - `eligible: false`, `runtime_active: false` und ein Eintrag in `inactive_devices` sind drei
    verschiedene Aussagen und werden getrennt angezeigt.

### Entfernt
- **Sieben Speicher-Helfer entfallen (BRECHEND).** Sie werden nicht mehr gelesen, haben keine
  Wirkung mehr und dürfen in Home Assistant gelöscht werden:
  `max_ladeleistung_w`, `max_entladeleistung_w`, `soc_reserve_prozent`, `soc_taper_band_prozent`,
  `soc_max_hysterese_prozent`, `entlade_sofort_schwelle_w` und `min_umschaltzeit_s` (nur beim
  Speicher — beim regelbaren Gerät bleibt `min_umschaltzeit_s` die Phasenwechsel-Sperre).
  - Die beiden Maximalleistungen werden durch `available_charge_power_w` und
    `available_discharge_power_w` in der Add-on-Konfiguration ersetzt.
  - Hysterese und Umschaltsperre sind jetzt statische Add-on-Felder
    `soc_max_hysteresis_percent` (Default `2`) und `direction_switch_delay_s` (Default `5`).
  - **Notstromreserve, Drosselband und Entlade-Sofort-Schwelle entfallen ersatzlos.** Der
    Entladeboden ist nur noch `soc_min_prozent`. Absenkungen der Entladeanforderung laufen
    ausschließlich über `max_anderung_pro_schritt_w`; die Fälle, die wirklich sofort auf `0 W`
    müssen — sicherer Standby, ungültiger Sensor, Richtungswechsel, Netzdefizit — greifen ohnehin
    vor der Rampe. Der Status verliert dadurch `soc_reserve_prozent` und den Sperrgrund
    `soc_reserve`.
- **Die Energy-Pilot-Vorschläge `lade_max_w` und `entlade_max_w` werden nicht mehr gelesen** und
  sind aus dem HEMS-Gerätevertrag entfernt. Der Energy Pilot darf physische Grenzen des
  Wechselrichters nicht überschreiben.

### Behoben
- **Gültig korrigierte Geräte bleiben nicht mehr als übersprungen markiert.** Die Geräteliste
  unterscheidet jetzt den aktuellen Entwurf vom geladenen Altzustand. Nach einer erfolgreichen
  Speicherung werden die veralteten Fehler- und `inactive_devices`-Daten ebenfalls entfernt.
  Dadurch ist sichtbar, dass Speichern erfolgreich war und nur noch der Neustart aussteht.
- **Neue Speichergrenzen werden nicht mehr still mit `0 W` vorbelegt.** Beide Pflichtfelder
  starten leer und bleiben rot markiert, bis der User die reale Lade- beziehungsweise
  Entladegrenze ausdrücklich eingetragen hat. Eine bewusst eingegebene `0` bleibt gültig.
- **Geräteformular bleibt nach Korrekturen nicht mehr rot.** Feldfehler aus dem geladenen Stand
  werden bei einer lokalen Korrektur sofort ausgeblendet und der übernommene Entwurf danach erneut
  serverseitig validiert. Langsame alte Validierungsantworten können keinen neueren Stand mehr
  überschreiben.
- **Konkrete Fehler beim Speichern sind wieder sichtbar.** Der Frontend-API-Client behält bei
  `422` den vollständigen JSON-Fehlerrumpf. `field_errors` gingen zuvor verloren, sodass nur ein
  allgemeiner Fehler erschien und die tatsächlich beanstandeten Felder nicht aktualisiert wurden.
- **Fremdgesteuerte Verbraucher blähen den Pool nicht mehr auf.** Der Pool wird als
  `residual_w + Summe(current_w)` gebildet – diese Rückrechnung ist nur zulässig, wenn HEMS
  die Leistung selbst angefordert hat und sie daher auch wieder freigeben kann. Wurde ein
  Gerät extern („Force-Modus" außerhalb HEMS) eingeschaltet, rechnete HEMS diese Fremdlast
  als eigenen, abschaltbaren Überschuss gut, verteilte sie an weitere Verbraucher und erzeugte
  Netzbezug. Jetzt gilt:
  - `BinaryDevice.current_w` liefert `power_w` nur, wenn der Schalter AN **und** die
    HEMS-Anforderung (`input_boolean.ems_<prefix>_anforderung_an`) aktiv ist. Der
    Anforderungszustand wird dazu neu aus HA gelesen und als `anforderung_an` im
    Gerätestatus (`/api/status`) ausgegeben; die Oberfläche zeigt bei Fremdsteuerung
    den Hinweis „⚠ extern AN – zählt nicht zum Pool".
  - `ControllableDevice.current_w` wird auf den HEMS-Sollwert gedeckelt
    (`min(actual_w, anforderung_current_w)`, 0 wenn nicht freigegeben). Damit zählt auch
    ein Teil-Fremdbezug (HEMS fordert 3 kW an, extern laufen 11 kW) nur mit 3 kW.
    `max_relief_w` nutzt dieselbe gedeckelte Größe, sonst überschätzte die
    Defizit-Notabschaltung die tatsächlich abregelbare Leistung.

  Die Fremdlast bleibt implizit über `residual_w` berücksichtigt (dort ist sie bereits
  abgezogen); HEMS regelt konservativ um sie herum. Der Normalbetrieb ist unverändert.

### Geändert
- **Lesbare deutsche Anzeigetexte (UI-Audit).** Verbliebene englische/technische Bezeichner
  in der Oberfläche durch deutsche ersetzt: Status-Tab-Zeile `Ziel (alloc)` → `Ziel (Zuteilung)`;
  Warn-Chip `⚠ LOCKOUT` → `⚠ SPERRE`;
  Regelmodus-Chip zeigt den Wert lesbar (`nur_heizen` → „Nur Heizen", `auto` → „Automatik" …)
  statt in snake_case; Steuerung-Tab-Label `Deadband` → `Totband (Deadband)` (im Kontrollschema,
  `/api/device_controls_schema`). Rein anzeigeseitig – Entitäts-IDs unverändert.
- **Weboberfläche im Home-Assistant-Design neu gestaltet.** Layout, Farben und Aufbau des
  Monitoring-/Steuerungs-UIs sind jetzt stark an das HA-Standardtheme (Material Design)
  angelehnt: blaue App-Bar (Primärfarbe `#03a9f4`) mit den View-Tabs „Status"/„Steuerung" und
  Unterstrich-Indikator, abgerundete `ha-card`-Karten (12 px, weiche Schatten) für Kennzahlen,
  Geräte- und Steuerkarten, HA-typische Statuschips, `ha-switch`-artige Toggle-Pillen und
  HA-Textfelder – inklusive hellem **und** dunklem Theme über `prefers-color-scheme`.
  - **Rein visuell – keine funktionale Änderung:** beide Tabs, alle API-Aufrufe (`/api/status`,
    `/api/controls`, `/api/device_controls_schema`, `/api/set`), sämtliche Element-IDs und das
    gesamte `app.js`-Verhalten (Polling, Countdown-Ticker, Auf-/Zuklappen, Speichern) bleiben
    unverändert. Die Klassennamen sind identisch.
  - **CSS jetzt inline in `templates/index.html`** (wie beim Energy Pilot) statt in einer
    separaten `static/styles.css` – letztere wurde entfernt. Damit greift das neue Design unter
    HA-Ingress zuverlässig, ohne dass ein separat gecachtes Stylesheet veralten und die alte
    Optik plus überdimensioniertes Kopf-Logo stehenlassen kann. `static/app.js` bleibt separat.
- **`/api/device_controls_schema` liefert je Gerät zusätzlich `name`.** Das Kontrollschema
  gab bisher nur `label` (Anzeigename) + `items` aus. Konsumenten (Energy Pilot) mussten die
  technische Geräteidentität aus dem `entity_prefix` erraten und hingen für die Zuordnung am
  Label – ein Label-Rename in der Geräteverwaltung brach die Korrelation. Das Schema enthält
  nun `name` (technischer Bezeichner, identisch mit der `id` in `/api/status`), sodass EP die
  Identität am stabilen `name` festmacht und `label` nur noch anzeigt. Rein additiv,
  abwärtskompatibel.
- **Doppelte Geräte-Freigabe:** Ein Gerät wird für das HEMS nur noch dann
  freigegeben (eligible), wenn **beide** Freigabe-Schalter aktiv sind:
  `input_boolean.ems_<prefix>_freigabe` (Bedien-/Nutzungsfreigabe) **und** der
  neue `input_boolean.ems_<prefix>_technische_freigabe` (technische Freigabe).
  Zusätzlich muss – wie bisher – `input_select.ems_<prefix>_modus` auf `auto`
  stehen.

### Hinzugefügt
- Neuer Pro-Gerät-Helfer `input_boolean.ems_<prefix>_technische_freigabe`.
  Er erscheint im Steuerung-Tab der Web-UI (Label „Technische Freigabe") und ist
  in der README bei den gemeinsamen Geräte-Helfern dokumentiert.

### Migration
- Für **jedes** bereits konfigurierte Gerät muss in Home Assistant der neue
  Helfer `input_boolean.ems_<prefix>_technische_freigabe` angelegt werden.
  Solange dieser Helfer fehlt oder auf `off` steht, gilt das Gerät als **nicht**
  freigegeben und wird vom EMS nicht geregelt.
