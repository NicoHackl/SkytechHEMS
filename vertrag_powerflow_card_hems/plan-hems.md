# Umsetzungsplan: Flow-Card-Anbindung im Skytech HEMS

> **Repository:** dieses (`SkytechHEMS`). Der Gegenpart im Card-Repo steht in
> [`plan-card.md`](plan-card.md), der gemeinsame Datenvertrag in [`kontrakt.md`](kontrakt.md).
>
> **Stand:** 23.08.2026. Entwurf v1 — Grundlage der Umsetzung.

## Zweck und Arbeitsauftrag

Dieser Plan beschreibt die vollständige Umsetzung der HEMS-Seite der dynamischen Power-Flow-Card.
Er ist als ausführbarer Arbeitsauftrag für einen KI-Agenten gedacht. Die Umsetzung umfasst
Add-on-Optionen, einen neuen Veröffentlichungsdienst, einen Diagnoseendpunkt, einen neuen Bereich
in der Ingress-Oberfläche, Tests, Manifest, Übersetzungen, Dokumentation und Changelog.

Das HEMS bekommt zwei Aufgaben dazu:

1. **Standardwerte pflegen.** PV-Leistung, Netzleistung, Hausleistung, Batterie-SoC und
   -Leistung sind heute nirgends im HEMS hinterlegt. Sie bekommen einen neuen Bereich
   „Flow Card" in der Oberfläche.
2. **Kartendaten veröffentlichen.** Das HEMS schreibt Layout, Geräteliste und Zyklus-Kennzahlen
   in zwei eigene HA-Sensoren, aus denen sich die Lovelace-Karte selbst aufbaut.

Vor der ersten Änderung sind vollständig zu lesen:

- `AGENTS.md`
- [`kontrakt.md`](kontrakt.md) — der Datenvertrag, autoritativ für jedes Feld
- `docs/architektur.md`
- `docs/entwicklerrichtlinien.md`
- `docs/frontend.md`
- `docs/design-system.md`
- `docs/konfiguration.md`
- `docs/datenmodell.md`
- `docs/api-referenz.md`
- `docs/test-strategie.md`
- `docs/bekannte-luecken.md`
- `docs/device_classes/global.md`

Die Umsetzung erfolgt ausschließlich auf `claude/main`. Bestehende, nicht zu diesem Arbeitspaket
gehörende Änderungen dürfen nicht überschrieben werden.

---

## Verbindliche Entscheidungen

1. **Der Transportweg ist die HA-Zustandsmaschine, nicht Ingress.** Das Add-on schreibt
   `sensor.skytech_hems_flow_config` und `sensor.skytech_hems_flow_status` über
   `POST {HA_URL}/api/states/<entity_id>`. Die Karte ruft das Add-on **nicht** auf. Begründung und
   verworfene Alternative stehen in [`kontrakt.md`](kontrakt.md), Abschnitt 2.

2. **Das bricht Invariante 4 und wird als D-046 festgeschrieben.** `docs/architektur.md` sagt
   heute: „Geschrieben werden ausschließlich `input_*`-Helfer." Das gilt weiterhin für den
   **Regelpfad** und ist dort unverändert. Der Invariantentext wird präzisiert auf: *im Regelpfad
   schreibt das Add-on ausschließlich `input_*`-Helfer; darüber hinaus veröffentlicht es reine
   Anzeigedaten als eigene `sensor.*`-Entitäten, die kein Gerät schalten (D-046).*
   Ein ADR unter `docs/adr/D-046-flow-card-veroeffentlichung.md` hält die verworfene
   Ingress-Variante fest.

3. **Der Publisher darf den Regelzyklus niemals stören.** Jeder Fehler beim Schreiben wird
   protokolliert und verschluckt. Kein `raise` verlässt `flow_publisher.py`. Vorbild ist
   `HAClient.execute_write_ops` — ein kaputtes Schreibziel reißt die übrigen nicht mit.

4. **Der Publisher läuft nach dem Zyklus, nicht darin.** Er liest den fertigen `CycleStatus` und
   das bereits geholte HA-Zustandsabbild. Er löst **keine** zusätzliche HA-Abfrage aus.

5. **Die neuen Optionen lösen keine Geräteabschaltung aus.** Keiner der `flow_*`-Schlüssel kommt
   in `GLOBAL_KEYS_FORCING_SHUTDOWN` (`app/configuration.py`). Anzeigeeinstellungen zu ändern darf
   nicht dazu führen, dass ein Heizstab abgeschaltet wird.

6. **Validierung bleibt serverseitig.** Die neue Seite nutzt den bestehenden Pfad
   `POST /api/config/validate`; im Browser wird keine Prüflogik nachgebaut.

7. **Entity-IDs werden im Vertrag ausgeschrieben.** Der Publisher setzt jede Helfer-Entity-ID
   explizit in die Nutzlast. Die Karte darf keine Namen aus Präfixen zusammensetzen — dieselbe
   Regel, die `GET /api/device_controls_schema` für den Steuerung-Tab schon durchsetzt.

8. **Der Datenvertrag ist additiv.** Felder werden erweitert, nie umbenannt (D-034 sinngemäß).
   `schema_version` bleibt `1`, solange nichts entfällt oder seine Bedeutung ändert.

---

## Ziel-Datenmodell der Add-on-Optionen

Neue globale Schlüssel, flach mit Präfix `flow_`. Flach deshalb, weil die Add-on-Schemasyntax des
Supervisors keine verschachtelten Blöcke ausdrücken kann — dieselbe Begründung wie bei den
bestehenden `*_formula_*`-Feldern.

| Schlüssel | Typ | Default | Bedeutung |
|---|---|---|---|
| `flow_publish` | bool | `false` | Veröffentlichung ein/aus. Aus heißt: der Publisher tut nichts. |
| `flow_title` | str | `"Leistungsfluss"` | Überschrift der Karte. Leer = keine Überschrift. |
| `flow_watt_threshold` | int (0…100000) | `1000` | Ab diesem Betrag zeigt die Karte kW statt W. |
| `flow_animation` | bool | `true` | Wandernde Punkte auf den Flusslinien. |
| `flow_house_node` | bool | `true` | Hausknoten zeichnen. |
| `flow_pv_power_entities` | Objektliste `[{entity}]` | `[]` | PV-Leistungssensoren, werden summiert. |
| `flow_pv_label` | str | `"Photovoltaik"` | Anzeigename des PV-Knotens. |
| `flow_grid_power_entity` | str | `""` | Signierter Netzsensor. |
| `flow_grid_power_sign` | list | `"positiv_bezug"` | `positiv_bezug` \| `positiv_einspeisung` |
| `flow_grid_import_entity` | str | `""` | Alternative: getrennter Bezugssensor. |
| `flow_grid_export_entity` | str | `""` | Alternative: getrennter Einspeisesensor. |
| `flow_grid_label` | str | `"Netz"` | Anzeigename des Netzknotens. |
| `flow_house_power_entity` | str | `""` | Hausleistung. Leer = die Karte rechnet die Bilanz. |
| `flow_house_label` | str | `"Haus"` | Anzeigename des Hausknotens. |
| `flow_battery_label` | str | `""` | Anzeigename des Batterieknotens. Leer = kein Knoten. |
| `flow_battery_soc_entity` | str | `""` | SoC in Prozent. |
| `flow_battery_capacity_kwh` | float \| null | `null` | Nur Anzeige. |
| `flow_battery_power_entity` | str | `""` | Variante A: ein signierter Sensor. |
| `flow_battery_power_sign` | list | `"positiv_laden"` | `positiv_laden` \| `positiv_entladen` |
| `flow_battery_charge_power_entity` | str | `""` | Variante B: Ladesensor. |
| `flow_battery_discharge_power_entity` | str | `""` | Variante B: Entladesensor. |

Je Gerät kommen drei optionale Felder dazu — sie gehören zum Gerät, damit sie ein Umsortieren der
Liste überleben:

| Schlüssel | Typ | Default | Bedeutung |
|---|---|---|---|
| `flow_show` | bool | `true` | Gerät auf der Karte anzeigen. |
| `flow_icon` | str | `""` | mdi-Name. Leer = die Karte wählt nach Geräteklasse. |
| `flow_color` | str | `""` | CSS-Farbe als Override. Leer = Skytech-Akzent. |

### Abbildung Option → Vertragsfeld

Der Publisher übersetzt die flachen Optionen in die verschachtelte Nutzlast. Die Zuordnung ist
verbindlich und wird nicht geraten:

| Option | Vertragsfeld in `sensor.skytech_hems_flow_config` |
|---|---|
| `flow_title` | `anzeige.titel` |
| `flow_watt_threshold` | `anzeige.watt_schwelle` |
| `flow_animation` | `anzeige.animation` |
| `flow_house_node` | `anzeige.haus_knoten_anzeigen` |
| `flow_pv_power_entities[].entity` | `standard.pv_power_entities[]` (nur die Entity-IDs) |
| `flow_pv_label` | `standard.pv_label` |
| `flow_grid_power_entity` | `standard.grid_power_entity` |
| `flow_grid_power_sign` | `standard.grid_power_sign` |
| `flow_grid_import_entity` | `standard.grid_import_entity` |
| `flow_grid_export_entity` | `standard.grid_export_entity` |
| `flow_grid_label` | `standard.grid_label` |
| `flow_house_power_entity` | `standard.house_power_entity` |
| `flow_house_label` | `standard.house_label` |
| `flow_battery_label` | `standard.batterie.label` |
| `flow_battery_soc_entity` | `standard.batterie.soc_entity` |
| `flow_battery_capacity_kwh` | `standard.batterie.capacity_kwh` |
| `flow_battery_power_entity` | `standard.batterie.power_entity` |
| `flow_battery_power_sign` | `standard.batterie.power_sign` |
| `flow_battery_charge_power_entity` | `standard.batterie.charge_power_entity` |
| `flow_battery_discharge_power_entity` | `standard.batterie.discharge_power_entity` |
| Gerät `flow_show` | steuert die Aufnahme in `devices[]`, erscheint dort **nicht** als Feld |
| Gerät `flow_icon` | `devices[].icon` |
| Gerät `flow_color` | `devices[].farbe` |
| Gerät `name` | `devices[].id` |
| Gerät `label` | `devices[].label` (leer → `name`) |
| Gerät `class` | `devices[].class` |
| Gerät `actual_power_entity` | `devices[].power_entity` (Klasse `controllable`) |
| Gerät `switch_entity`, `power_actual_entity`, `power_w` | `devices[].switch_entity`, `.power_actual_entity`, `.static_power_w` |
| Gerät `voltage_l1/l2/l3_entity` | `devices[].voltage_entities[0..2]` |
| Gerät `phases` | `devices[].phases_fallback` (bei `"1,3"` gilt `3`) |
| Gerät `soc_entity`, `capacity_kwh` | `devices[].soc_entity`, `.capacity_kwh` |
| Gerät `charge_power_entity`, `discharge_power_entity` | gleichnamig |
| Gerät `power_entity`, `power_sign` | gleichnamig (Klasse `battery`) |

`devices[].reihenfolge` ist die 1-basierte Position in der Geräteliste der Add-on-Optionen.
`devices[].phases_entity` ist der Helfer `input_number.ems_<prefix>_anzahl_phase`, sofern das Gerät
in Ampere geregelt wird, sonst leer.

### Validierungsregeln

Die Prüfung gehört in `app/configuration.py` neben die bestehenden Regeln und liefert deutsche
Feldfehler im gewohnten `field_errors`-Format.

- **Netz:** Entweder `flow_grid_power_entity` **oder** das Paar
  `flow_grid_import_entity`/`flow_grid_export_entity`, nie beides. Sind beide Wege belegt: Fehler
  *„Entweder ein signierter Netzsensor oder getrennte Sensoren für Bezug und Einspeisung — nicht
  beides."*
- **Batterie:** Ist `flow_battery_label` oder `flow_battery_soc_entity` gesetzt, muss genau eine
  Leistungsvariante belegt sein — dieselbe Regel und derselbe Fehlertext-Stil wie bei der
  Geräteklasse `battery`.
- **`flow_publish: true`** verlangt mindestens einen belegten Standardwert. Sonst Fehler
  *„Für die Veröffentlichung wird mindestens ein Standardwert benötigt."*
- **`flow_pv_power_entities`:** jede Zeile braucht eine nichtleere `entity`; Duplikate sind ein
  Feldfehler.
- **`flow_icon`:** wenn belegt, muss es mit `mdi:` beginnen.
- Leere Werte sind überall gültig — die Karte kommt mit fehlenden Knoten zurecht.

Alles gespiegelt in `config.yaml` (`options:`, `schema:` und der Beschreibungstext oben) sowie in
`translations/de.yaml` und `translations/en.yaml`.

---

## Zielarchitektur der Veröffentlichung

```
 EMSController.run_cycle()        (unverändert)
        │  liefert CycleStatus + HA-Zustandsabbild
        ▼
 HEMSApp._run_cycle()             (app/main.py)
        │  nach erfolgreichem Zyklus
        ▼
 FlowPublisher.publish(status, states, options)      app/flow_publisher.py  ← NEU
        ├── build_config_payload()  → Verweise, Geräteliste, Anzeigeoptionen
        ├── build_status_payload()  → Kennzahlen, Rückfallwerte je Gerät
        ├── revision = sha256(config_payload)[:12]
        ├── schreibe config NUR wenn revision != last_revision
        │                    ODER Entität fehlt im Zustandsabbild
        └── schreibe status IMMER
                │
                ▼
        HAClient.set_state()      app/ha_client.py  ← NEU
                POST {HA_URL}/api/states/<entity_id>
```

Der Publisher hält genau zwei Dinge im Speicher: die zuletzt geschriebene Revision und den
Zeitpunkt des letzten Schreibens. Keine Datei, keine Datenbank — das HEMS hat bewusst keine eigene
Persistenz.

---

## API-Vertrag der eigenen Oberfläche

Ein neuer Endpunkt, nach dem Vorbild von `POST /api/config/sensors/test`:

```
GET api/flow/preview
```

Liefert **immer HTTP 200**. Es ist ein Diagnosewerkzeug; eine unvollständige Konfiguration ist
kein HTTP-Fehler.

```jsonc
{
  "publish_enabled": true,
  "config_entity": "sensor.skytech_hems_flow_config",
  "status_entity": "sensor.skytech_hems_flow_status",
  "revision": "a3f19c02b7d4",
  "zuletzt_geschrieben": "23.08.2026 18:04:12",   // "" wenn noch nie
  "config_payload": { /* wie in kontrakt.md, Abschnitt 3 */ },
  "status_payload": { /* wie in kontrakt.md, Abschnitt 4 */ },
  "aufgeloest": [                                  // je Verweis der aktuelle Zustand
    { "pfad": "standard.pv_power_entities[0]",
      "entity": "sensor.e3dc_leistung_ertrag_hausdach",
      "state": "3120.0", "value": 3120.0, "valid": true },
    { "pfad": "devices[heizstab].power_entity",
      "entity": "sensor.elwa_modbus_istleistung",
      "state": "unavailable", "value": null, "valid": false }
  ],
  "warnungen": ["Nutzlast über 12 KiB — Home Assistant zeichnet große Attribute nicht auf."]
}
```

`aufgeloest` ist das, was die Seite dem Benutzer zeigt: welcher Verweis gerade trägt und welcher
nicht. Die Werte kommen aus dem Zustandsabbild des letzten Zyklus, es wird keine zusätzliche
HA-Abfrage ausgelöst — dieselbe Regel wie bei `GET /api/config/entities`.

---

## Umsetzungsschritte

### 1. Optionen erweitern

`app/configuration.py`: die zwanzig `flow_*`-Schlüssel in `GLOBAL_DEFAULTS` aufnehmen,
Normalisierung und Validierung nach dem Muster der bestehenden Felder ergänzen. Die drei
Gerätefelder `flow_show`, `flow_icon`, `flow_color` in die gemeinsame Gerätenormalisierung
aufnehmen — sie gelten für **alle** Geräteklassen. `GLOBAL_KEYS_FORCING_SHUTDOWN` bleibt
unangetastet.

`config.yaml`: `options:` und `schema:` ergänzen, den Beschreibungstext um einen Absatz
„Flow Card" erweitern. `translations/de.yaml` und `translations/en.yaml` nachziehen.

**Akzeptanz:** `pytest -q` und `ruff check app tests` grün; eine bestehende Konfiguration ohne
`flow_*`-Schlüssel lädt unverändert und verhält sich bit-identisch wie vorher.

### 2. `HAClient.set_state()`

`app/ha_client.py`: eine Methode

```python
async def set_state(self, entity_id: str, state: str,
                    attributes: Optional[Dict[str, Any]] = None) -> bool:
    """Schreibt einen Zustand in die HA-Zustandsmaschine. Liefert Erfolg, wirft nie."""
```

`POST {_HA_URL}/api/states/{entity_id}`, Rumpf `{"state": ..., "attributes": {...}}`,
5-Sekunden-Timeout, Erfolg bei 200/201. Jeder Fehler wird auf `warning` protokolliert und als
`False` zurückgegeben. Kommentar im Kopf, der auf D-046 verweist.

**Akzeptanz:** Test mit einer Attrappe belegt: Nicht-2xx und Netzwerkfehler liefern `False` und
werfen nicht.

### 3. `app/flow_publisher.py`

Neu. Aufbau:

- `build_config_payload(options, devices, addon_version, now)` → dict nach
  [`kontrakt.md`](kontrakt.md) Abschnitt 3. Enthält die Ableitung von `power_kind`:

  | Gerät | `power_kind` |
  |---|---|
  | `class: controllable`, `output_unit: watt` | `watt` |
  | `class: controllable`, `output_unit: ampere` | `ampere` |
  | `class: binary` | `binary_static` |
  | `class: battery` mit `charge_power_entity`/`discharge_power_entity` | `battery_split` |
  | `class: battery` mit `power_entity`/`power_sign` | `battery_signed` |

  Die Steuer-Helfer je Gerät stammen aus derselben Quelle wie der Steuerung-Tab: die Funktionen
  `_ctrl_items_controllable`, `_ctrl_items_binary` und die Speichervariante in `app/main.py`.
  **Nicht duplizieren** — die Entity-IDs werden über die vorhandenen `key`-Felder
  (`freigabe`, `technische_freigabe`, `modus`, `prioritat`, `anforderung_*`) herausgesucht.
  Geräte mit `flow_show: false` und Geräte, die als `inactive_devices` gar nicht geladen wurden,
  kommen nicht in die Liste.

- `build_status_payload(status, now)` → dict nach [`kontrakt.md`](kontrakt.md) Abschnitt 4.
  `leistung_w` je Gerät: bei `controllable` das Feld `actual_w`, bei `binary` `power_actual_w`
  falls vorhanden, sonst `power_w` wenn `final_on`, sonst `0`, bei `battery` `netto_w`.

- `revision(payload)` → `sha256` der kanonisch sortierten JSON-Serialisierung, erste 12
  Hex-Zeichen. `erzeugt_am` und `revision` selbst gehen **nicht** in den Hash ein, sonst ändert er
  sich bei jedem Zyklus.

- `class FlowPublisher` mit `async def publish(...)`: Entscheidungslogik aus
  [`kontrakt.md`](kontrakt.md) Abschnitt 3, Warnung ab 12 KiB Nutzlast, alles in `try/except`.

Aufruf in `HEMSApp._run_cycle()` (`app/main.py`) direkt nach dem erfolgreichen Zyklus, vor dem
Setzen von `_last_cycle_at`. Bei `flow_publish: false` kehrt `publish()` sofort zurück.

**Akzeptanz:** Ein simulierter Zyklus mit der Beispielanlage erzeugt die Nutzlast aus
[`kontrakt.md`](kontrakt.md) Abschnitt 8 (bis auf Zeitstempel und Revision).

### 4. Diagnoseendpunkt

`GET api/flow/preview` in `app/main.py` registrieren und einen Handler ergänzen, der die beiden
Nutzlasten baut, jeden Verweis gegen das letzte Zustandsabbild auflöst und das Ergebnis wie oben
beschrieben zurückgibt. Immer 200.

**Akzeptanz:** Bei völlig leerer Flow-Konfiguration antwortet der Endpunkt mit 200,
`publish_enabled: false` und leeren Nutzlasten — kein Traceback im Log.

### 5. Neuer Bereich „Flow Card" in der Oberfläche

Bauanleitung ist der zuletzt hinzugefügte Bereich „Sensoren" (Commit `1b46ef9`); die Dateiliste
ist dieselbe.

- **Route** in `web/src/App.tsx`: `/flow-card` → `<FlowCard />`.
- **Sidebar** in `web/src/components/Layout.tsx`, Gruppe „Einrichtung", unterhalb von „Sensoren".
  Neues Icon in `web/src/components/Icon.tsx` — kein Inline-SVG in der Seite.
  **Wichtig:** Die Seite schreibt in denselben `ConfigDraft` wie die Konfigurationsseiten, deshalb
  muss `/flow-card` in die Ausnahmeliste der `guard()`-Funktion (neben `/konfiguration` und
  `/sensoren`) und bekommt denselben Dirty-Punkt `{dirty ? <span className="count">•</span> : null}`.
- **Seite** `web/src/pages/FlowCard.tsx`, aufgebaut wie `web/src/pages/KonfigurationGlobal.tsx`:
  `useConfigDraft()`, `useEffect(ensureLoaded, [ensureLoaded])`, Lade- und Fehlerzustand,
  `<PageHeader>`, `.card`-Sektionen, `<RestartOverlay />` bei `restarting`, abschließend
  `<ConfigActions />`.
- **Wiederverwenden statt neu bauen:** `EntityField`, `NumberField`, `TextField`, `SelectField`
  aus `web/src/components/ConfigFields.tsx`; für die PV-Liste das Zeilenmuster aus
  `web/src/components/FormulaVariablesField.tsx` samt den Klassen `.formula-vars` und
  `.formula-var-row`. Für die Geräteübersicht `.table-wrap` + `table.data` wie in
  `web/src/pages/KonfigurationGeraete.tsx`.
- **Typen** in `web/src/types.ts`: `ConfigOptions` und `ConfigDevice` um die neuen Felder
  erweitern, dazu die Antworttypen des Diagnoseendpunkts. Client-Methode `api.flowPreview()` in
  `web/src/api.ts` — Pfad ohne führenden Schrägstrich (D-036).

**Sektionen der Seite, in dieser Reihenfolge:**

| Sektion | Inhalt |
|---|---|
| **Veröffentlichung** | Schalter `flow_publish`, darunter die beiden Entitätsnamen als `.mono` zum Abschreiben, plus Hinweis, dass die Karte im Dashboard ohne weitere Konfiguration auskommt. |
| **Erzeugung** | PV-Sensoren als Zeilenliste mit Hinzufügen/Entfernen, `flow_pv_label`. |
| **Netz** | `flow_grid_power_entity` + `flow_grid_power_sign`, alternativ `flow_grid_import_entity`/`flow_grid_export_entity`, `flow_grid_label`. Hinweistext, dass genau ein Weg belegt sein darf. |
| **Haus** | `flow_house_power_entity` (optional), `flow_house_label`. Hinweis: leer heißt, die Karte rechnet die Bilanz aus den übrigen Werten. |
| **Batterie** | `flow_battery_label`, `flow_battery_soc_entity`, `flow_battery_capacity_kwh`, Leistungsvariante A oder B. Hinweis, dass der E3DC bewusst kein HEMS-Gerät ist und hier trotzdem hingehört. |
| **Geräte** | Tabelle aller konfigurierten HEMS-Geräte: Name, Klasse, dazu je Zeile `flow_show` als Schalter, `flow_icon` und `flow_color` als Textfeld. Leerzustand mit Verweis auf die Gerätekonfiguration. |
| **Anzeige** | `flow_title`, `flow_watt_threshold`, `flow_animation`, `flow_house_node`. |
| **Vorschau** | Ergebnis von `api.flowPreview()`: Revision, Zeitpunkt der letzten Veröffentlichung, Tabelle der aufgelösten Verweise mit `.pill ok`/`.pill err`, Warnungen als `.hint-box`. Aktualisierungsknopf, kein Dauerpolling. |

Gestaltungsregeln aus `docs/design-system.md` gelten unverändert: keine Literalfarben, keine
gestaltenden Inline-Styles, keine neue Klasse für einen Einzelfall, jede Icon-Schaltfläche mit
`aria-label`, deutsche Texte.

**Akzeptanz:** `cd web && npm run build` läuft fehlerfrei (`tsc --noEmit` inklusive); der Bereich
ist in Hell- und Dunkelmodus geprüft; ein Wechsel weg von der Seite mit ungespeicherten Änderungen
löst **keine** Rückfrage aus (sie ist Teil des Konfigurationsentwurfs).

### 6. Bundle bauen und mitcommitten

`cd web && npm run build` schreibt nach `app/static/`. Das erzeugte Bundle gehört in **denselben**
Commit (D-035); die CI bricht sonst mit einem Drift-Fehler ab.

### 7. Tests

Neu: `tests/test_flow_publisher.py`. Regeln aus `docs/test-strategie.md` — kein Netz, kein HA,
kein `sleep`, eine Aussage pro Test, sprechender deutscher Testname.

Pflichtfälle:

- `test_konfigurationsnutzlast_enthaelt_alle_geraeteklassen`
- `test_power_kind_wird_aus_geraeteklasse_und_einheit_abgeleitet`
- `test_revision_bleibt_stabil_bei_unveraendertem_zustand`
- `test_revision_ignoriert_zeitstempel`
- `test_konfiguration_wird_neu_geschrieben_wenn_entitaet_fehlt`
- `test_geraet_mit_flow_show_false_fehlt_in_der_nutzlast`
- `test_inaktives_geraet_fehlt_in_der_nutzlast`
- `test_publish_deaktiviert_schreibt_nichts`
- `test_schreibfehler_bricht_den_zyklus_nicht_ab`
- `test_statusnutzlast_liefert_rueckfallleistung_je_geraeteklasse`
- `test_warnung_ab_zwoelf_kibibyte_nutzlast`
- `test_leere_flow_konfiguration_erzeugt_gueltige_leere_nutzlast`

Ergänzend in den bestehenden Konfigurationstests: die neuen Validierungsregeln (Netz doppelt
belegt, Batterie ohne Leistungsvariante, `flow_icon` ohne `mdi:`-Präfix, doppelte PV-Entität).

Für die Oberfläche gibt es bewusst keine automatisierten Tests — `tsc --noEmit` im Build plus die
Sichtprüfung aus `docs/frontend.md`.

### 8. Dokumentation und Changelog — im selben Arbeitspaket

| Datei | Was |
|---|---|
| `docs/architektur.md` | Invariante 4 präzisieren (Entscheidung 2), Publisher in den Datenfluss aufnehmen |
| `docs/datenmodell.md` | Neuer Abschnitt „Veröffentlichte Kartendaten" mit beiden Sensoren als Datenvertrag, Verweis auf `vertrag_powerflow_card_hems/kontrakt.md` |
| `docs/api-referenz.md` | `GET api/flow/preview` |
| `docs/konfiguration.md` | Die zwanzig `flow_*`-Optionen, Empfehlung zum `recorder`-Ausschluss beider Entitäten |
| `docs/device_classes/global.md` | `flow_show`, `flow_icon`, `flow_color` als gemeinsame Gerätefelder |
| `docs/frontend.md` | Neuer Bereich „Flow Card" in der Seitenübersicht |
| `docs/design-entscheidungen.md` | **D-046** „Anzeigedaten als eigene HA-Sensoren veröffentlichen", **D-047** „Datenvertrag der Flow Card mit `schema_version`" |
| `docs/adr/D-046-flow-card-veroeffentlichung.md` | Neuer ADR nach `docs/adr/0000-vorlage.md`: Kontext, Entscheidung, verworfene Ingress-Variante, Folgen (Neustartverhalten, Recorder-Last) |
| `docs/roadmap.md` | Neuer Meilenstein **M5 — Power Flow Card**, Phasen mit Status |
| `CHANGELOG.md` | Unter `## [Unreleased]` → `### Hinzugefügt` |

D-046 ist die erste freie Nummer (der Log endet bei D-045).

### 9. Commit

Conventional Commits, Betreff deutsch, maximal 72 Zeichen, Push auf `claude/main`:

```
feat(flow-card): Kartendaten als HA-Sensoren veroeffentlichen
```

Vorher zwingend: `pytest -q` grün, `ruff check app tests` grün, `cd web && npm run build`
ausgeführt und das Bundle mit im Commit. `git add` gezielt, nie `git add -A` ohne vorherige
Prüfung von `git status`.

---

## Abnahmekriterien

1. Eine bestehende Anlage ohne `flow_*`-Optionen verhält sich nach dem Update **bit-identisch**
   wie vorher. Ohne `flow_publish: true` wird keine einzige Entität geschrieben.
2. Nach dem Einschalten der Veröffentlichung existieren beide Sensoren in den
   HA-Entwicklerwerkzeugen mit der Nutzlast aus [`kontrakt.md`](kontrakt.md).
3. Die Konfigurationsentität wird bei unveränderter Konfiguration **nicht** jeden Zyklus neu
   geschrieben — nachweisbar an einem konstanten `last_changed`.
4. Nach einem Home-Assistant-Neustart ist die Konfigurationsentität spätestens nach einem
   Regelintervall wieder da.
5. Ein im HEMS neu angelegtes Gerät erscheint innerhalb eines Zyklus in `devices[]`; ein auf
   `flow_show: false` gesetztes verschwindet.
6. Ein `unavailable` gewordener Sensor führt zu `valid: false` in der Vorschau und **nicht** zu
   einem Nullwert in der Nutzlast.
7. Ein erzwungener Schreibfehler (falsche Entity-ID) erzeugt eine Warnung im Log und lässt den
   Regelzyklus unbeeinflusst weiterlaufen.
8. `pytest -q`, `ruff check app tests` und `npm run build` sind grün; die CI meldet keinen
   Bundle-Drift.
9. Alle unter Schritt 8 genannten Dokumentationsdateien sind im selben Commit aktualisiert.

---

## Nicht Bestandteil dieses Auftrags

- Die Lovelace-Karte selbst. Sie entsteht im eigenen Repository nach
  [`plan-card.md`](plan-card.md).
- Eine Vorschau der gerenderten Karte innerhalb des Ingress-Panels. Die Seite zeigt die
  aufgelösten Werte als Tabelle, nicht die Grafik — das Diagramm zweimal zu bauen wäre zwei
  Wahrheiten.
- Historisierung oder Aggregation von Energiewerten (kWh je Tag). Der Vertrag trägt heute reine
  Leistungswerte; Energiefelder sind eine additive Erweiterung für später.
- Schreibende Aktionen aus der Karte heraus (Freigabe schalten, Priorität ändern). Die Karte
  öffnet den More-Info-Dialog, mehr nicht.
- Änderungen an der Regellogik. Der Regelzyklus bleibt in diesem Arbeitspaket unangetastet.
