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
`discharge_power_entity`, `power_entity`, `power_sign`, `available_charge_power_entity`,
`available_discharge_power_entity`, `capacity_kwh`, `mode_entity` und `request_sign`. `request_entity` trägt beim Speicher **einen signierten Wert**: positiv = laden,
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

## Fremde Schnittstellen

Vom Add-on genutzte Endpunkte von Home Assistant:

| Dienst | Endpunkt | Wofür | Verhalten bei Ausfall |
|---|---|---|---|
| Home Assistant | `GET /api/states` | Kompletter State-Schnappschuss je Zyklus, Timeout 10 s | Zyklus wird abgebrochen und in `/api/status.error` gemeldet; die zuletzt geschriebenen Sollwerte bleiben stehen |
| Home Assistant | `POST /api/services/<domain>/<service>` | Sollwerte, Schaltanforderungen, Post-Cycle-Skript, Timeout 5 s | Eine fehlgeschlagene Write-Op wird ihrem Gerät zugeordnet, geloggt und im Status sichtbar gemacht; das Gerät fährt im nächsten Zyklus nur noch seinen sicheren Zustand, die übrigen regeln weiter. Das Post-Cycle-Skript wirft und wird als Warnung gemeldet |
