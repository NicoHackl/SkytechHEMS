# Umsetzungsplan: Entitäten-Fallbacks und Add-on-Konfiguration

## Zweck und Arbeitsauftrag

Dieser Plan beschreibt die vollständige Umsetzung der abgestimmten Änderungen aus
`erweiterungen/enitäten_und_fallback/device_classes/`. Er ist als ausführbarer Arbeitsauftrag
für einen KI-Agenten gedacht. Die Umsetzung umfasst Backend, Regellogik, Supervisor-Anbindung,
Ingress-Oberfläche, Tests, Manifest, Statusverträge, Dokumentation und Changelog.

Die Dateien unter `erweiterungen/enitäten_und_fallback/device_classes/` sind Arbeitsunterlagen
mit Kommentaren und teilweise noch dem alten Ist-Stand. Die hier festgehaltenen Entscheidungen
haben Vorrang. Nach der Implementierung muss `docs/` den tatsächlichen Code beschreiben.

Vor der ersten Änderung sind vollständig zu lesen:

- `AGENTS.md`
- `docs/architektur.md`
- `docs/entwicklerrichtlinien.md`
- `docs/frontend.md`
- `docs/design-system.md`
- `docs/konfiguration.md`
- `docs/datenmodell.md`
- `docs/api-referenz.md`
- `docs/test-strategie.md`
- `docs/bekannte-luecken.md`
- die vier Dateien unter `erweiterungen/enitäten_und_fallback/device_classes/`

Die Umsetzung erfolgt ausschließlich auf `claude/main`. Bestehende, nicht zu diesem Arbeitspaket
gehörende Änderungen dürfen nicht überschrieben werden.

## Verbindliche Entscheidungen

### Konfigurationsoberfläche

1. Die Ingress-Oberfläche erhält einen Bereich **Konfiguration** mit getrennten Ansichten für
   **Globale Einstellungen** und **Geräte**.
2. Geräte können angelegt, bearbeitet, gelöscht und in ihrer Reihenfolge verschoben werden.
   Die Reihenfolge muss erhalten bleiben, weil sie bei gleichen Prioritäten entscheidet.
3. Es gibt genau diese drei Aktionen:
   - **Speichern**: validieren und in den Add-on-Optionen speichern, ohne Neustart;
   - **Neu starten**: das Add-on mit der bereits gespeicherten Konfiguration neu starten;
   - **Speichern und neu starten**: validieren, speichern, sicher deaktivieren und neu starten.
4. Ungespeicherte Formularänderungen werden vor **Neu starten**, Navigation und Neuladen
   erkennbar gemacht. Ein Neustart verwirft sie erst nach Bestätigung.
5. Nach **Speichern** muss sichtbar bleiben, dass die laufende Konfiguration erst nach einem
   Neustart wechselt. Die aktuell laufende Regelung darf nicht heimlich im Prozess umgebaut werden.
6. Die Konfigurationsseite nutzt das bestehende Home-Assistant-Design mit `data-design="ha"`,
   funktioniert in Hell und Dunkel und bleibt bei 375 px Breite vollständig bedienbar.

### Globale und gerätespezifische Regelmodi

1. Die vom Code unterstützten normalen Regelmodi bleiben fest vorgegeben:
   `manuell`, `nur_heizen` und `nur_laden`. Frei erfundene Namen sind unzulässig, weil dafür
   keine Regellogik existiert.
2. Eine neue globale Add-on-Option `available_modes` speichert die aktivierten normalen Modi als
   kommagetrennten String. Default für Bestandsanlagen:
   `"manuell,nur_heizen,nur_laden"`.
3. `auto` und `aus` sind Sondermodi von `input_select.ems_regelmodus`. Sie gehören weder in
   `available_modes` noch in `devices[].allowed_modes` und bleiben immer unterstützt.
4. `devices[].allowed_modes` bleibt ein verpflichtendes Add-on-Feld und wird weiterhin als
   kommagetrennter String gespeichert. Die UI zeigt dafür Checkboxen aus der Schnittmenge mit
   `available_modes`.
5. Eine leere Geräteauswahl ist gültig. Das Gerät wird in der UI als **Nur Energy Pilot**
   gekennzeichnet und kann nicht durch normale Nutzerregeln aktiviert werden.
6. Wird ein globaler Modus deaktiviert, muss die UI die betroffenen Geräte nennen und den Modus
   nach Bestätigung aus deren `allowed_modes` entfernen.
7. Der Altwert `auto` in `allowed_modes` wird weiterhin auf `manuell` migriert. Unbekannte Tokens,
   Duplikate und ein gerätespezifischer Modus außerhalb von `available_modes` werden validiert;
   gespeichert wird in stabiler Reihenfolge ohne Duplikate.
8. Meldet `input_select.ems_regelmodus` einen normalen, global deaktivierten Modus, ist dieser
   Zyklus sicher inaktiv. Der rohe HA-State bleibt im Status sichtbar; zusätzlich wird gemeldet,
   dass der Modus nicht konfiguriert ist. Die Optionen des HA-Helfers werden vom Add-on nicht
   angelegt oder dynamisch verändert.

### Entitäts-IDs und Messwerte

1. Felder wie `actual_power_entity`, `soc_entity` oder `switch_entity` enthalten ausschließlich
   die ID einer bereits vorhandenen HA-Entität. Die Add-on-Konfiguration erzeugt weder diese
   Entitäten noch Messwerte.
2. Entity-Auswahlfelder starten bei neuen Geräten leer und bieten die tatsächlich aus Home
   Assistant gelesenen Entitäten als Suchauswahl an. Ein aktuell nicht vorhandener, bereits
   gespeicherter Wert darf nicht stillschweigend gelöscht werden; er wird mit Warnung angezeigt.
3. Ist-Sensoren erhalten keine erfundenen Messwerte in der Konfiguration. Laufzeit-Fallbacks wie
   `0 W`, `230 V` oder sicherer Standby sind ausdrücklich Laufzeitverhalten und werden als solches
   diagnostiziert.

### Doppelte Fallback-Auflösung

Für alle gelesenen HA-Entitäten muss unterschieden werden:

- `missing`: Die Entity-ID ist im HA-Schnappschuss nicht vorhanden.
- `unavailable`: Die Entität existiert, ihr State ist `unknown`, `unavailable` oder `null`.
- `invalid`: Der State ist vorhanden, aber vom falschen Typ, nicht endlich oder außerhalb eines
  zwingenden Wertebereichs.
- `valid`: Der State ist verwendbar; insbesondere ist ein gültiger Wert `0` kein Anlass für
  einen Fallback.

Die fachlichen Fallbacks bleiben erhalten. Neu ist die Diagnose der Ursache und Quelle. Jeder
aufgelöste Wert kann deshalb als Quelle `ha`, `addon` oder `internal` melden. Die Regelung darf
nicht durch Wahrheitswert-Ausdrücke wie `value or fallback` einen gültigen Nullwert verwerfen.

Der Statusvertrag wird additiv um `entity_diagnostics`, `runtime_active` und
`inactive_reasons` erweitert. Bestehende Statusfelder werden nicht beiläufig umbenannt.
`ep_proposal_status` bleibt für Bestandskonsumenten erhalten; genauere Ursachen eines fehlenden
oder nicht verfügbaren EP-Sensors stehen ebenfalls in `entity_diagnostics`.

### Schreibziele und inaktive Geräte

1. Die abgeleiteten Sollwert-Entitäten besitzen keinen Fallback. Fehlt ein Schreibziel, ist es
   `unknown`/`unavailable`, hat es eine unpassende Domain beziehungsweise notwendige Optionen
   nicht oder schlägt ein Schreibversuch fehl, wird das Gerät als nicht aktiv gekennzeichnet.
2. Betroffen sind:
   - `controllable`: der zur Einheit passende
     `input_number.ems_<prefix>_anforderung_leistung_<w|a>` und bei `phases: "1,3"`
     `input_number.ems_<prefix>_anzahl_phase`;
   - `binary`: `input_boolean.ems_<prefix>_anforderung_an`;
   - `battery`: `input_number.ems_<prefix>_anforderung_leistung_w` und
     `input_select.ems_<prefix>_anforderung_betriebsart` mit den Optionen `laden`, `entladen`
     und `standby`. Der Zahlenhelfer muss einen negativen Mindestwert erlauben.
3. Ein inaktives Gerät erhält keine normale Zuteilung. Soweit das Schreibziel erreichbar ist,
   versucht das HEMS weiter den sicheren Zustand zu schreiben, damit eine reparierte Entität
   ohne Add-on-Neustart wieder sicher eingefangen wird. Ein fehlendes Schreibziel kann nicht durch
   Direktzugriff auf das reale Gerät ersetzt werden; der unabhängige HA-Watchdog bleibt Pflicht.
4. Fehlgeschlagene Write-Ops dürfen nicht mehr nur geloggt werden. Sie werden dem verursachenden
   Gerät zugeordnet, im Status sichtbar gemacht und beheben damit die bekannte Lücke B-2.
   Andere Geräte laufen weiter.
5. Ungültige Add-on-Geräteeinträge werden beim Start nicht instanziiert, aber als
   `inactive_devices` mit Geräte-ID, Klasse, Label und konkreten Feldfehlern in den Status
   aufgenommen. Es dürfen dafür keine erfundenen Istwerte erzeugt werden.

## Ziel-Datenmodell der Add-on-Optionen

### Globale Felder

| Feld | Pflicht/Default | Validierung und Bedeutung |
|---|---|---|
| `interval_s` | Pflicht, Default `30` | Ganzzahl `1…300`; neues Intervall erst nach Neustart |
| `log_level` | Pflicht, Default `info` | `debug`, `info`, `warning` oder `error` |
| `post_cycle_script` | optional, leer | leer oder `script.<object_id>` |
| `residual_power_entity` | in der UI Pflicht, vorhandener Default | Entity-ID des globalen Überschuss-Sensors |
| `speicher_in_residual_enthalten` | Default `true` | bestehende Semantik unverändert |
| `available_modes` | Default alle drei normalen Modi | kommagetrennte Teilmenge aus `manuell`, `nur_heizen`, `nur_laden` |
| `devices` | Pflicht, darf leer sein | geordnete Geräteliste |

### Gemeinsame Gerätefelder

| Feld | Pflicht/Default | Validierung und Bedeutung |
|---|---|---|
| `name` | Pflicht | stabile, eindeutige ID; `[a-z0-9_]+` |
| `class` | Pflicht | `controllable`, `binary` oder `battery` |
| `label` | optional, Fallback `name` | reiner Anzeigename |
| `entity_prefix` | optional, Fallback `name` | `[a-z0-9_]+`; muss zwischen Geräten eindeutig sein |
| `allowed_modes` | Pflicht, darf leer sein | kommagetrennte Teilmenge von `available_modes`; leer = Nur Energy Pilot |

Fehlt `allowed_modes` in einer Bestandskonfiguration, wird für die Anzeige und Migration
`manuell` angenommen. Ein ausdrücklich gespeicherter leerer String bleibt leer und darf nicht
durch `manuell` ersetzt werden.

### `controllable`

Die sechs neuen Felder sind verpflichtende Add-on-Fallbacks. Die HA-Helfer bleiben optional und
haben bei einem gültigen State Vorrang.

| Add-on-Feld | Primärer HA-Helfer | Startwert im Formular | Validierung |
|---|---|---:|---|
| `technical_minimum` | `min_technisch_<u>` | `0` | endlich und `>= 0` |
| `technical_maximum` | `max_technisch_<u>` | `0` | endlich, `> 0` und `>= technical_minimum` |
| `increase_delay_s` | `hoch_regelzeit_s` | `60` | endlich und `>= 0` |
| `decrease_delay_s` | `runter_regelzeit_s` | `60` | endlich und `>= 0` |
| `maximum_step_change` | `max_anderung_pro_schritt_<u>` | `1000` | endlich und `> 0` |
| `minimum_step_change` | `min_anderung_pro_schritt_<u>` | `0` | endlich, `>= 0` und nicht größer als das Maximum |

`<u>` ist `w` bei `output_unit: watt` und `a` bei `output_unit: ampere`. Die Add-on-Werte liegen
ebenfalls in dieser nativen Einheit. Fehlt eines der sechs Felder in einer gespeicherten
Gerätekonfiguration, wird das Gerät beim Start übersprungen und als inaktiv angezeigt. Der
Formular-Startwert `0` für `technical_maximum` macht ein neu angelegtes Gerät absichtlich noch
nicht speicherfähig: Die reale Obergrenze muss vom User eingetragen werden.

Die vorhandenen Felder bleiben:

- `actual_power_entity` verpflichtend;
- `output_unit` mit Default `watt`;
- `phases` mit Default `"1"` und den Werten `"1"`, `"3"`, `"1,3"`;
- `phase_switch_delay_s` mit Default `300` als Fallback des optionalen HA-Helfers
  `min_umschaltzeit_s`;
- `voltage_l1_entity`, `voltage_l2_entity`, `voltage_l3_entity` optional, je Phase mit internem
  Fallback `230 V`.

`geschutzte_mindestleistung_<u>` und `reserve_w` behalten bei fehlendem und nicht verfügbarem
HA-State ihren bisherigen internen Fallback `0`. `prioritat` behält `99`.

### `binary`

Die fünf neuen Felder sind verpflichtende Add-on-Fallbacks. Die gleichnamigen HA-Helfer bleiben
optional und haben bei einem gültigen State Vorrang.

| Add-on-Feld | Primärer HA-Helfer | Startwert im Formular | Validierung |
|---|---|---:|---|
| `power_w` | `leistung_w` | `0` | endlich und `> 0` |
| `on_reserve_w` | `einschaltreserve_w` | `0` | endlich und `>= 0` |
| `min_runtime_s` | `mindestlaufzeit_s` | `0` | endlich und `>= 0` |
| `min_offtime_s` | `mindestauszeit_s` | `0` | endlich und `>= 0` |
| `off_delay_s` | `abschaltverzogerung_s` | `0` | endlich und `>= 0` |

`switch_entity` bleibt verpflichtend. Fehlt eines der fünf Fallback-Felder, wird das Gerät
beim Start übersprungen und als inaktiv angezeigt. `prioritat` behält den internen Fallback
`99`.

### `battery`

Verpflichtende externe Entity-Zuordnungen:

- `soc_entity`;
- genau eine vollständige Ist-Leistungsvariante:
  - `power_entity` mit `power_sign`, oder
  - `charge_power_entity` und `discharge_power_entity`.

Die beiden verpflichtenden Add-on-Felder `available_charge_power_w` und
`available_discharge_power_w` sind direkte Wattwerte ab `0` und die alleinigen physischen
Maximalgrenzen. Die HA-Helfer `max_ladeleistung_w` und `max_entladeleistung_w` entfallen. Ein
konfigurierter Wert `0` sperrt nur die jeweilige Richtung bewusst.

Neue beziehungsweise verbleibende statische Felder:

| Feld | Pflicht/Default | Bedeutung |
|---|---|---|
| `power_sign` | Default `positiv_laden` | `positiv_laden` oder `positiv_entladen` für `power_entity` |
| `capacity_kwh` | optional, Default `0` | ausschließlich Anzeige |
| `available_charge_power_w` | Pflicht, Formularstart leer | statische Ladegrenze in Watt; `0` sperrt Laden |
| `available_discharge_power_w` | Pflicht, Formularstart leer | statische Entladegrenze in Watt; `0` sperrt Entladen |
| `soc_max_hysteresis_percent` | Pflicht mit Default `2` | ersetzt den HA-Helfer `soc_max_hysterese_prozent` |
| `direction_switch_delay_s` | Pflicht mit Default `5` | ersetzt den HA-Helfer `min_umschaltzeit_s` des Speichers |

Folgende Speicher-Helfer und ihre Funktion werden vollständig entfernt:

- `input_number.ems_<prefix>_max_ladeleistung_w`;
- `input_number.ems_<prefix>_max_entladeleistung_w`;
- `input_number.ems_<prefix>_soc_reserve_prozent`;
- `input_number.ems_<prefix>_soc_taper_band_prozent`;
- `input_number.ems_<prefix>_soc_max_hysterese_prozent`;
- `input_number.ems_<prefix>_entlade_sofort_schwelle_w`;
- `input_number.ems_<prefix>_min_umschaltzeit_s` nur für `battery`.

Die entsprechenden Felder müssen auch aus Steuerschema, Statusdarstellung, UI, Tests und
Dokumentation verschwinden. Bestehende öffentliche Statusfelder `max_ladeleistung_w` und
`max_entladeleistung_w` bleiben aus Kompatibilitätsgründen erhalten und enthalten die
konfigurierten `available_*_w`-Werte. Die effektiven Felder `lade_limit_w`
und `entlade_limit_w` bleiben ebenfalls bestehen. `soc_reserve_prozent` wird entfernt, weil seine
Funktion ausdrücklich entfällt.

Weitere Speicher-Fallbacks:

- `soc_min_prozent`: optionaler HA-Helfer, intern `10`;
- `soc_max_prozent`: optionaler HA-Helfer, intern `100`;
- `min_ladeleistung_w` und `min_entladeleistung_w`: optional, intern `0`;
- `reserve_w`: optional; fehlende Entität fällt auf `50 W`, eine vorhandene Entität mit
  gültigem `0` überschreibt diesen Wert;
- `max_anderung_pro_schritt_w`: optional; Fallback **keine Begrenzung**;
- `min_anderung_pro_schritt_w`: optional; Fallback `0`;
- `laden_erlaubt` und `entladen_erlaubt`: fehlt die Entität vollständig, gilt die Richtung als
  erlaubt; existiert sie mit `unknown`, `unavailable`, `null` oder einem ungültigen State, gilt
  die Richtung als gesperrt;
- alle übrigen bestehenden Helfer behalten die derzeit dokumentierten Sicherheitsfallbacks.

Die Entlade-Sofort-Schwelle entfällt ersatzlos. Erhöhungen und normale Absenkungen der
Entladeanforderung laufen ausschließlich über `max_anderung_pro_schritt_w`; ein sicherheitsbedingter
Standby, ein ungültiger Sensor und ein Richtungswechsel dürfen weiterhin sofort `0 W` verlangen.
`min_anderung_pro_schritt_w` bleibt das Schreib-Totband. Bei fehlender Maximaländerung wird das
Ziel ohne Schrittbegrenzung erreicht. Ein gesunkenes gültiges WR-Limit darf nach der Rampe niemals
überschritten werden.

Die Energy-Pilot-Vorschläge `lade_max_w` und `entlade_max_w` werden nicht mehr gelesen und aus dem
HEMS-Gerätevertrag entfernt. Der Energy Pilot darf physische WR-Limits nicht überschreiben.
Andere bereits unterstützte Speicher-Vorschläge bleiben unverändert.

Der globale Helfer `input_number.ems_ac_speicher_entlade_abschlag_w` bleibt unverändert. Er wird
einmal vom gesamten Hausdefizit abgezogen, bevor dieses nach `entlade_prioritat` auf alle
entladebereiten Speicher verteilt wird. Er ist kein Wert pro Speicher.

## Zielarchitektur der Konfigurationsverwaltung

### Supervisor statt direktem Dateischreiben

`/data/options.json` darf weiterhin beim Prozessstart gelesen, aber niemals direkt beschrieben
werden. Die neue Oberfläche verwaltet dieselbe Optionsquelle wie die native Add-on-Seite über die
Supervisor-API:

- `GET http://supervisor/addons/self/info` zum Lesen der aktuellen Optionen;
- `POST http://supervisor/addons/self/options/validate` mit den rohen Optionsdaten;
- `POST http://supervisor/addons/self/options` mit `{ "options": ... }` zum Speichern;
- `POST http://supervisor/addons/self/restart` zum Neustarten.

Hierfür wird `config.yaml` um `hassio_api: true`, `hassio_role: default` und explizit
`panel_admin: true` erweitert. Die `self`-Endpunkte sind laut Supervisor-Sicherheitsvertrag für
das eigene Add-on freigegeben; eine weitergehende Manager- oder Admin-Rolle ist nicht nötig.

Offizielle Referenzen:

- <https://developers.home-assistant.io/docs/api/supervisor/endpoints/>
- <https://developers.home-assistant.io/docs/apps/configuration/>
- <https://github.com/home-assistant/supervisor/blob/main/supervisor/api/middleware/security.py>

### Backend-Aufteilung

Neue Verantwortlichkeiten nicht weiter in `app/main.py` stapeln:

1. `app/configuration.py`
   - Konstanten für unterstützte Modi und Formular-Defaults;
   - `normalize_options()` für abwärtskompatibles Lesen;
   - `validate_options()` mit Feldfehlern wie `devices[2].technical_maximum`;
   - Parser und stabiler Serializer für `available_modes` und `allowed_modes`;
   - Ermittlung gültiger und inaktiver Gerätekonfigurationen;
   - kanonischer Revisions-Hash über die rohen gespeicherten Optionen;
   - Diff der laufenden gegen die gespeicherte Gerätekonfiguration für die sichere Deaktivierung.
2. `app/supervisor_client.py`
   - eine langlebige `aiohttp.ClientSession`;
   - Bearer-Token ausschließlich aus `SUPERVISOR_TOKEN`;
   - Methoden `get_self_info`, `validate_self_options`, `save_self_options` und
     `restart_self`;
   - explizite Timeouts, Entpacken des Supervisor-Antwortformats und deutsche, bereinigte
     Fehlermeldungen ohne Token oder vollständigen Optionsdump.
3. `app/main.py`
   - Clients und Scheduler verdrahten;
   - neue HTTP-Handler registrieren;
   - geladene Startkonfiguration und deren Revision festhalten;
   - Write-Ergebnisse an den Controller zurückmelden;
   - Neustart erst nach vollständig ausgelieferter `202`-Antwort zeitversetzt anstoßen.
4. `app/ems/state.py`
   - prüfbare Präsenz-/Verfügbarkeitsmethoden ergänzen;
   - typisierte Resolver für Zahl, Boolean und Select bereitstellen oder eine ebenso zentrale
     Lösung schaffen;
   - keine geräteklassenspezifischen Defaultwerte in `StateProxy` verstecken.
5. `app/ems/controller.py` und `app/ems/devices.py`
   - nur bereits validierte Konfiguration verwenden;
   - Fallbackquelle und Entitätsdiagnosen je Zyklus sammeln;
   - Laufzeitaktivität vor der Pool-Verteilung als hartes Gate prüfen;
   - Schreiboperationen eindeutig einem Gerät zuordnen;
   - sicheren Ausgangszustand je Geräteklasse liefern.

Keine neue Python- oder Frontend-Abhängigkeit einführen. `hashlib`, `dataclasses`, React-State
und Context reichen aus.

### API-Vertrag der eigenen Oberfläche

Die genaue Benennung darf bei der Implementierung nur mit gleichwertiger Begründung abweichen.
Vorgesehen sind:

1. `GET /api/config`
   - liefert nur bekannte, für die UI bestimmte Optionsfelder;
   - liefert `stored_revision`, `loaded_revision`, `restart_required` und Fähigkeiten
     `can_save`/`can_restart`;
   - liefert serverseitige Feldfehler, Gerätevalidität und die unterstützten Moduswerte;
   - gibt keine unbekannten zukünftigen Felder und keine potenziellen Secrets an den Browser.
2. `GET /api/config/entities`
   - liefert eine reduzierte Liste `{entity_id, state, friendly_name, domain}` aus dem aktuellen
     HA-Schnappschuss;
   - unterstützt mindestens `sensor`, `switch` und `script`;
   - liefert keine kompletten, unnötigen Attribute.
3. `POST /api/config/validate`
   - validiert den UI-Entwurf ohne zu speichern;
   - antwortet mit `valid`, globalen Fehlern und einem Feldfehler-Dictionary.
4. `PUT /api/config`
   - erwartet den Entwurf und `stored_revision`;
   - prüft zuerst die eigene fachliche Validierung, danach Supervisor-Validierung;
   - vergleicht direkt vor dem Schreiben die Revision; bei Paralleländerung Antwort `409`;
   - mischt die bekannten UI-Felder in die frisch gelesenen rohen Optionen, damit unbekannte
     zukünftige Top-Level-Felder nicht verloren gehen;
   - antwortet mit neuer Revision und `restart_required: true`, startet aber nicht neu.
5. `POST /api/config/restart`
   - verwirft niemals still ungespeicherte Browserdaten; die UI bestätigt vorher;
   - liest die bereits gespeicherten Optionen, deaktiviert betroffene alte Ausgänge und stößt
     danach den Selbst-Neustart an;
   - antwortet vor dem Stoppen mit `202`.
6. `POST /api/config/save-and-restart`
   - führt Validierung und Revisionsprüfung wie `PUT /api/config` aus;
   - speichert zuerst, deaktiviert dann betroffene alte Ausgänge und startet zuletzt neu;
   - schlägt die sichere Deaktivierung fehl, bleibt die Konfiguration gespeichert, aber der
     Neustart wird nicht ausgelöst. Die Antwort muss diesen Teilstatus eindeutig benennen.

Fehlercodes: `400` für einen unlesbaren Request, `409` für einen Revisionskonflikt, `422` für
Feldvalidierung und `502`/`503` für Supervisor- oder HA-Ausfall. Fehlertexte für den User sind
deutsch; technische Details stehen bereinigt im Log.

Außerhalb des Add-on-Containers darf `GET /api/config` auf die lokal gelesene Konfiguration
zurückfallen. Speichern und Neustarten sind dann deaktiviert und werden in der UI verständlich
erklärt; niemals lokal so tun, als sei ein Supervisor-Schreibvorgang erfolgreich gewesen.

### Revisions- und Neustartverhalten

1. Der Revisions-Hash wird aus kanonischem JSON der rohen Supervisor-Optionen gebildet. Dadurch
   werden parallele Änderungen aus der nativen Add-on-Konfiguration erkannt.
2. `loaded_revision` bezeichnet den Stand, mit dem der laufende Controller instanziiert wurde.
   `stored_revision` bezeichnet den aktuell beim Supervisor gespeicherten Stand.
3. Die UI zeigt `restart_required`, wenn beide abweichen.
4. Nach ausgelöstem Neustart zeigt die UI einen nicht interaktiven Neustartzustand und pollt den
   relativen API-Pfad, bis eine neue Prozessinstanz erreichbar ist. Eine beim Start erzeugte
   `instance_id` im Status verhindert, dass eine sehr kurze Unterbrechung fälschlich als
   abgeschlossener Neustart gewertet wird.
5. Vor einem Neustart werden die alte Startkonfiguration und die gespeicherte Zielkonfiguration
   verglichen:
   - gelöschte oder in irgendeinem Feld geänderte Altgeräte werden über ihre alten Schreibziele
     sicher deaktiviert;
   - Änderungen an `residual_power_entity`, `speicher_in_residual_enthalten` oder
     `available_modes` deaktivieren vorsorglich alle alten Geräte;
   - reine Änderungen an Log-Level, Intervall oder Post-Cycle-Skript benötigen keine vorherige
     Ausgangsänderung.
6. Sichere Alt-Ausgaben:
   - `controllable`: Anforderung `0`;
   - `binary`: Anforderung `off`;
   - `battery`: zuerst signierte Leistung `0`, danach Betriebsart `standby`.
7. Schlägt eine erforderliche sichere Ausgangsänderung fehl, wird nicht neu gestartet. Das ist
   absichtlich strenger als der normale Regelzyklus.

## Umsetzungsschritte

### 1. Ist-Verhalten mit Charakterisierungstests absichern

- Vor dem Umbau die bestehende Testsuite ausführen und den Ausgangsstand notieren.
- Tests für die aktuelle `allowed_modes`-Migration `auto` → `manuell`, gültige Nullwerte,
  fehlende Entitäten und `unknown`/`unavailable` ergänzen, soweit sie für den Umbau als
  Regression dienen.
- Keine Tests löschen, nur weil der neue Code sie zunächst rot macht. Fachlich bewusst entfernte
  Funktionen werden im späteren Schritt durch neue Zusicherungen ersetzt.

### 2. Zentrales Konfigurationsmodell und Validierung bauen

- `app/configuration.py` mit kleinen, reinen Funktionen und typisierten Ergebnissen anlegen.
- Globale, gemeinsame und klassenspezifische Feldvalidierung implementieren.
- Geräte-ID und effektiven Prefix jeweils auf Eindeutigkeit prüfen.
- Leere `allowed_modes` ausdrücklich erhalten; fehlendes Feld nur für die Migration auf
  `manuell` normalisieren.
- Bestandsoptionen ohne `available_modes` ohne Verhaltensänderung auf alle drei Modi abbilden.
- Heterogene Geräteobjekte nicht allein dem Supervisor-Schema überlassen: Das Manifest kann je
  Klasse keine unterschiedlichen Pflichtfelder ausdrücken. Die Anwendung ist die autoritative
  bedingte Validierung.
- `_build_devices()` so umbauen, dass nur validierte Einträge instanziiert werden und Fehler als
  strukturierte `inactive_devices` erhalten bleiben statt nur im Log zu verschwinden.

### 3. Add-on-Schema, Defaults und Beispiele erweitern

- `config.yaml` um `hassio_api`, `hassio_role`, `panel_admin`, `available_modes` und alle neuen
  Gerätefelder erweitern.
- Klassenspezifische Felder im gemischten Supervisor-Listenschema optional lassen, wenn eine
  Pflichtmarkierung alle anderen Klassen ungültig machen würde. Im Code und in der UI sind sie
  trotzdem wie oben beschrieben verpflichtend.
- Beispielgeräte auf `manuell` statt des veralteten `auto` in `allowed_modes` umstellen und die
  neuen Pflicht-Fallbacks vollständig eintragen.
- Batterie-Beispiel mit verpflichtenden `available_*_w`-Werten und den Defaults `2`/`5`
  ergänzen.
- `translations/de.yaml` und `translations/en.yaml` aktualisieren. Deutsche UI-Texte bleiben
  deutsch; die englische Manifest-Übersetzung beschreibt denselben Vertrag.

### 4. State-Auflösung und Entitätsdiagnose zentralisieren

- `StateProxy` um eine Präsenzprüfung erweitern; `get()` allein kann fehlend und vorhandenes
  `null` nicht unterscheiden.
- Numerische Werte auf `math.isfinite` prüfen.
- Einen gemeinsamen Resolve-Vertrag einführen, der Wert, Zustand und Quelle zurückgibt.
- Die Resolver in globalen Eingaben, `Device`, `ControllableDevice`, `BinaryDevice` und
  `BatteryDevice` einsetzen.
- Jeden in diesem Plan genannten Fallback explizit testen, jeweils mindestens mit:
  gültigem HA-Wert, gültigem HA-Nullwert, fehlender Entität, `unavailable`, `unknown` und
  nicht numerischem Wert.
- Fallback-Diagnosen am Zyklusanfang leeren und danach im Status serialisieren.

### 5. Fallbackfelder für `controllable` und `binary` anschließen

- Neue Konstruktorparameter mit englischen Namen an die Geräteklassen geben.
- Reihenfolge immer: gültiger HA-State → Add-on-Fallback. Der Add-on-Wert ist auch bei
  `missing`, `unavailable` und `invalid` wirksam; die Diagnose bleibt verschieden.
- Einheit des `controllable`-Fallbacks an `output_unit` koppeln und erst danach wie bisher in
  Watt umrechnen.
- `phase_switch_delay_s` behält die bestehende eigene Kette HA → Add-on → interner Default.
- Geräte mit unvollständigen Pflicht-Fallbackfeldern nicht registrieren und in
  `inactive_devices` ausgeben.
- Status- und Kontrollschema um die Fallbackquelle ergänzen, ohne die vorhandenen semantischen
  EP-Schlüssel umzubenennen.

### 6. Speichervertrag vereinfachen

- Konstruktor und Registry auf verpflichtende `available_*_w`-Werte sowie die beiden neuen
  statischen Felder umstellen.
- HA-Lesen, Attribute, Sperrgründe, SoC-Latch, Grenzberechnung, Rampe und Status von
  `soc_reserve`, `soc_taper`, HA-Hysterese, HA-Umschaltzeit und Entlade-Sofort-Schwelle bereinigen.
- SoC-Latch mit `soc_max_hysteresis_percent` aus der Add-on-Konfiguration weiterführen.
- Entladeboden nur noch aus `soc_min_prozent` bilden.
- Kein lineares SoC-Taper mehr anwenden. Innerhalb der SoC-Grenzen ist das konfigurierte
  `available_*_w`-Limit maßgeblich; an der Grenze wird die Richtung `0`.
- Lade- und Entladelimit getrennt validieren; `0` sperrt nur die jeweilige Richtung.
- `laden_erlaubt`/`entladen_erlaubt` mit der besonderen Missing-/Unavailable-Regel umsetzen.
- Batterie-Reserve mit fehlend = `50`, aber vorhandenem `0` = `0` umsetzen.
- `max_anderung_pro_schritt_w` intern ohne magischen sehr großen Zahlenwert als optionales Limit
  modellieren; kein `Infinity` in JSON ausgeben.
- Entladerampe ohne Sofort-Schwelle neu formulieren. Sicherer Standby, Sensorfehler und
  Richtungswechsel bleiben unmittelbare Sicherheitsklemmen.
- Die EP-Felder `lade_max_w` und `entlade_max_w` weder lesen noch im Geräteschema anbieten.
- Die reservierte Netzlade-Schnittstelle nicht nebenbei freigeben oder neu entwerfen; B-4 bleibt
  außerhalb dieses Auftrags bestehen.

### 7. Schreibziel-Gesundheit und Fehlerbehandlung implementieren

- Vor der Allokation die erforderlichen Schreibziele im HA-Schnappschuss prüfen.
- `input_select`-Optionen und beim Batterie-Sollwert das negative Minimum aus den Attributen
  validieren.
- Write-Ops um Besitzer/Geräte-ID erweitern, beispielsweise durch eine kleine Dataclass statt
  anonymer Tupel. Fachlogik bleibt in den Geräten, HTTP in `HAClient`.
- `HAClient.execute_write_ops()` gibt pro Operation Erfolg oder bereinigten Fehler zurück und
  verschluckt Nicht-2xx nicht mehr.
- Der Controller merkt sich pro Gerät den Write-Fehler, setzt `runtime_active` auf `false` und
  versucht in Folgezyklen ausschließlich den sicheren Zustand, bis die Ziele wieder funktionieren.
- Der globale Zyklusstatus darf bei einem einzelnen Gerätefehler die anderen Geräte nicht als
  fehlgeschlagen behandeln.
- B-2 nach grünen Regressionstests aus `docs/bekannte-luecken.md` entfernen.

### 8. Supervisor-Client und Konfigurations-API implementieren

- `SupervisorClient` wie im Architekturabschnitt umsetzen und in `HEMSApp` sauber schließen.
- Niemals Token, Header oder rohe Optionen loggen.
- Neue API-Handler dünn halten; Validierung, Merge, Revision und Diff liegen in
  `configuration.py`.
- Supervisor-Validierung immer vor dem Speichern ausführen.
- Revisionskonflikt unmittelbar vor dem Speichern erneut prüfen.
- Sichere Deaktivierungsoperationen aus der laufenden Alt-Konfiguration ableiten, nicht aus dem
  bereits bearbeiteten Entwurf.
- Neustart in einer Hintergrundaufgabe erst nach der `202`-Antwort anstoßen.
- Einen lokalen Nur-Lese-Modus ohne Supervisor implementieren und testen.

### 9. Frontend-Datenverträge und Navigation erweitern

- `web/src/types.ts` um Konfigurations-, Validierungs-, Revisions-, Diagnose- und
  `inactive_devices`-Typen erweitern. Kein `any` verwenden.
- `web/src/api.ts` als einzigen `fetch`-Ort um benannte Methoden für alle neuen Endpunkte
  erweitern.
- In `web/src/App.tsx` die Konfigurationsrouten ergänzen.
- In `web/src/components/Layout.tsx` einen Navigationspunkt **Konfiguration** mit passendem Icon
  aus dem eigenen Icon-Set ergänzen.
- Für gemeinsam gehaltenen Konfigurationsentwurf React-Context oder einen lokalen Provider der
  Konfigurationsrouten verwenden; kein State-Paket einführen.

Empfohlene Routen:

```text
#/konfiguration/global
#/konfiguration/geraete
#/konfiguration/geraete/neu
#/konfiguration/geraete/:index
```

Anlegen und Bearbeiten verwenden dasselbe Formular mit `mode: 'create' | 'edit'`. Der Index ist
nur die Entwurfsposition; die fachliche Identität bleibt `name`.

### 10. Konfigurationsseiten bauen

- Globale Seite mit den sechs globalen Feldern und Modus-Checkboxen.
- Geräteliste mit Klasse, Name, Label, Prefix, erlaubten Modi, Validität, Laufzeitstatus,
  Bearbeiten, Löschen und Hoch/Runter-Aktionen.
- Gemeinsames Geräteformular mit bedingten Bereichen je Klasse und den oben festgelegten
  Startwerten.
- Entity-Suche als zugängliches Combobox-/Datalist-Muster ohne neue UI-Bibliothek. Domainfilter:
  Sensorfelder `sensor`, Schaltzustand `switch`, Post-Cycle-Skript `script`.
- Abgeleitete HA-Helfer samt Status `vorhanden`, `fehlt`, `nicht verfügbar`, `ungültig` oder
  `Schreiben fehlgeschlagen` lesbar anzeigen. Entity-IDs in Monospace darstellen.
- Pflichtfelder am Label markieren und Server-Feldfehler direkt am Feld anzeigen.
- Bei leerem `allowed_modes` die Kennzeichnung **Nur Energy Pilot** anzeigen.
- Sticky Aktionsbereich mit **Speichern**, **Neu starten** und
  **Speichern und neu starten**. Nur die kombinierte Standardaktion ist Primärbutton; die beiden
  anderen sind klar sichtbare Nebenaktionen.
- Lade-, Leer-, Fehler-, Konflikt-, Speichern-, Neustart- und Supervisor-nicht-verfügbar-Zustand
  vollständig umsetzen.
- Bei `409` den Entwurf nicht verwerfen: erklären, dass die Add-on-Konfiguration zwischenzeitlich
  geändert wurde, und gezieltes Neuladen anbieten.
- Nach Neustart anhand der neuen `instance_id` Erfolg erkennen und Konfiguration/Status neu laden.

Wächst eine Seite über etwa 150 Zeilen, Formularabschnitte und Aktionsleiste unter
`web/src/components/` auslagern. Alle Gestaltung bleibt in `web/src/styles.css`, ausschließlich
mit vorhandenen Tokens oder begründet ergänzten Klassen. Keine gestaltenden Inline-Styles und
keine Literalfarben im TSX.

### 11. Bestehende Status- und Steuerungsseiten anpassen

- `web/src/pages/Status.tsx` um Konfigurations-/Laufzeit-Inaktivität und konkrete Gründe
  erweitern. `eligible: false` bleibt eine aktuelle Freigabeentscheidung und darf nicht mit einer
  ungültigen Konfiguration gleichgesetzt werden.
- Inaktive, beim Start übersprungene Geräte separat ohne erfundene Leistungs-, SoC- oder
  Schaltwerte darstellen.
- Speicherkarte und `BatteryDevice`-Type von Notstromreserve und Taper bereinigen; SoC-Balken nur
  noch mit Minimum und Maximum.
- Sperrgrund `soc_reserve` aus der UI entfernen.
- `web/src/pages/Steuerung.tsx` zeigt keine entfernten Speicher-Helfer mehr. Optionale Helfer mit
  Add-on-Fallback bekommen eine lesbare Kennzeichnung, welcher Wert gerade wirkt.
- Das Energy-Pilot-Frontend darf entfernte Maximalvorschläge nicht mehr als wirksam darstellen;
  verwaiste HA-Sensoren können weiterhin gespiegelt werden, müssen aber anhand des aktuellen
  Schemas ausgeblendet werden.

### 12. Tests aktualisieren und erweitern

Mindestens folgende Testgruppen sind erforderlich:

1. `tests/test_configuration.py` neu:
   - Normalisierung alter Modi;
   - leerer `allowed_modes`-String bleibt leer;
   - globale Teilmenge und Entfernen deaktivierter Modi;
   - eindeutige Namen und Prefixe;
   - bedingte Pflichtfelder jeder Klasse;
   - genaue Batterie-Sensorvarianten;
   - Feldpfade und deutsche Fehlermeldungen;
   - stabiler Revisions-Hash und Konflikterkennung;
   - Diff für sichere Altgeräte-Deaktivierung.
2. `tests/test_state.py`:
   - `missing`, `unavailable`, `unknown`, `invalid`, `valid` und gültige Null;
   - NaN und unendliche Werte sind ungültig.
3. `tests/test_controllable_device.py`:
   - jeder der sechs HA-Werte gewinnt bei Gültigkeit;
   - fehlend und unavailable verwenden denselben Add-on-Wert, aber verschiedene Diagnose;
   - Ampere-Fallback wird korrekt in Watt umgerechnet;
   - vorhandene Nullwerte werden nicht überschrieben.
4. `tests/test_binary_device.py`:
   - dieselbe Matrix für alle fünf Felder;
   - Zeit- und Hystereseschutz bleiben unverändert.
5. `tests/test_battery_device.py`:
   - keine HA-Maximalleistungs-, Reserve-, Taper-, Hysterese-, Speicher-Umschaltzeit- oder
     Sofortschwellen-Abfrage mehr;
   - beide `available_*_w`-Limits begrenzen korrekt und unabhängig;
   - fehlend, negativ oder nicht endlich macht die Konfiguration ungültig;
   - Limit `0` sperrt nur die jeweilige Richtung;
   - SoC-Grenzen ohne Taper und ohne Reserve;
   - Config-Hysterese `2` und Config-Umschaltzeit `5`;
   - `laden_erlaubt`/`entladen_erlaubt`: Entity fehlt → an, Entity unavailable → aus;
   - Reserve fehlt → `50`, vorhandene `0` → `0`;
   - Maximaländerung fehlt → unbegrenzt, vorhanden → in beiden Richtungen eingehalten;
   - Sofort-Stopp bei Sicherheitsgründen;
   - nach Rampenberechnung nie über einem konfigurierten Leistungslimit;
   - EP-Maximalvorschläge werden ignoriert.
6. `tests/test_controller.py` und `tests/test_run_cycle.py`:
   - global deaktivierter Modus setzt sicher inaktiv;
   - EP-only-Gerät;
   - unvollständige Config erscheint in `inactive_devices` und beeinflusst Pool nicht;
   - fehlendes beziehungsweise nicht verfügbares Schreibziel verhindert Zuteilung;
   - Write-Fehler markiert nur das betroffene Gerät;
   - repariertes Ziel kann über sicheren Retry wieder aktiv werden;
   - sicherer Zustand des Speichers wird weiter aktiv geschrieben;
   - globaler Entlade-Abschlag bleibt genau einmal systemweit wirksam.
7. `tests/test_device_schema.py` und `tests/test_ep_uebernahme.py`:
   - neue Fallback-/Diagnosemetadaten;
   - `available_modes` und leere `allowed_modes`;
   - entfernte Batterie-Items und EP-Maximalvorschläge fehlen;
   - verbleibender Vertrag bleibt additiv kompatibel.
8. Supervisor-/API-Hilfslogik mit Fake-Client testen:
   - Lesen, Validieren, Speichern, `409`, lokale Nur-Lese-Fähigkeiten;
   - Speichern startet nicht neu;
   - Restart speichert nicht;
   - Save-and-Restart hält die Reihenfolge ein;
   - fehlgeschlagene sichere Deaktivierung verhindert den Neustart;
   - Optionen oder Token erscheinen nicht in Fehlern/Logs.

Property-Tests in `tests/test_allocation_properties.py` an den neuen Speichervertrag anpassen.
Die Invarianten „Entladung erhöht den Pool nicht“, „Hausdefizit enthält keine HEMS-Last“,
„Laden und Entladen nie gleichzeitig“ und „ohne Speicher unverändert“ bleiben Pflicht.

### 13. Dokumentation und Entscheidungen nachziehen

Nach grüner Implementierung den alten Ist-Stand nicht in `docs/` stehen lassen:

- `docs/device_classes/global.md`
- `docs/device_classes/controllable.md`
- `docs/device_classes/binary.md`
- `docs/device_classes/battery.md`
- `docs/konfiguration.md`
- `docs/datenmodell.md`
- `docs/api-referenz.md`
- `docs/architektur.md`
- `docs/frontend.md`
- `docs/design-system.md`, falls Klassen ergänzt werden
- `docs/sicherheit-datenschutz.md`
- `docs/test-strategie.md`
- `docs/bekannte-luecken.md`
- `docs/roadmap.md`
- `docs/README.md`, falls neue Referenzdateien entstehen

Besonders zu korrigieren:

- bisherige Aussage, nur `phase_switch_delay_s` sei ein echter Add-on-Fallback;
- alle entfernten Speicher-Helfer, Taper-, Reserve- und Sofortschwellen-Erklärungen;
- Bedeutung der verpflichtenden direkten `available_*_w`-Werte;
- globale Modi, EP-only-Geräte und `available_modes`;
- Supervisor als einzige Schreibschnittstelle der Add-on-Optionen;
- neue API-Endpunkte, Revisionen und Neustartverhalten;
- `SUPERVISOR_TOKEN` wird danach auch in `supervisor_client.py` gelesen;
- B-2 nach seiner Behebung;
- F-12 darf nicht mehr auf die entfernte Entlade-Sofort-Schwelle verweisen;
- die genaue, einmalige Wirkung des globalen Entlade-Abschlags;
- die Konfigurationsseite als Ersatz für die alleinige YAML-Bedienung, ohne die native Seite als
  zweite Datenquelle darzustellen.

Die geänderten Grundsatzentscheidungen erhalten neue Einträge in
`docs/design-entscheidungen.md` und bei Bedarf ADRs:

1. vereinfachter Speichervertrag: physische Maxima nur aus `available_*_w`, kein SoC-Taper, keine
   Notstromreserve im HEMS und keine Entlade-Sofort-Schwelle;
2. Supervisor-gestützte Add-on-Konfigurationsseite mit Revisionsschutz, ohne eigene Persistenz.

Die Historie von D-040 nicht löschen. Geänderte Teile nachvollziehbar auf die neue Entscheidung
verweisen. `CHANGELOG.md` erhält im selben Arbeitspaket Einträge unter `Unreleased`, inklusive
Migration und entfallener Helfer.

Da neue Pflichtfelder Bestandskonfigurationen bis zur Ergänzung inaktiv machen können und der
Speichervertrag Felder entfernt, ist dies eine brechende Konfigurationsänderung. Gemäß
`docs/git-workflow.md` ist vor dem Release eine MAJOR-Anhebung vorzusehen; die konkrete
Release-Version und das Release-Datum nicht außerhalb des vorgesehenen Release-Ablaufs erfinden.

### 14. Technische und visuelle Abnahme

Pflichtbefehle:

```bash
pytest -q
ruff check app tests
cd web && npm run build
```

Das erzeugte Bundle unter `app/static/` gehört in denselben Commit.

Danach die laufende Oberfläche im Browser prüfen:

- Desktop und 375 px Breite;
- heller und dunkler Modus;
- globale Modi aktivieren/deaktivieren;
- Gerät aller drei Klassen anlegen und bearbeiten;
- EP-only-Gerät;
- fehlende Pflichtfelder und fehlende Entity-ID;
- Entity-Suche und gespeicherte, aktuell nicht vorhandene Entity-ID;
- Speichern ohne Neustart samt Hinweis;
- Neustart mit ungespeicherten Änderungen;
- Speichern und Neustarten samt Wiederverbindung;
- Revisionskonflikt;
- Supervisor lokal nicht verfügbar;
- inaktives Gerät wegen fehlendem oder nicht beschreibbarem Sollwert-Helfer.

Vor dem Commit `git status`, `git diff` und `git diff --staged` prüfen, gezielt stagen, eine
deutsche Conventional-Commit-Message verwenden und ausschließlich nach `claude/main` pushen.

## Abnahmekriterien

Die Aufgabe ist erst abgeschlossen, wenn alle folgenden Aussagen nachweislich stimmen:

1. Gültige HA-Werte haben Vorrang; fehlende und nicht verfügbare Entitäten sind unterscheidbar
   und verwenden den festgelegten Add-on- oder internen Fallback.
2. `controllable` und `binary` besitzen alle vereinbarten verpflichtenden Add-on-Fallbackfelder;
   unvollständige Geräte laufen nicht unbemerkt mit Nullwerten.
3. Der Speicher nutzt keine entfernten HA-Helfer oder EP-Maximalvorschläge mehr.
4. Beide momentanen Speicherlimits sind verpflichtend, getrennt ausfallsicher und niemals durch
   einen EP-Wert überschreibbar.
5. SoC-Reserve, SoC-Taper und Entlade-Sofort-Schwelle haben weder im Code noch in Status, UI,
   Kontrollschema oder aktueller Dokumentation eine Wirkung.
6. Der globale Entlade-Abschlag wird weiterhin genau einmal auf das gemeinsame Entladeziel
   angewandt.
7. Leere `allowed_modes` sind ein unterstütztes EP-only-Gerät; globale und gerätespezifische
   Modusauswahl funktionieren über Checkboxen und werden kompatibel als Strings gespeichert.
8. Fehlende oder nicht beschreibbare Sollwert-Helfer machen nur das betroffene Gerät sichtbar
   inaktiv; andere Geräte regeln weiter.
9. Die native Add-on-Konfiguration und die neue UI schreiben dieselbe Supervisor-Optionsquelle.
   Es gibt keine neue Konfigurationsdatei und kein direktes Schreiben nach `/data/options.json`.
10. Die drei Aktionen Speichern, Neu starten und Speichern und neu starten haben exakt die
    beschriebenen, getrennten Wirkungen.
11. Vor relevanten Neustarts werden alte Ausgänge sicher deaktiviert; bei Fehlschlag wird der
    Neustart nicht ausgelöst.
12. Revisionskonflikte überschreiben keine fremde Änderung.
13. Tests, Ruff und Frontend-Build sind grün, das Bundle ist aktuell und die UI wurde in beiden
    Themes und mobil geprüft.
14. `docs/`, `CHANGELOG.md`, Manifest-Übersetzungen und bekannte Lücken stimmen mit dem fertigen
    Code überein.

## Nicht Bestandteil dieses Auftrags

- Anlegen oder Bearbeiten von HA-Helfern durch das Add-on;
- Direktsteuerung realer Geräte statt Schreiben der vorhandenen `input_*`-Helfer;
- frei definierbare neue Regelmodi ohne implementierte Fachlogik;
- Freigabe oder Vervollständigung des zurückgestellten Netzladens;
- Einführung einer Datenbank oder einer eigenen Konfigurationsdatei;
- automatische Migration realer HA-Helfer oder Löschung verwaister HA-Entitäten;
- Behebung anderer, nicht unmittelbar berührter bekannter Lücken wie B-1 oder B-3.
