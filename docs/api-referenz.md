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
    "pool_w": 3240.0,
    "current_deficit_w": 0.0,
    "binary_immediate_off": false,
    "binary_total_w": 2000.0,
    "devices": [ { "id": "heizstab", "type": "controllable" } ]
  },
  "last_cycle_at": "13.08.2026 20:14:03",
  "cycle_count": 412,
  "error": "",
  "interval_s": 30
}
```

Die Felder je Gerät sind in [datenmodell.md](datenmodell.md) beschrieben — sie sind Datenvertrag
zum Energy Pilot und werden nicht beiläufig umbenannt.

`error` ist ein leerer String, solange der letzte Zyklus durchlief; andernfalls die Fehlermeldung.

### `GET /api/controls`

Liefert die frischen Zustände aller EMS-Helfer, gefiltert auf die Präfixe
`input_boolean.ems_`, `input_select.ems_` und `input_number.ems_`. Struktur je Entität:
`{ "state": …, "attributes": { … }, "last_changed": … }` — die Attribute (`min`, `max`, `step`,
`options`, `unit_of_measurement`) steuern die Darstellung der Bedienelemente.

**Fehler `500`** `{"error": "<Meldung>"}` — Home Assistant nicht erreichbar.

### `GET /api/device_controls_schema`

Das Steuerschema der Oberfläche, abgeleitet aus der aktuellen Gerätekonfiguration. Eine Liste von
Gruppen: zuerst `{"label": "Global", "items": […]}`, danach je Gerät
`{"name": "<technische ID>", "label": "<Anzeigename>", "items": […]}`.
Jedes Item ist `{"entity": "<entity_id>", "label": "<deutscher Text>"}`.

`name` und `label` sind bewusst getrennt: Konsumenten machen die Identität am `name` fest, `label`
ist nur Anzeige. Ein Umbenennen des Labels bricht damit keine Zuordnung.

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
| Home Assistant | `POST /api/services/<domain>/<service>` | Sollwerte, Schaltanforderungen, Post-Cycle-Skript, Timeout 5 s | Einzelne Write-Ops werden geloggt und übersprungen (siehe [bekannte-luecken.md](bekannte-luecken.md)); das Post-Cycle-Skript wirft und wird als Warnung gemeldet |
