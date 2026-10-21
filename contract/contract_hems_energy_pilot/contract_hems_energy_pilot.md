# Vertrag: SkytechHEMS ↔ Skytech Energy Pilot

**Version:** 2.0

**Status:** Dokumentierter Implementierungsstand mit bekannten Kompatibilitätsgrenzen; Schnittstellen-Entität `sensor.energy_pilot_schnittstelle` in beiden Projekten **implementiert**

**Stand:** 20.10.2026

**Geprüfte Codebasis:** SkytechHEMS `e5c0156`, Skytech-Energy-Pilot `e08e211`; Schnittstellen-Entität: SkytechHEMS D-070, Energy Pilot D-069.

Dieser Vertrag beschreibt den tatsächlich vorhandenen Austausch. Er führt keine neuen
Laufzeitfunktionen ein. Einseitig implementierte Fähigkeiten und bekannte Abweichungen stehen
ausdrücklich im Abschnitt „Kompatibilitätsgrenzen“ und gelten nicht als gemeinsame Zusage.

Die Datei liegt wortgleich in beiden Repositories unter
`contract/contract_hems_energy_pilot/contract_hems_energy_pilot.md`. Änderungen am Austausch
müssen in beiden Kopien im selben Arbeitspaket dokumentiert werden. Projektregeln bleiben
übergeordnet; für die Schnittstellenbeschreibung ist dieser Vertrag maßgeblich.

## Zweck und Architekturgrenze

Energy Pilot (EP) plant vorausschauend. SkytechHEMS regelt lokal und entscheidet anhand seiner
Freigaben, Messwerte, Grenzen, Prioritäten und Schutzzeiten über die tatsächlichen Geräteausgaben.
Ein EP-Vorschlag ist weder ein direkter Gerätesollwert noch eine garantierte Leistungszuteilung.

```text
Energy Pilot ── GET Schema und Status ──► SkytechHEMS
Energy Pilot ◄── Gerätebeschreibung und Regelstatus ── SkytechHEMS
Energy Pilot ── sensor.energy_pilot_schnittstelle ──► Home Assistant ──► SkytechHEMS
Energy Pilot ◄── States der im Schema genannten Entitäten ── Home Assistant
```

**Grundsatz (seit 2.0):** Jede Einheit veröffentlicht genau eine Entität
`sensor.<einheit>_schnittstelle` mit allen Informationen für die anderen Teilnehmer (siehe
`contract/README.md`). EP schreibt seine Vorschläge für das HEMS deshalb ausschließlich in
`sensor.energy_pilot_schnittstelle` über die HA-State-API. HEMS liest sie aus seinem
Zyklus-Schnappschuss und schreibt seine `input_*`-Ausgabehelfer selbst. Die Richtung HEMS → EP
bleibt bewusst REST (Schema und Status sind groß und werden nur bei Bedarf gelesen; dokumentierte
Ausnahme). Der gesonderte EP-Original-Schreibweg für konfigurierte Zusatz-Entitäten ist unten als
Ausnahme beschrieben.

## Bezeichner und Konfiguration

| Bezeichner | Bedeutung |
|---|---|
| `name` | Stabile technische Geräte-ID aus der HEMS-Konfiguration; EP-Pläne benutzen sie als `devices[].name`. |
| `label` | Änderbarer Anzeigename; keine verbindliche technische Identität. |
| `<prefix>` | HEMS `devices[].entity_prefix`, standardmäßig `name`; bestimmt die Helfer- und Vorschlagsnamen. |
| `hems_base_url` | In EP konfigurierte Basisadresse der erreichbaren HEMS-HTTP-API. |
| `W`, `A`, `%` | Watt, Ampere beziehungsweise Prozent; Werte werden nicht still zwischen Einheiten umgedeutet. |

EP und HEMS müssen dieselbe Home-Assistant-Zustandsmaschine verwenden. EP benötigt zusätzlich
HTTP-Zugriff auf HEMS. Der vorhandene HEMS-Client verwendet einen Standardtimeout von zehn
Sekunden und keine eigene Authentifizierung gegenüber HEMS. Ein Ingress-Browserpfad ist kein
zusätzlich vereinbartes Austauschprotokoll.

## HEMS → EP: Geräte- und Steuerschema

`GET /api/device_controls_schema` liefert eine JSON-Liste: zuerst die globale Gruppe, danach
die konfigurierten Geräte. Es gibt keinen umschließenden `devices`-Container.

| Feld | Vorkommen | Bedeutung |
|---|---|---|
| `name`, `label`, `items` | alle Gruppen | Identität, Anzeige und Liste der Eingabefelder. |
| `schema_version` | globale Gruppe | Aktuell ganze Zahl `2`; unabhängig vom EP-Plan-Schema. |
| `control_policy` | global und Geräte | Aktuell `pv_surplus_only`; Regelprinzip, keine Garantie für jede Betriebsart oder Zwangsanforderung. |
| `residual_power_entity` | globale Gruppe | Konfigurierter Überschuss-Sensor. |
| `battery_residual_power_entity` | globale Gruppe | Separate Hausleistungsbilanz für AC-Speicher. |
| `interval_s` | globale Gruppe | HEMS-Regelintervall in Sekunden. |
| `class`, `entity_prefix`, `allowed_modes` | Geräte | Geräteklasse, Namenspräfix und erlaubte normale Regelmodi. |
| `output_unit`, `request_entity` | Geräte | Native Sollwerteinheit und vollständige HEMS-Ausgabe-Entity-ID. |
| `actual_power_entity` | `controllable` | Istleistung in Watt, auch bei Ampere-Ausgabe. |
| `phase_entity`, `allowed_phases`, `voltage_entities` | `controllable` | Phasenhelfer, mögliche Phasenzahlen und konfigurierte Spannungssensoren; leere Verweise sind möglich. |
| `switch_entity` | `binary` | Tatsächlicher Schaltzustand. |
| `soc_entity`, `charge_power_entity`, `discharge_power_entity`, `power_entity`, `power_sign` | `battery` | Messwertzuordnung des Speichers. |
| `available_charge_power_w`, `available_discharge_power_w`, `capacity_kwh` | `battery` | Konfigurierte Zahlenwerte, keine Entity-IDs. |
| `mode_entity`, `request_sign` | `battery` | Betriebsart-Ausgabe und `positiv_laden` für den signierten Sollwert. |

Jedes `items[]`-Objekt enthält `entity`, `label`, `key`, `kind`, `role` und
`planning_relevant`, gegebenenfalls `unit`. HEMS ergänzt `internal_editable` sowie je nach Typ
`min`, `max`, `step`, `integer` oder `options`. Das Schema beschreibt Eingaben; diese Attribute
sind keine aktuellen Mess- oder Ersatzwerte.

EP übernimmt stabile Metadaten aus dem Schema und liest die benannten States direkt aus HA.
Nur als `planning_relevant` markierte Schemafelder gehen als solche in den Planungskontext.
EP ergänzt außerdem Felder für HEMS-Anforderung, tatsächliche Leistung beziehungsweise
Schaltzustand. Für ältere Schemaformen existieren Suffixheuristiken; beim aktuellen Schema
sind die expliziten Entity-IDs und Metadaten maßgeblich.

Bei fehlgeschlagener Discovery gibt es keinen Ersatz durch eine statische EP-Geräteliste.
Beim Start bestehen begrenzte Wiederholungen und ein manueller Re-Sync. Eine automatische
laufende Übernahme jeder HEMS-Konfigurationsänderung wird nicht zugesagt.

## HEMS → EP: Regelstatus

`GET /api/status` liefert ein Objekt mit `status`, `last_cycle_at`, `last_cycle_at_iso`,
`cycle_count`, `error` und `interval_s` sowie zusätzlichen Diagnosefeldern wie `emergency`.
`status.devices` ist eine Liste; `id` entspricht dem technischen HEMS-Gerätenamen.

| Felder | Bedeutung für EP |
|---|---|
| `status.ems_enabled`, `global_mode`, `hard_lockout` | Zustand und Steuerquelle der Regelung. |
| `status.pool_w`, `current_deficit_w`, `residual_bereinigt_w` | Verbraucherpool und bereinigte Netzbilanz. |
| `status.battery_residual_bereinigt_w`, `hausdefizit_w` | Gesonderte AC-Speicherbilanz; kein Ersatz für den Verbraucherpool. |
| Geräte: `priority` | Wirksame Priorität für den Vergleich mit `prio_vorschlag`. |
| Geräte: `geschuetzte_mindestleistung_w` beziehungsweise `_a` | Roher wirksamer Schutzsockel; Vergleichswert für den Vorschlag. |
| Geräte: `eligible`, `source`, `freigabe`, `technische_freigabe` | Wirksame Freigabesituation; `eligible` enthält mehr Gates als der EP-Freigabevorschlag. |
| Geräte: `runtime_active`, `inactive_reasons`, `write_error`, `ep_proposal_status` | Geräte- und Vorschlagsdiagnose. |

`schutz_w` beziehungsweise `schutz_a` enthalten zusätzliche Reserven und sind deshalb kein
Ersatz für den rohen Schutzsockel. EP ergänzt einen fehlenden Rohwert bei älteren HEMS-Ständen
hilfsweise aus dem zugehörigen HA-Helfer; ein vorhandener HEMS-Statuswert hat Vorrang.

Die Plan-Rückkopplung vergleicht Priorität, Schutzsockel und Freigabe. Ein freigegebener
EP-Vorschlag bei `eligible: false` beweist keine fehlerhafte Übernahme: ein anderes HEMS-Gate
kann sperren. Die aktuelle Zuordnung im Feedback toleriert zusätzlich normalisierte Labels;
für neue Zuordnungen bleibt die technische Geräte-ID maßgeblich.

Der Collector setzt `online` bei erfolgreichem HTTP-Abruf. Das ist keine Garantie für einen
frischen Regelzyklus. Während einer HEMS-Notabschaltung können `status` und `cycle_count` den
letzten Zyklus davor zeigen. EP besitzt derzeit keine eigene umfassende Auswertung des
`emergency`-Objekts für diese Rückkopplung.

`GET /api/controls` existiert ebenfalls im EP-Client, wird im regulären Collector-Pfad aber
nicht verwendet. Es liefert HA-Helferzustände, keine HEMS-internen Ersatzwerte.

## EP → HEMS: `sensor.energy_pilot_schnittstelle`

Status: **Implementiert** — EP D-069 (`suggestion_publisher.py`), HEMS D-070 (`app/ems/devices.py`).

| Feld | Typ | Bedeutung |
|---|---|---|
| `state` | Text | `entity_prefix` aller Geräte mit mindestens einem Vorschlag, durch Komma getrennt. |
| `attributes.schnittstelle_version` | Ganzzahl | `1`. |
| `attributes.plan_id` | Text | Kennung des Plans. |
| `attributes.valid_from`, `valid_until` | Text | ISO-8601-Zeitstempel mit Zeitzone; Gültigkeitsfenster aller Vorschläge. |
| `attributes.schema_version` | Text | Version des EP-Plan-Schemas; keine Versionsprüfung im HEMS. |
| `attributes.<prefix>_label` | Text | Anzeigename des Geräts; nur Anzeige. |
| `attributes.<prefix>_<feld>` | Zahl oder Bool | Ein Vorschlag. `<feld>` ist der HEMS-Feldname ohne `_vorschlag`. |

Felder je Gerätekonstellation:

| Gerätekonstellation | EP liefert regulär | Aktuelle HEMS-Übernahme |
|---|---|---|
| `binary`, normales Präfix | `prio`, `freigabe` | Beide Felder bei Quelle `ep`. |
| `controllable`, Watt, normales Präfix | `prio`, `freigabe`, `geschutzte_mindestleistung_w` | Alle drei Felder bei Quelle `ep`. |
| `controllable`, Ampere, normales Präfix | `prio`, `freigabe`, `geschutzte_mindestleistung_a` | Nur `prio` und `freigabe`; der Ampere-Schutzvorschlag wird derzeit nicht gelesen. |
| EP-Sonderfall Präfix `batterie` | Nur `geschutzte_mindestleistung_w`; EP behandelt Priorität 1 und Freigabe als feste Planungsannahmen. | Nicht gleichbedeutend mit HEMS-Geräteklasse `battery`; keine pauschale Kompatibilitätszusage. |
| HEMS-Geräteklasse `battery` | Kein vollständiger, ausdrücklich implementierter EP-Pfad. | HEMS kann sieben Felder lesen; EP liefert diesen Satz derzeit nicht. |

Die sieben HEMS-seitigen Speicherfelder sind `freigabe`, `prio`,
`geschutzte_mindestleistung_w`, `entlade_prio`, `soc_ziel_prozent`, `soc_min_prozent` und
`betriebsart`. Bei `betriebsart` sind `auto`, `nur_laden`, `nur_entladen`, `standby` zulässig.
Physische Wechselrichtergrenzen sind keine EP-Vorschlagsfelder.

## Veröffentlichung und Gültigkeit

EP schreibt den ganzen Vorschlagssatz eines Plans in **einem** Schreibvorgang. Damit ist er für
das HEMS atomar sichtbar; der Commit-Marker `sensor.ep_plan_commit` und die Einzelsensoren
`sensor.ep_<prefix>_<feld>_vorschlag` aus Version 1.0 entfallen. EP entfernt sie beim ersten
Veröffentlichen nach dem Start über `DELETE /api/states/<entity_id>`.

HEMS akzeptiert ein angefragtes Feld nur, wenn:

- `sensor.energy_pilot_schnittstelle` einen vorhandenen, verfügbaren State hat;
- `valid_from` und `valid_until` gültig sind und `valid_from <= jetzt < valid_until` gilt;
- das Attribut `<prefix>_<feld>` vorhanden ist.

Bei fehlenden oder abgelaufenen Angaben fällt genau das betreffende Feld auf den normalen
Nutzer-/Ersatzwert zurück. `ep_proposal_status` nennt den ersten erkannten Vorschlagsfehler:
`missing_commit` (Entität fehlt oder ist nicht verfügbar), `invalid_commit` (Zeitfenster
unbrauchbar), `expired_commit` (außerhalb des Fensters) oder `missing_value` (Feld fehlt). Die
Namen bleiben aus Version 1.0 erhalten, damit EP sie weiter auswerten kann; `mismatched_plan`
entfällt.

Zeitgrenzen sind maschinenlesbare ISO-8601-Zeitstempel mit Zeitzoneninformation. Für Menschen
ausgegebene Zeiten werden als `TT.MM.JJJJ hh:mm:ss` in Berliner Ortszeit dargestellt.

## Steuerquelle, Schutzgrenzen und Zusatz-Entitäten

HEMS entscheidet über die Übernahme:

| Situation | Normale Steuerquelle |
|---|---|
| Hauptfreigabe aus, Hard-Lockout oder globaler Modus `aus` | `aus` |
| Gerätemodus `aus` | `aus`, auch bei global `auto` |
| Globaler Modus `auto` | `ep`, auch bei Gerätemodus `manuell` |
| Normaler globaler Modus und Gerätemodus `auto` | `ep` |
| Sonst, globaler Modus in `allowed_modes` | `user` |
| Sonst | `aus` |

Ungültige Vorschläge führen nicht zu einer automatischen Änderung dieser Modi. Technische
Freigaben, Schreibzielgesundheit und Gerätebegrenzungen bleiben HEMS-Aufgabe. Zwang und
Notabschaltung sind zusätzliche HEMS-Pfade, die EP nicht durch Vorschläge aufheben kann.

EP-Zusatz-Entitäten erzeugen weitere advisorische Sensoren `sensor.ep_<obj>_vorschlag`. Sie
gehören nicht zum regulären HEMS-Vorschlagsfeldsatz und nicht in die Schnittstellen-Entität. Die explizite Option „In Original schreiben“ kann zusätzlich
HA-Service-Aufrufe für erlaubte Helferdomänen auslösen. Diese Aufrufe erfolgen nach dem
Vorschlags-Commit, sind nicht dessen Transaktion und werden durch die EP-Modusauswertung
begrenzt. Diese reduzierte Modusauswertung ist keine vollständige Kopie aller HEMS-Schutzgates.

`sensor.ep_plan_status` und `sensor.ep_hems_verbindung` sind Anzeige-Entitäten und bleiben
einzeln. Sie ersetzen weder die Schnittstelle noch den Gerätesollwert. HEMS spiegelt
`sensor.energy_pilot_schnittstelle` und die EP-Sensoren über `/api/ep` für seine Oberfläche; HEMS
ruft dafür keine EP-HTTP-API auf.

## Kompatibilitätsgrenzen des aktuellen Stands

1. **AC-Speicher-Discovery:** EP erkennt explizit nur `controllable` und `binary`. Ein HEMS-
   `battery`-Eintrag kann je nach Items über alte Suffixheuristik falsch als `binary` eingeordnet
   oder ausgelassen werden. Der Sonderfall `entity_prefix == "batterie"` ersetzt keine
   Unterstützung der Geräteklasse. Die zusätzlichen Speicher-Vorschläge sind nicht durchgängig
   vom Plan-Schema bis zum Verbraucher implementiert.
2. **Ampere-Schutzsockel:** EP kann `<prefix>_geschutzte_mindestleistung_a` veröffentlichen; HEMS übernimmt in
   `ControllableDevice.update_from_ha()` den Schutzvorschlag nur bei `output_unit == "watt"`.
3. **Interne Werte und Add-on-Fallbacks:** HEMS kann fehlende oder ungültige HA-Eingaben aus
   internen Werten beziehungsweise Add-on-Optionen ersetzen. EP liest die Schema-Entities aus
   HA und übernimmt diese Ersatzwertkette nicht vollständig. Auch das Original-Schreibgate
   verwendet HA-Modi und liest keine HEMS-internen Modi. Gleiche wirksame Eingaben sind daher
   ohne passende HA-Helfer nicht zugesagt.
4. **Validierung:** HEMS prüft das Gültigkeitsfenster und verwendet seine Feldparser. Es führt keine
   erneute vollständige EP-Plan-JSON-Schemaprüfung aus und prüft `schema_version` nicht als
   Versionsgate. Boolesche Vorschläge werden als echter Bool oder als `on`, `true`, `1` interpretiert;
   andere vorhandene Strings werden als boolesch falsch interpretiert. Nicht konvertierbare
   Zahlen fallen über den Zahlenparser zurück; `NaN` und Unendlich werden dort nicht ausdrücklich
   ausgeschlossen. Die Vorschlagsdiagnose ist kein vollständiger Typvalidierungsnachweis.
5. **Lebenszeichen:** HTTP-Erreichbarkeit von HEMS ist kein Frischebeleg für den Regelzyklus.
   Vorschlagsgültigkeit wird über Zeitfenster geprüft, nicht über den EP-Prozesszustand.
6. **Tests:** Es gibt lokale Tests beider Seiten, aber bislang keine gemeinsame automatisierte
   Contract-Suite, die beide Implementierungen gegen denselben vollständigen Vertrag prüft.

Diese Punkte dokumentieren den Bestand. Ihre Behebung benötigt eigene Codeänderungen und
gegebenenfalls eine gemeinsame Vertragserweiterung.

## Beispiel eines gültigen Vorschlagssatzes

Beispiel für einen regelbaren Watt-Verbraucher mit Präfix `heizstab`; die Zeitstempel gehören
zur maschinenlesbaren Nutzlast:

```json
{
  "sensor.energy_pilot_schnittstelle": {
    "state": "heizstab",
    "attributes": {
      "schnittstelle_version": 1,
      "plan_id": "plan-42",
      "schema_version": "1.0",
      "valid_from": "2026-10-06T08:00:00Z",
      "valid_until": "2026-10-06T09:00:00Z",
      "heizstab_label": "Heizstab",
      "heizstab_prio": 2,
      "heizstab_freigabe": true,
      "heizstab_geschutzte_mindestleistung_w": 600
    }
  }
}
```

Anzeigeattribute sind hier gekürzt. Auch mit gültigem Vorschlag kann HEMS den Verbraucher wegen
seiner eigenen Gates sperren oder ihm weniger Leistung als den gewünschten Schutzsockel zuteilen.

## Zuständigkeiten und Änderungen

| Thema | SkytechHEMS | Energy Pilot |
|---|---|---|
| Geräteliste und Schema-Identitäten | erzeugt | entdeckt und liest |
| Prognose, KI-Plan, lokale Planvalidierung | führt nicht aus | verantwortlich |
| `sensor.energy_pilot_schnittstelle` | liest und prüft Gültigkeit | veröffentlicht |
| Freigaben, Messwertprüfung, Pool und Gerätesollwerte | entscheidet | beobachtet |
| Physische Gerätekommunikation | nachgelagerte Integration/Automation | kein regulärer Zugriff |
| Notabschaltung | führt aus | erhält Diagnose, quittiert nicht automatisch |

Version `2.0` (20.10.2026) ist inkompatibel zu `1.0`: Die Einzelsensoren und der Commit-Marker
entfallen, EP und HEMS (ab 4.0.0) müssen zusammen aktualisiert werden. Ohne passende Schnittstelle
fällt das HEMS auf die Nutzerwerte zurück (sicher).

Die Dokumentversion, die HEMS-Schema-Zahl `2`, `schnittstelle_version` und die
EP-Plan-Schemaversion `"1.0"` sind unterschiedliche Versionsachsen. Eine Änderung dieses Dokuments ändert keine davon im Code.
Neue optionale Felder sind additiv; Umbenennungen, entfernte Felder, andere Einheiten oder
geänderte Übernahmebedingungen müssen gemeinsam geprüft und versioniert werden.

Implementierungsreferenzen:

| Repository | Dateien |
|---|---|
| SkytechHEMS | `app/main.py`, `app/ems/devices.py`, `app/ems/state.py`, `app/internal_values.py` |
| Skytech-Energy-Pilot | `app/energy_pilot/hems_client.py`, `devices.py`, `constraints.py`, `plan_schema.py`, `suggestion_publisher.py`, `control_mode.py`, `hems_status_collector.py`, `plan_feedback.py` (Dateien unter `app/energy_pilot/`) |

## Additive Watt-Ladeziele — 21.10.2026

HEMS ergänzt im Geräteschema `charging_backend` (leer, `evms`, `wallbox_provider`,
`automation`). Ein nichtleerer Wert kennzeichnet ein Watt-Ladeziel. `class` bleibt
`controllable`, `output_unit` ist `watt`; `actual_power_entity` ist dabei leer,
weil HEMS die Messung aus der gewählten Schnittstellen-Entität liest. Der Gerätestatus
enthält weiter `actual_w`; zusätzlich `charging_backend`, `charging_assignment_id`
, `charging_interface` und `charging_measurement_valid`. Die bestehenden EP-Vorschlagsfelder bleiben unverändert.

EP steuert weder EVMS noch Wallboxen direkt. Fahrzeugidentität, automatische Zielanlage,
Abfahrtszeiten und Ladeziele sind damit nicht implementiert; ein direkter EVMS–EP-Vertrag
wird erst bei geklärtem Bedarf ergänzt. EP darf neue Ladeziele nicht anhand einer
fehlenden separaten Sensor-Entity als fehlendes Gerät interpretieren.
