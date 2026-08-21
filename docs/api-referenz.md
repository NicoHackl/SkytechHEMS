# API-Referenz

> Die HTTP-Schnittstelle des Add-ons. Sie bedient die eigene Oberfläche und ist nicht als
> öffentliche API gedacht — erreichbar ist sie nur über den HA-Ingress.

## Grundsätzliches

- Basis-Pfad: die Wurzel des Add-ons, im Ingress-Betrieb also
  `/api/hassio_ingress/<token>/`. Alle Pfade unten sind **relativ** dazu zu verstehen; die
  Oberfläche ruft sie ohne führenden Schrägstrich auf (D-036, siehe
  [frontend.md](frontend.md)).
- Keine Versionierung im Pfad: Server und Oberfläche werden gemeinsam ausgeliefert.
- Authentifizierung: durch den Ingress von Home Assistant. Das Add-on prüft selbst nicht.
- Format: JSON. Zeitangaben, die ein Mensch zu sehen bekommt, liefert der Server bereits als
  `TT.MM.JJJJ hh:mm:ss` in Berliner Zeit (eiserne Regel 9 in [`AGENTS.md`](../AGENTS.md));
  Zeitstempel aus fremden Quellen (`valid_until` des Energy Pilot) bleiben ISO 8601 und werden
  erst in der Oberfläche umgesetzt.

## Endpunkte

### `GET /`

Liefert die Oberfläche (`app/static/index.html`). Die Assets darunter kommen aus
`app/static/assets/` und werden unter `/assets/` ausgeliefert.

### `GET /api/status`

Schnappschuss des zuletzt gelaufenen Zyklus. Rechnet nichts neu — der Wert stammt aus dem
Scheduler.

**Antwort `200`**

```json
{
  "status": {
    "timestamp": "13.08.2026 20:14:03",
    "ems_enabled": true,
    "global_mode": "manuell",
    "hard_lockout": false,
    "residual_sensor_valid": true,
    "residual_w": 1840.0,
    "residual_bereinigt_w": 1840.0,
    "netz_support_w": 0.0,
    "hems_last_w": 1400.0,
    "hems_last_gemessen_w": 1400.0,
    "pool_roh_w": 3240.0,
    "pool_w": 3240.0,
    "entlade_basis_w": 3240.0,
    "hausdefizit_w": 0.0,
    "current_deficit_w": 0.0,
    "binary_immediate_off": false,
    "binary_total_w": 2000.0,
    "global_mode_configured": true,
    "available_modes": ["manuell", "nur_heizen", "nur_laden"],
    "devices": [ { "id": "heizstab", "type": "controllable" } ],
    "inactive_devices": []
  },
  "last_cycle_at": "13.08.2026 20:14:03",
  "last_cycle_at_iso": "2026-08-13T20:14:03+02:00",
  "cycle_count": 412,
  "error": "",
  "interval_s": 30
}
```

Die Felder je Gerät sind in [datenmodell.md](datenmodell.md) beschrieben — sie sind Datenvertrag
zum Energy Pilot und werden nicht beiläufig umbenannt.

`type` ist `controllable`, `binary` oder `battery`. Die Speicherfelder kamen additiv dazu; ohne
konfigurierten Speicher ist `netz_support_w` immer `0`, `residual_bereinigt_w` gleich
`residual_w`, `pool_roh_w` gleich dem alten ungeklemmten Pool und `hausdefizit_w` immer `0`.

**Für Planer wichtig:** Regelentscheidungen beziehen sich auf `residual_bereinigt_w`, nicht auf
`residual_w`. Und `hausdefizit_w` ist bewusst kleiner als `current_deficit_w`, sobald HEMS-Geräte
laufen — die Differenz ist deren gemessene Last, die ein Speicher ausdrücklich **nicht** decken
soll.

`error` ist ein leerer String, solange der letzte Zyklus durchlief; andernfalls die Fehlermeldung.
Ein einzelnes Gerät mit kaputtem Schreibziel macht den Zyklus **nicht** fehlerhaft — es steht in
`devices_inactive_runtime` und trägt selbst `runtime_active: false` samt `inactive_reasons` und
`write_error`.

### `GET /api/controls`

Liefert die frischen Zustände aller EMS-Helfer, gefiltert auf die Präfixe
`input_boolean.ems_`, `input_select.ems_` und `input_number.ems_`. Struktur je Entität:
`{ "state": …, "attributes": { … }, "last_changed": … }` — die Attribute (`min`, `max`, `step`,
`options`, `unit_of_measurement`) steuern die Darstellung der Bedienelemente.

**Fehler `500`** `{"error": "<Meldung>"}` — Home Assistant nicht erreichbar.

### `GET /api/device_controls_schema`

Das Steuerschema der Oberfläche, abgeleitet aus der aktuellen Gerätekonfiguration. Eine Liste von
Gruppen: zuerst `{"name": "global", "label": "Global", "schema_version": 2, "items": […]}`,
danach je Gerät `{"name": "<technische ID>", "label": "<Anzeigename>", "items": […]}`.
Die bisherige Form bleibt additiv kompatibel. Geräte ergänzen `class`, `entity_prefix`,
`output_unit`, `allowed_modes`, `control_policy`, `request_entity` sowie je nach Klasse
`actual_power_entity` oder `switch_entity`. Jedes Item trägt weiterhin `entity` und `label` und
zusätzlich `key`, `kind`, `unit` (falls vorhanden), `role` und `planning_relevant`.

Ein Speicher (`class: "battery"`) ergänzt `soc_entity`, `charge_power_entity`,
`discharge_power_entity`, `power_entity`, `power_sign`, `available_charge_power_w`,
`available_discharge_power_w`, `capacity_kwh`, `mode_entity` und `request_sign`. Die beiden
`available_*_w`-Felder sind direkt konfigurierte Zahlenwerte in Watt, keine Entity-IDs.
`request_entity` trägt beim Speicher **einen signierten Wert**: positiv = laden,
negativ = entladen. `request_sign: "positiv_laden"` sagt das ausdrücklich, damit niemand raten
muss.

`name` und `label` sind bewusst getrennt: Konsumenten machen die Identität am `name` fest, `label`
ist nur Anzeige. Ein Umbenennen des Labels bricht damit keine Zuordnung.

`control_policy = "pv_surplus_only"` bedeutet: HEMS begrenzt die tatsächliche Verbraucherleistung
bereits auf verfügbaren PV-Überschuss. Ein Planer darf Netzbezug deshalb nicht als kausalen
Abschaltgrund für diese Verbraucher verwenden.

### EP-Plan-Commit

Vorschläge unter `sensor.ep_<gerät>_<feld>_vorschlag` werden nur übernommen, wenn ihre Attribute
`plan_id` und `valid_until` zu `sensor.ep_plan_commit` passen. Der Commit-State ist die `plan_id`;
seine Attribute enthalten `valid_from` und `valid_until`. Fehlt der Commit, stimmen IDs oder
Gültigkeit nicht überein oder ist das Zeitfenster abgelaufen, nutzt HEMS für das betreffende Feld
den Nutzerwert. `ep_proposal_status` im Gerätestatus nennt die Ursache.

### `GET /api/ep`

Spiegelt die vom **Energy Pilot** veröffentlichten `sensor.ep_*`-Entitäten, gefiltert aus dem
HA-State. Reine Anzeige — es gibt keinen direkten Add-on-zu-Add-on-Aufruf.

Relevant sind `sensor.ep_plan_status`, `sensor.ep_hems_verbindung` und je Gerät und Feld ein
`sensor.ep_<gerät>_<feld>_vorschlag`. Zum Umgang mit verwaisten Vorschlägen siehe
[datenmodell.md](datenmodell.md).

**Fehler `500`** `{"error": "<Meldung>"}`.

### `POST /api/set`

Schreibt einen Wert in eine HA-`input_*`-Entität.

**Rumpf**

```json
{ "entity_id": "input_number.ems_heizstab_prioritat", "value": 10 }
```

| Domain | Ausgeführter Service | Wertbehandlung |
|---|---|---|
| `input_boolean` | `turn_on` / `turn_off` | wahr sind `true`, `"on"`, `"true"`, `1`, `"1"` |
| `input_number` | `set_value` | `float(value)` |
| `input_select` | `select_option` | `str(value)` |

**Antwort `200`** `{"ok": true}`

| Code | Wann | Rumpf |
|---|---|---|
| `400` | Domain wird nicht unterstützt | `{"error": "Unsupported domain: <domain>"}` |
| `500` | Schreiben fehlgeschlagen | `{"error": "<Meldung>"}` |

## Konfigurations-Endpunkte

Sie bedienen den Bereich **Konfiguration** der Oberfläche. Geschrieben wird ausschließlich über die
Supervisor-API — es gibt keine zweite Konfigurationsdatei und kein direktes Schreiben nach
`/data/options.json`.

Fehlercodes durchgehend: `400` unlesbarer Request, `403` fehlende Supervisor-Schreibberechtigung,
`409` Revisionskonflikt, `422` Feldvalidierung, `502` Supervisor nicht erreichbar, `503` kein
Supervisor-Zugang oder Neustart nicht auslösbar. Fehlertexte für den User sind deutsch; technische
Details stehen bereinigt im Log.

### `GET /api/config`

Alles, was die Konfigurationsseite zum Anzeigen braucht.

| Feld | Bedeutung |
|---|---|
| `options` | Die **normalisierten, bekannten** Optionsfelder. Unbekannte künftige Top-Level-Felder werden ausdrücklich nicht an den Browser gegeben |
| `valid`, `errors`, `field_errors` | Serverseitige Prüfung der gespeicherten Konfiguration; Feldpfade wie `devices[2].technical_maximum` |
| `inactive_devices` | Einträge, die beim Start nicht instanziiert würden, samt Feldfehlern |
| `stored_revision` | Hash der aktuell beim Supervisor gespeicherten **rohen** Optionen |
| `loaded_revision` | Stand, mit dem der laufende Controller instanziiert wurde |
| `restart_required` | `true`, wenn beide abweichen |
| `can_save`, `can_restart` | Fähigkeiten dieser Instanz — ohne Supervisor beide `false` |
| `supervisor_available`, `supervisor_error` | Warum gegebenenfalls nicht |
| `instance_id` | Kennung dieses Prozessstarts |
| `supported` | Wertebereiche und Formular-Startwerte: Modi, Klassen, Log-Level, Einheiten, Phasen, Vorzeichen, Defaults je Klasse |

Außerhalb des Add-on-Containers fällt der Endpunkt auf die lokal gelesene Konfiguration zurück.
Speichern und Neustarten sind dann deaktiviert — es wird niemals vorgetäuscht, ein
Supervisor-Schreibvorgang sei erfolgreich gewesen.

### `GET /api/config/entities`

Reduzierte Entitätsliste aus dem letzten HA-Schnappschuss für die Suchauswahl:
`{entity_id, domain, state, friendly_name}`. Ohne Parameter `sensor`, `switch` und `script`;
`?domains=input_number,input_boolean` fragt andere Domains ab. Bewusst ohne die vollständigen
Attribute.

### `POST /api/config/validate`

Prüft einen Entwurf, ohne zu speichern. **Rumpf** `{"options": { … }}`.
**Antwort `200`** `{"valid": …, "errors": [ … ], "field_errors": { … }, "inactive_devices": [ … ]}`.

### `PUT /api/config`

**Rumpf** `{"options": { … }, "stored_revision": "…"}`. Ablauf in genau dieser Reihenfolge:

1. eigene fachliche Validierung → `422` mit `field_errors`;
2. frisch gelesene gespeicherte Optionen holen und die Revision vergleichen → `409`;
3. bekannte Felder in diese rohen Optionen mischen, damit unbekannte künftige Felder erhalten
   bleiben;
4. Validierung durch den Supervisor → `422`;
5. speichern.

**Antwort `200`** `{"stored_revision": "…", "loaded_revision": "…", "restart_required": true}`.
Der Endpunkt startet ausdrücklich **nicht** neu.

### `POST /api/config/restart`

Startet mit der **bereits gespeicherten** Konfiguration neu; ein Browser-Entwurf wird nie still
verworfen. Zuerst werden die Ausgänge betroffener Altgeräte sicher gesetzt (`controllable` → `0`,
`binary` → `off`, `battery` → erst `0 W`, dann `standby`). Schlägt das fehl, wird **nicht** neu
gestartet: `503` mit `deactivation_failed`.

**Antwort `202`** `{"restarting": true, "instance_id": "…", "stored_revision": "…"}` — sie geht
raus, bevor der Prozess endet.

### `POST /api/config/save-and-restart`

Rumpf wie `PUT /api/config`. Reihenfolge: speichern → sicher deaktivieren → neu starten.
Schlägt die Deaktivierung fehl, **bleibt die Konfiguration gespeichert** und der Neustart
unterbleibt; die Antwort benennt diesen Teilstatus:

- `202` `{"restarting": true, …}` — gespeichert und Neustart läuft;
- `200` `{"restarting": false, "deactivation_failed": [ … ], "message": "…"}` — gespeichert, aber
  nicht neu gestartet.

### Neustart erkennen

`GET /api/status` liefert `instance_id`, eine je Prozessstart neue Kennung. Die Oberfläche pollt
nach einem ausgelösten Neustart den relativen API-Pfad und wertet erst eine **andere**
`instance_id` als abgeschlossenen Neustart — eine sehr kurze Unterbrechung sähe sonst wie ein
erfolgreicher Neustart aus.

## Fremde Schnittstellen

Vom Add-on genutzte Endpunkte von Home Assistant:

| Dienst | Endpunkt | Wofür | Verhalten bei Ausfall |
|---|---|---|---|
| Home Assistant | `GET /api/states` | Kompletter State-Schnappschuss je Zyklus, Timeout 10 s | Zyklus wird abgebrochen und in `/api/status.error` gemeldet; die zuletzt geschriebenen Sollwerte bleiben stehen |
| Supervisor | `GET /addons/self/info` | Gespeicherte Add-on-Optionen lesen, Timeout 10 s | `GET /api/config` fällt auf die lokal gelesene Konfiguration zurück, Speichern und Neustarten sind gesperrt |
| Supervisor | `POST /addons/self/options/validate` | Optionen gegen das Manifest-Schema prüfen, Timeout 10 s | Fachliche Ablehnung wird als `422` mit der Supervisor-Meldung durchgereicht; fehlende Manager-Rolle als erklärendes `403` |
| Supervisor | `POST /addons/self/options` | Optionen speichern, Timeout 10 s | Fehlende Manager-Rolle als erklärendes `403`, Verbindungsfehler als `502`; es wird nie vorgetäuscht, das Speichern sei gelungen |
| Supervisor | `POST /addons/self/restart` | Eigenes Add-on neu starten, Timeout 30 s | Wird erst nach der ausgelieferten `202`-Antwort angestoßen |
| Home Assistant | `POST /api/services/<domain>/<service>` | Sollwerte, Schaltanforderungen, Post-Cycle-Skript, Timeout 5 s | Eine fehlgeschlagene Write-Op wird ihrem Gerät zugeordnet, geloggt und im Status sichtbar gemacht; das Gerät fährt im nächsten Zyklus nur noch seinen sicheren Zustand, die übrigen regeln weiter. Das Post-Cycle-Skript wirft und wird als Warnung gemeldet |
