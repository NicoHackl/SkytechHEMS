# Vertrag: SkytechHEMS ↔ Skytech Energy Pilot

**Version:** 1.0

**Status:** Dokumentierter Implementierungsstand mit bekannten Kompatibilitätsgrenzen

**Stand:** 06.10.2026

**Geprüfte Codebasis:** SkytechHEMS `e5c0156`, Skytech-Energy-Pilot `e08e211`.

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
Energy Pilot ── Vorschlagssensoren + Plan-Commit ──► Home Assistant ──► SkytechHEMS
Energy Pilot ◄── States der im Schema genannten Entitäten ── Home Assistant
```

EP schreibt im regulären Vorschlagspfad ausschließlich eigene `sensor.ep_*`-Zustände über
die HA-State-API. HEMS liest sie aus seinem Zyklus-Schnappschuss und schreibt seine
`input_*`-Ausgabehelfer selbst. Der gesonderte EP-Original-Schreibweg für konfigurierte
Zusatz-Entitäten ist unten als Ausnahme beschrieben.

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

## EP → HEMS: Vorschläge und unterstützter Umfang

Alle regulären Vorschlagssensoren folgen
`sensor.ep_<prefix>_<feld>_vorschlag`. Boolesche Werte veröffentlicht EP als `on`/`off`, Zahlen
als numerische Strings. Jeder Sensor trägt `plan_id`, `valid_from`, `valid_until`,
`friendly_name`, `source` und bei Leistung `unit_of_measurement`.

| Gerätekonstellation | EP veröffentlicht regulär | Aktuelle HEMS-Übernahme |
|---|---|---|
| `binary`, normales Präfix | `prio`, `freigabe` | Beide Felder bei Quelle `ep`. |
| `controllable`, Watt, normales Präfix | `prio`, `freigabe`, `geschutzte_mindestleistung_w` | Alle drei Felder bei Quelle `ep`. |
| `controllable`, Ampere, normales Präfix | `prio`, `freigabe`, `geschutzte_mindestleistung_a` | Nur `prio` und `freigabe`; der Ampere-Schutzvorschlag wird derzeit nicht gelesen. |
| EP-Sonderfall Präfix `batterie` | Nur `geschutzte_mindestleistung_w`; EP behandelt Priorität 1 und Freigabe als feste Planungsannahmen. | Nicht gleichbedeutend mit HEMS-Geräteklasse `battery`; keine pauschale Kompatibilitätszusage. |
| HEMS-Geräteklasse `battery` | Kein vollständiger, ausdrücklich implementierter EP-Pfad. | HEMS kann sieben Vorschlagsfelder lesen; EP liefert diesen Satz derzeit nicht. |

Die sieben HEMS-seitigen Speicherfelder sind `freigabe`, `prio`,
`geschutzte_mindestleistung_w`, `entlade_prio`, `soc_ziel_prozent`, `soc_min_prozent` und
`betriebsart`. Bei `betriebsart` sind `auto`, `nur_laden`, `nur_entladen`, `standby` zulässig.
Physische Wechselrichtergrenzen sind keine EP-Vorschlagsfelder.

## Veröffentlichung und Gültigkeit

EP übergibt kein vollständiges Plan-JSON an einen HEMS-REST-Endpunkt. Der Austausch erfolgt
über einzelne HA-Sensoren mit einem gemeinsamen Sichtbarkeitsmarker:

1. EP setzt `sensor.ep_plan_commit` auf `publishing` und macht dessen Zeitfenster ungültig.
   Schlägt bereits das fehl, wird die Veröffentlichung abgebrochen.
2. EP schreibt die Vorschlagssensoren mit gemeinsamer Plan-ID und gemeinsamem Zeitfenster.
3. Nur wenn alle Vorschlagssensoren erfolgreich geschrieben wurden, setzt EP den Commit-State
   auf die `plan_id`. Seine Attribute enthalten `plan_id`, `valid_from`, `valid_until` und
   `schema_version` des EP-Plans.
4. HEMS liest Commit und Vorschläge aus seinem nächsten HA-Schnappschuss.

HEMS akzeptiert ein angefragtes Feld nur, wenn:

- Sensor und Commit einen vorhandenen, verfügbaren State haben;
- das Commit-Zeitfenster gültig ist und `valid_from <= jetzt < valid_until` gilt;
- Sensor-`plan_id` gleich Commit-State ist;
- beide Zeitgrenzen nach dem Parsen exakt mit denen des Commits übereinstimmen.

Bei fehlenden, nicht passenden oder abgelaufenen Angaben fällt genau das betreffende Feld auf
den normalen Nutzer-/Ersatzwert zurück. `ep_proposal_status` nennt den ersten erkannten
Vorschlagsfehler, etwa `missing_value`, `missing_commit`, `invalid_commit`, `expired_commit`
oder `mismatched_plan`.

Das ist eine Freigabe eines vollständig veröffentlichten Vorschlagssatzes, keine Datenbank-
Transaktion und keine Alles-oder-nichts-Anwendung sämtlicher Felder. Während der Veröffentlichung
wirken Fallbackwerte. Ein nachträglich fehlendes Feld lässt andere gültige Felder weiter wirken.

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

EP-Zusatz-Entitäten erzeugen weitere advisorische Sensoren. Sie gehören nicht zum regulären
HEMS-Vorschlagsfeldsatz. Die explizite Option „In Original schreiben“ kann zusätzlich
HA-Service-Aufrufe für erlaubte Helferdomänen auslösen. Diese Aufrufe erfolgen nach dem
Vorschlags-Commit, sind nicht dessen Transaktion und werden durch die EP-Modusauswertung
begrenzt. Diese reduzierte Modusauswertung ist keine vollständige Kopie aller HEMS-Schutzgates.

`sensor.ep_plan_status` und `sensor.ep_hems_verbindung` sind Diagnoseausgaben. Sie ersetzen
weder den Plan-Commit noch den Gerätesollwert. HEMS kann die EP-Sensoren über `/api/ep` für
seine Oberfläche spiegeln; HEMS ruft dafür keine EP-HTTP-API auf.

## Kompatibilitätsgrenzen des aktuellen Stands

1. **AC-Speicher-Discovery:** EP erkennt explizit nur `controllable` und `binary`. Ein HEMS-
   `battery`-Eintrag kann je nach Items über alte Suffixheuristik falsch als `binary` eingeordnet
   oder ausgelassen werden. Der Sonderfall `entity_prefix == "batterie"` ersetzt keine
   Unterstützung der Geräteklasse. Die zusätzlichen Speicher-Vorschläge sind nicht durchgängig
   vom Plan-Schema bis zum Verbraucher implementiert.
2. **Ampere-Schutzsockel:** EP kann `_a_vorschlag` veröffentlichen; HEMS übernimmt in
   `ControllableDevice.update_from_ha()` den Schutzvorschlag nur bei `output_unit == "watt"`.
3. **Interne Werte und Add-on-Fallbacks:** HEMS kann fehlende oder ungültige HA-Eingaben aus
   internen Werten beziehungsweise Add-on-Optionen ersetzen. EP liest die Schema-Entities aus
   HA und übernimmt diese Ersatzwertkette nicht vollständig. Auch das Original-Schreibgate
   verwendet HA-Modi und liest keine HEMS-internen Modi. Gleiche wirksame Eingaben sind daher
   ohne passende HA-Helfer nicht zugesagt.
4. **Validierung:** HEMS prüft den Commit-Bezug und verwendet seine Feldparser. Es führt keine
   erneute vollständige EP-Plan-JSON-Schemaprüfung aus und prüft die Commit-`schema_version`
   nicht als Versionsgate. Boolesche Vorschläge werden als `on`, `true`, `1` interpretiert;
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
zur maschinenlesbaren Nutzlast. Alle drei Sensoren erhalten dieselben Gültigkeitsattribute:

```json
{
  "sensor.ep_heizstab_prio_vorschlag": {
    "state": "2",
    "attributes": {"plan_id": "plan-42", "valid_from": "2026-10-06T08:00:00Z", "valid_until": "2026-10-06T09:00:00Z"}
  },
  "sensor.ep_heizstab_freigabe_vorschlag": {
    "state": "on",
    "attributes": {"plan_id": "plan-42", "valid_from": "2026-10-06T08:00:00Z", "valid_until": "2026-10-06T09:00:00Z"}
  },
  "sensor.ep_heizstab_geschutzte_mindestleistung_w_vorschlag": {
    "state": "600",
    "attributes": {"plan_id": "plan-42", "valid_from": "2026-10-06T08:00:00Z", "valid_until": "2026-10-06T09:00:00Z", "unit_of_measurement": "W"}
  },
  "sensor.ep_plan_commit": {
    "state": "plan-42",
    "attributes": {"plan_id": "plan-42", "schema_version": "1.0", "valid_from": "2026-10-06T08:00:00Z", "valid_until": "2026-10-06T09:00:00Z"}
  }
}
```

Anzeigeattribute sind hier gekürzt. Vor dem finalen Commit steht der Marker vorübergehend auf
`publishing`. Auch mit gültigem Commit kann HEMS den Verbraucher wegen seiner eigenen Gates
sperren oder ihm weniger Leistung als den gewünschten Schutzsockel zuteilen.

## Zuständigkeiten und Änderungen

| Thema | SkytechHEMS | Energy Pilot |
|---|---|---|
| Geräteliste und Schema-Identitäten | erzeugt | entdeckt und liest |
| Prognose, KI-Plan, lokale Planvalidierung | führt nicht aus | verantwortlich |
| Vorschlagssensoren und Commit | liest und prüft Feldbezug | veröffentlicht |
| Freigaben, Messwertprüfung, Pool und Gerätesollwerte | entscheidet | beobachtet |
| Physische Gerätekommunikation | nachgelagerte Integration/Automation | kein regulärer Zugriff |
| Notabschaltung | führt aus | erhält Diagnose, quittiert nicht automatisch |

Die Dokumentversion `1.0`, die HEMS-Schema-Zahl `2` und die EP-Plan-Schemaversion `"1.0"`
sind unterschiedliche Versionsachsen. Eine Änderung dieses Dokuments ändert keine davon im Code.
Neue optionale Felder sind additiv; Umbenennungen, entfernte Felder, andere Einheiten oder
geänderte Übernahmebedingungen müssen gemeinsam geprüft und versioniert werden.

Implementierungsreferenzen:

| Repository | Dateien |
|---|---|
| SkytechHEMS | `app/main.py`, `app/ems/devices.py`, `app/ems/state.py`, `app/internal_values.py` |
| Skytech-Energy-Pilot | `app/energy_pilot/hems_client.py`, `devices.py`, `constraints.py`, `plan_schema.py`, `suggestion_publisher.py`, `control_mode.py`, `hems_status_collector.py`, `plan_feedback.py` (Dateien unter `app/energy_pilot/`) |
