# Datenvertrag: Skytech Power Flow Card

> **Status:** Entwurf v1 — Grundlage der Umsetzung. Stand 23.08.2026.
>
> **Geltungsbereich:** Diese Datei ist der **gemeinsame** Vertrag zwischen zwei Repositories und
> wird in beide kopiert:
>
> - **Skytech HEMS** (Add-on) — der *Erzeuger*. Umsetzung nach [`plan-hems.md`](plan-hems.md).
> - **Skytech Power Flow Card** (Lovelace-Karte) — der *Verbraucher*. Umsetzung nach
>   [`plan-card.md`](plan-card.md).
>
> **Bei Widerspruch gilt diese Datei.** Weder Erzeuger noch Verbraucher darf ein Feld einseitig
> umbenennen, umdeuten oder entfernen. Additive Felder sind jederzeit erlaubt.

---

## Inhalt

1. [Ziel und Grundidee](#1-ziel-und-grundidee)
2. [Transportweg](#2-transportweg)
3. [Entität 1 — `sensor.skytech_hems_flow_config`](#3-entität-1--sensorskytech_hems_flow_config)
4. [Entität 2 — `sensor.skytech_hems_flow_status`](#4-entität-2--sensorskytech_hems_flow_status)
5. [Leistungsermittlung je `power_kind`](#5-leistungsermittlung-je-power_kind)
6. [Zustände, Ausfälle und Rückfallebenen](#6-zustände-ausfälle-und-rückfallebenen)
7. [Versionierung und Verträglichkeit](#7-versionierung-und-verträglichkeit)
8. [Vollständiges Beispiel](#8-vollständiges-beispiel)
9. [Gefahren und wie der Vertrag sie entschärft](#9-gefahren-und-wie-der-vertrag-sie-entschärft)

---

## 1. Ziel und Grundidee

Die Karte soll den Leistungsfluss im Haus zeichnen — Erzeugung, Netz, Speicher, Haus und die
einzelnen Verbraucher — **ohne dass im Lovelace-Editor eine einzige Entität gepflegt wird**.

Der entscheidende Gedanke: Die „Individual Devices" des Vorbilds
[`power-flow-card-plus`](https://github.com/flixlix/power-flow-card-plus) sind im Bestand exakt
die Geräte, die das HEMS ohnehin schon kennt und regelt. Das HEMS ist damit die einzige Quelle
der Wahrheit für die Geräteliste. Was es bisher **nicht** kennt, sind die Standardwerte der
Anlage (PV-Leistung, Netzleistung, Hausleistung, E3DC-SoC und -Leistung); die werden im HEMS im
neuen Bereich „Flow Card" gepflegt.

Der Vertrag besteht deshalb aus zwei Teilen:

| Teil | Inhalt | Ändert sich |
|---|---|---|
| **Konfiguration** | Layout, Anzeigeoptionen, Geräteliste, **Verweise** auf HA-Entitäten | selten (nur bei Konfigurationsänderung im HEMS) |
| **Status** | Kennzahlen des letzten Regelzyklus, Rückfallwerte je Gerät | jeden Zyklus (Standard 30 s) |

**Grundregel des Vertrags:** Der Erzeuger liefert **Verweise, keine Messwerte**. Die Karte löst
die Verweise selbst gegen `hass.states` auf. Dadurch aktualisiert die Grafik im Takt von Home
Assistant und nicht im 30-Sekunden-Takt des HEMS, und die Karte bleibt lesbar, wenn das Add-on
gerade gestoppt ist.

**Zweite Grundregel:** Entity-IDs werden **niemals** auf der Karte aus Präfixen zusammengesetzt.
Jede benötigte Entity-ID steht ausgeschrieben im Vertrag. Das HEMS erzeugt seine Helfernamen nach
dem Muster `<domain>.ems_<prefix>_<suffix>`, aber dieses Muster ist Wissen des Erzeugers und
bleibt es.

---

## 2. Transportweg

Das HEMS schreibt beide Nutzlasten über die Home-Assistant-REST-API in die Zustandsmaschine:

```
POST {HA_URL}/api/states/sensor.skytech_hems_flow_config
POST {HA_URL}/api/states/sensor.skytech_hems_flow_status
```

Die Karte liest ausschließlich `hass.states[...]`. Es gibt **keinen** HTTP-Aufruf von der Karte
zum Add-on, keine Ingress-Session, kein Polling und keine Adminrechte-Anforderung.

### Warum nicht über Ingress?

Eine Lovelace-Karte läuft im HA-Frontend, nicht unter `/api/hassio_ingress/<token>/`. Um dorthin
zu gelangen, müsste sie sich per WebSocket die Ingress-URL des Add-ons besorgen und eine
Ingress-Session samt Cookie unterhalten — nur für Administratoren möglich, an HA-Interna gekoppelt
und auf Polling angewiesen. Der Entitätsweg ist HA-nativ, für jeden Benutzer sichtbar und liefert
Aktualisierungen ereignisgesteuert.

### Preis dieses Weges — offen benannt

1. **Es bricht Invariante 4 des HEMS** („Geschrieben werden ausschließlich `input_*`-Helfer").
   Das ist bewusst so entschieden (**D-046**) und wird in `docs/architektur.md` nachgezogen. Die
   Invariante bleibt für den **Regelpfad** unangetastet: Aus dem Flow-Publisher wird nichts
   geschaltet, er schreibt reine Anzeigedaten.
2. **Per `POST /api/states` erzeugte Entitäten überleben einen HA-Neustart nicht.** Sie sind
   Zustandsmaschinen-Einträge ohne Integration dahinter. Der Erzeuger muss das erkennen und neu
   schreiben — Regel dazu in Abschnitt 3.
3. **Recorder-Last.** Die Statusentität ändert sich jeden Zyklus. Beide Entitäten gehören in die
   `recorder`-Ausschlussliste des Benutzers, sofern keine Historie gewünscht ist.

---

## 3. Entität 1 — `sensor.skytech_hems_flow_config`

Trägt Layout und Verweise. **Ohne diese Entität kann die Karte nichts zeichnen.**

| Merkmal | Wert |
|---|---|
| `entity_id` | `sensor.skytech_hems_flow_config` |
| `state` | Revisions-Kurzhash der Nutzlast, 12 Hex-Zeichen (z. B. `a3f19c02b7d4`) |
| `friendly_name` | `Skytech HEMS Flow-Konfiguration` |
| `icon` | `mdi:transit-connection-variant` |

Es gibt bewusst **keine** `unit_of_measurement` und **keine** `device_class`: Der Zustand ist eine
Kennung, kein Messwert.

### Schreibregel des Erzeugers

Geschrieben wird **genau dann**, wenn eine der beiden Bedingungen zutrifft:

1. Der berechnete Revisionshash weicht vom zuletzt geschriebenen ab, **oder**
2. `sensor.skytech_hems_flow_config` fehlt im HA-Zustandsabbild des laufenden Zyklus.

Bedingung 2 deckt den HA-Neustart ab und kostet nichts: Das HEMS liest den vollständigen
HA-Zustand ohnehin einmal pro Zyklus. Nach einem HA-Neustart ist die Karte damit spätestens nach
einem Regelintervall wieder vollständig.

### Attribute

```jsonc
{
  "schema_version": 1,                       // int, siehe Abschnitt 7
  "addon_version": "2.1.0",                  // string, Version aus config.yaml
  "revision": "a3f19c02b7d4",                // string, identisch mit state
  "erzeugt_am": "23.08.2026 18:04:12",       // string, Berliner Zeit, TT.MM.JJJJ hh:mm:ss

  "anzeige": {
    "titel": "Leistungsfluss",               // string, Kartenüberschrift; leer = keine Überschrift
    "watt_schwelle": 1000,                   // int, ab diesem Betrag in kW statt W anzeigen
    "animation": true,                       // bool, wandernde Punkte an/aus
    "haus_knoten_anzeigen": true,            // bool, Haus als eigener Knoten
    "freigabe_ring_farbe": ""                // string, CSS-Farbe; leer = weißer Standardwert
  },

  "standard": {
    "pv_power_entities": [                   // Liste, wird summiert; leer = kein PV-Knoten
      "sensor.e3dc_leistung_ertrag_hausdach",
      "sensor.e3dc_leistung_ertrag_garagendach"
    ],
    "pv_detail_entities": [                  // Liste, wird NICHT summiert; nur Aufschlüsselung
      "sensor.string_sued",
      "sensor.string_ost"
    ],
    "pv_label": "Photovoltaik",              // string, Anzeigename des Knotens

    "grid_power_entity": "sensor.e3dc_leistung_netz",
    "grid_power_sign": "positiv_bezug",      // "positiv_bezug" | "positiv_einspeisung"
    "grid_import_entity": "",                // Alternative: getrennte Sensoren …
    "grid_export_entity": "",                // … dann bleibt grid_power_entity leer
    "grid_label": "Netz",

    "house_power_entity": "sensor.e3dc_leistung_haus",  // leer = Karte rechnet die Bilanz
    "house_label": "Haus",

    // Navigationsziele je Knoten. Leer = Klick öffnet den More-Info-Dialog.
    "pv_navigation": "/dashboard-pv/pv",
    "grid_navigation": "/dashboard-pv/netz",
    "house_navigation": "/dashboard-pv/ems",
    "rest_navigation": "/dashboard-pv/ueberschussverbraucher",

    "batterie": {                            // null oder fehlend = kein Batterieknoten
      "label": "E3DC",
      "soc_entity": "sensor.e3dc_batterie_soc",
      "capacity_kwh": null,                  // float oder null, nur Anzeige.
                                             // Das Skytech HEMS befüllt es nicht: es braucht die
                                             // Kapazität für nichts, und ein Pflichtfeld dafür hat
                                             // einmal den Add-on-Start blockiert. Ein anderer
                                             // Erzeuger darf eine Zahl liefern.
      "power_entity": "",                    // Variante A: ein signierter Sensor …
      "power_sign": "positiv_laden",         // … "positiv_laden" | "positiv_entladen"
      "charge_power_entity": "sensor.e3dc_leistung_batterie_laden",     // Variante B …
      "discharge_power_entity": "sensor.e3dc_leistung_batterie_entladen", // … zwei Sensoren
      "navigation": "/dashboard-pv/batterie"
    }
  },

  "devices": [ /* siehe unten */ ],

  "hems": {
    "ems_enabled_entity": "input_boolean.ems_pv_regelung_aktiv",
    "regelmodus_entity": "input_select.ems_regelmodus",
    "panel_pfad": "/hassio/ingress/skytech_hems",  // string, für „Im HEMS öffnen"-Verweise
    "interval_s": 30                               // int, Regelintervall; Grundlage von „veraltet"
  }
}
```

`hems.interval_s` ist **additiv ergänzt** (23.08.2026) und erhöht `schema_version` nicht. Ohne
diesen Wert könnte die Karte die Regel „älter als 5 × Regelintervall" aus Abschnitt 6 gar nicht
anwenden — sie stand im Vertrag, die Größe dazu fehlte. Fehlt das Feld (älterer Erzeuger), nimmt
die Karte `30` an.

`anzeige.freigabe_ring_farbe` ist **additiv ergänzt** (04.09.2026) und erhöht `schema_version`
nicht. Der Ring um ein freigegebenes Gerät war fest auf die Akzentfarbe der Karte verdrahtet; das
Feld macht ihn je Anlage einstellbar, im HEMS unter Flow-Card-Konfiguration gepflegt. Ein
beliebiger gültiger CSS-Farbwert überschreibt den Ring, leer oder fehlend (älterer Erzeuger)
ergibt den weißen Standardwert. Der graue gestrichelte Ring eines gesperrten Geräts bleibt davon
unberührt — er zeigt unabhängig von diesem Feld immer dieselbe feste Farbe.

**Navigationsziele, verbindlich** (additiv ergänzt 27.08.2026, `schema_version` bleibt `1`):

Ein Klick auf einen Knoten springt auf die hinterlegte Dashboard-Ansicht; ohne Ziel öffnet er wie
bisher den More-Info-Dialog der Leitentität. Zulässig ist **ausschließlich ein Pfad innerhalb
derselben Home-Assistant-Instanz**:

- er beginnt mit `/`,
- er beginnt **nicht** mit `//` — das wäre protokollrelativ und führte auf einen fremden Host,
- er enthält **keinen** Doppelpunkt — der ließe `http://…` und `javascript:…` durch,
- er enthält keinen Leerraum.

Der Erzeuger prüft das, und **die Karte prüft es erneut**. Sie springt nicht ungeprüft dorthin,
wohin ein Attributwert zeigt. Ein Ziel, dessen Ansicht es nicht mehr gibt, ist kein Fehler: Home
Assistant zeigt dann seine eigene Meldung, die Karte zeichnet unverändert weiter.

**Vorzeichenkonventionen, verbindlich:**

`pv_detail_entities` ist **additiv ergänzt** (24.08.2026) und erhöht `schema_version` nicht. Es
löst ein reales Problem: eine Anlage hat oft einen Sensor für die Systemleistung **und** je einen
je String. Beides in `pv_power_entities` zu legen verdoppelte die Erzeugung. Der Erzeuger legt
deshalb genau eine der beiden Sichten in die Summe und die andere hierher; die Karte summiert
`pv_detail_entities` **nie**, sondern zeigt sie als Aufschlüsselung am Erzeugungsknoten. Fehlt das
Feld (älterer Erzeuger), gibt es keine Aufschlüsselung — kein Fehler.

Verbindlich: Eine Entität steht **entweder** in `pv_power_entities` **oder** in
`pv_detail_entities`, nie in beiden.

- `grid_power_sign: "positiv_bezug"` — positiver Wert bedeutet Bezug aus dem Netz, negativer
  Einspeisung. `"positiv_einspeisung"` bedeutet das Gegenteil.
- `batterie.power_sign: "positiv_laden"` — positiver Wert bedeutet Laden, negativer Entladen.
  `"positiv_entladen"` bedeutet das Gegenteil. Die Bezeichner sind absichtlich identisch mit dem
  bestehenden Gerätefeld `power_sign` der HEMS-Speicherklasse.
- Es gilt entweder `power_entity` **oder** das Paar `charge_power_entity` /
  `discharge_power_entity`, nie beides. Analog für Netz.

### `devices[]` — ein Eintrag je sichtbarem HEMS-Gerät

Die Reihenfolge im Array ist die Anzeigereihenfolge. Geräte, die im HEMS auf „nicht anzeigen"
stehen, sind gar nicht erst enthalten.

```jsonc
{
  "id": "heizstab",                          // string, = HEMS-Feld `name`, STABILE IDENTITÄT
  "label": "Heizstab",                       // string, Anzeigename, darf sich jederzeit ändern
  "class": "controllable",                   // "controllable" | "binary" | "battery"
  "power_kind": "watt",                      // siehe Abschnitt 5
  "icon": "mdi:radiator",                    // string, mdi-Name; leer = Karte wählt nach class
  "farbe": "",                               // string, CSS-Farbe als Override; leer = Akzent
  "navigation": "/dashboard-pv/heizstab",    // string, Ziel eines Klicks; leer = More-Info
  "reihenfolge": 1,                          // int, nur informativ; maßgeblich ist die Arrayfolge

  // Leistungsermittlung — je nach power_kind ist nur eine Teilmenge belegt
  "power_entity": "sensor.elwa_modbus_istleistung",
  "power_sign": "",                          // nur bei power_kind "battery_signed"
  "switch_entity": "",                       // nur bei "binary_static"
  "power_actual_entity": "",                 // optional bei "binary_static", schlägt static_power_w
  "static_power_w": null,                    // float oder null, nur bei "binary_static"
  "voltage_entities": ["", "", ""],          // nur bei "ampere", L1/L2/L3; leer = 230 V annehmen
  "phases_entity": "",                       // nur bei "ampere", liefert die Phasenzahl
  "phases_fallback": 3,                      // int, wenn phases_entity leer oder ungültig
  "charge_power_entity": "",                 // nur bei "battery_split"
  "discharge_power_entity": "",              // nur bei "battery_split"
  "soc_entity": "",                          // nur class "battery"
  "capacity_kwh": null,                      // float oder null, nur class "battery"

  // Steuer-Helfer des HEMS, ausgeschrieben. Die Karte nutzt sie für Zusatzanzeigen
  // und als Ziel des More-Info-Dialogs. Ein leerer Wert heißt „gibt es nicht".
  "control": {
    "freigabe": "input_boolean.ems_heizstab_freigabe",
    "technische_freigabe": "input_boolean.ems_heizstab_technische_freigabe",
    "modus": "input_select.ems_heizstab_modus",
    "prioritat": "input_number.ems_heizstab_prioritat",
    "anforderung": "input_number.ems_heizstab_anforderung_leistung_w"
  }
}
```

`id` ist die einzige Identität. Die Karte darf Zustände (z. B. eine gemerkte Auswahl) an `id`
festmachen, **nie** an `label` oder an der Position im Array.

---

## 4. Entität 2 — `sensor.skytech_hems_flow_status`

Trägt die Kennzahlen des letzten Regelzyklus und die Rückfallwerte. **Optional:** Fehlt sie, ist
die Karte voll funktionsfähig; es entfallen lediglich die HEMS-Abzeichen und die Rückfallebene.

| Merkmal | Wert |
|---|---|
| `entity_id` | `sensor.skytech_hems_flow_status` |
| `state` | `pool_w` — der aktuell verteilbare Überschuss, gerundet |
| `unit_of_measurement` | `W` |
| `device_class` | `power` |
| `state_class` | `measurement` |
| `friendly_name` | `Skytech HEMS Flow-Status` |
| `icon` | `mdi:solar-power` |

Wird nach **jedem** abgeschlossenen Regelzyklus geschrieben.

### Attribute

```jsonc
{
  "schema_version": 1,
  "last_cycle_at": "23.08.2026 18:04:12",   // Berliner Zeit, TT.MM.JJJJ hh:mm:ss
  "cycle_count": 412,

  "ems_enabled": true,                       // bool
  "global_mode": "manuell",                  // string
  "hard_lockout": false,                     // bool, true = Regelung gesperrt
  "residual_w": 1840.0,                      // float, Überschuss wie gemessen
  "hems_last_w": 1400.0,                     // float, vom HEMS angeforderte Last
  "hausdefizit_w": 0.0,                      // float, Unterdeckung des Hauses
  "pool_w": 3240.0,                          // float, identisch mit state

  // Rückfallebene je Gerät, Schlüssel ist devices[].id
  "devices": {
    "heizstab": {
      "leistung_w": 1400.0,                  // float oder null
      "runtime_active": true,                // bool, regelt gerade mit
      "inactive_reasons": []                 // string[], deutsche Klartextgründe
    }
  }
}
```

`inactive_reasons` ist **nach Handlungsrelevanz sortiert**: der erste Eintrag ist der Grund, den
der Nutzer am ehesten selbst beheben kann. Die Karte zeigt genau diesen einen. Konkret steht die
Bedienfreigabe deshalb vor der technischen Freigabe — sind beide aus, lautet der erste Eintrag
`"Freigabe aus"`. Der Erzeuger darf die Reihenfolge nicht als beliebig behandeln.

`leistung_w` ist bewusst **nicht** der Primärwert. Sie wird nur benutzt, wenn die Karte den
Direktwert nicht auflösen kann — siehe Abschnitt 6.

---

## 5. Leistungsermittlung je `power_kind`

Die Karte rechnet selbst. Alle Ergebnisse sind **Watt**, positiv bedeutet Verbrauch bzw. Laden.

| `power_kind` | Gilt für | Herleitung |
|---|---|---|
| `watt` | `controllable` mit `output_unit: watt` | Zustand von `power_entity` direkt |
| `ampere` | `controllable` mit `output_unit: ampere` | `power_entity` [A] × Summe der belegten `voltage_entities` (je fehlender oder ungültiger Spannung 230 V annehmen, begrenzt auf die Phasenzahl) |
| `binary_static` | `binary` | `switch_entity` ist `on` → `power_actual_entity` falls gesetzt und gültig, sonst `static_power_w`. Ist der Schalter `off` → `0` |
| `battery_split` | `battery` mit zwei Sensoren | `charge_power_entity` − `discharge_power_entity` |
| `battery_signed` | `battery` mit einem Sensor | Zustand von `power_entity`, bei `power_sign: "positiv_entladen"` mit −1 multipliziert |

**Phasenzahl bei `ampere`:** Zustand von `phases_entity` als ganze Zahl; ist er leer, `unknown`,
`unavailable` oder kein gültiger Wert aus `{1, 3}`, gilt `phases_fallback`. Bei einer Phase wird
nur `voltage_entities[0]` verwendet, bei drei Phasen alle drei.

Der Erzeuger setzt `power_kind` autoritativ aus der Gerätekonfiguration. Die Karte leitet ihn
**nicht** aus `class` ab — dieselbe Klasse kann verschiedene Varianten haben.

---

## 6. Zustände, Ausfälle und Rückfallebenen

Jeder aufgelöste Wert hat genau einen von drei Zuständen:

| Zustand | Wann | Darstellung auf der Karte |
|---|---|---|
| **gültig** | Entität vorhanden und in eine endliche Zahl wandelbar | Zahl, normale Farbe |
| **unbekannt** | Entität fehlt, ist `unavailable`/`unknown` oder nicht wandelbar, und es gibt keinen Rückfallwert | `—` in gedämpfter Farbe, Kante wird **nicht** gezeichnet |
| **ersetzt** | Direktwert unbekannt, aber `status.devices[id].leistung_w` liefert eine Zahl | Zahl mit gedämpfter Kennzeichnung „aus HEMS-Status" |

**Verbindlich: „unbekannt" wird nie als `0` gezeichnet.** Eine fehlende Messung sieht sonst aus
wie ein ausgeschaltetes Gerät, und das ist die gefährlichere Verwechslung.

Auflösungsreihenfolge je Gerät:

1. Direktwert nach Abschnitt 5 aus `hass.states`.
2. Fällt der aus: `sensor.skytech_hems_flow_status` → `devices[id].leistung_w`.
3. Fällt auch die aus: Zustand **unbekannt**.

### Weitere Ausfälle

| Fall | Verhalten der Karte |
|---|---|
| `sensor.skytech_hems_flow_config` fehlt | Deutscher Klartexthinweis statt Grafik: *„Das Skytech HEMS veröffentlicht noch keine Kartendaten. Im HEMS-Panel unter ‚Flow Card' die Veröffentlichung einschalten."* |
| `schema_version` höher als unterstützt | Hinweis, die Karte zu aktualisieren. Kein Zeichenversuch. |
| `devices` leer | Grafik ohne Geräteknoten zeichnen, kein Fehler. Ein Haus ohne HEMS-Geräte ist ein gültiger Zustand. |
| Navigationsziel zeigt auf eine gelöschte Ansicht | Kein Fehler der Karte. Home Assistant meldet die unbekannte Ansicht selbst. |
| Navigationsziel ist kein Pfad dieser Instanz | Die Karte ignoriert es und öffnet den More-Info-Dialog. |
| `standard.pv_power_entities` leer | Kein PV-Knoten, kein Fehler. Eine gefüllte `pv_detail_entities` allein erzeugt ebenfalls keinen Knoten — sie beschreibt nur, woraus sich die Erzeugung zusammensetzt. |
| `hard_lockout: true` | Abzeichen „HEMS gesperrt" am Kartenkopf. Werte werden weiter gezeichnet. |
| `ems_enabled: false` | Abzeichen „HEMS aus". Werte werden weiter gezeichnet. |
| Statusentität älter als 5 × Regelintervall (`hems.interval_s`, sonst 30 s) | Abzeichen „HEMS-Daten veraltet" mit Zeitpunkt. Gemessen wird am `last_updated` der Entität, nicht am formatierten Zeitstempel — der ist für Menschen, nicht zum Rechnen. |

---

## 7. Versionierung und Verträglichkeit

- `schema_version` ist eine ganze Zahl, aktuell **1**.
- **Additive Änderungen erhöhen sie nicht.** Neue optionale Felder, neue `power_kind`-Werte mit
  dokumentiertem Rückfallverhalten und neue Attribute sind jederzeit erlaubt. Die Karte ignoriert,
  was sie nicht kennt.
- **Erhöht wird nur bei brechenden Änderungen:** ein Feld entfällt, wird umbenannt oder ändert
  seine Bedeutung oder Einheit.
- Die Karte prüft beim Lesen: `schema_version > UNTERSTÜTZTE_VERSION` → Hinweis statt Grafik.
  `schema_version < UNTERSTÜTZTE_VERSION` → die Karte muss ältere Verträge weiter lesen können,
  solange sie dokumentiert unterstützt werden.
- Beide Repositories versionieren unabhängig nach Semantic Versioning. Der Vertrag ist die
  einzige Kopplung.

---

## 8. Vollständiges Beispiel

Anlage mit zwei PV-Feldern, E3DC-Speicher (kein HEMS-Gerät), Heizstab, Wallbox und zwei
Heizlüftern.

**`sensor.skytech_hems_flow_config`** — `state: "a3f19c02b7d4"`

```json
{
  "schema_version": 1,
  "addon_version": "2.1.0",
  "revision": "a3f19c02b7d4",
  "erzeugt_am": "23.08.2026 18:04:12",
  "anzeige": { "titel": "Leistungsfluss", "watt_schwelle": 1000, "animation": true, "haus_knoten_anzeigen": true },
  "standard": {
    "pv_power_entities": ["sensor.e3dc_leistung_ertrag_hausdach", "sensor.e3dc_leistung_ertrag_garagendach"],
    "pv_detail_entities": [],
    "pv_label": "Photovoltaik",
    "grid_power_entity": "sensor.e3dc_leistung_netz",
    "grid_power_sign": "positiv_bezug",
    "grid_import_entity": "",
    "grid_export_entity": "",
    "grid_label": "Netz",
    "house_power_entity": "sensor.e3dc_leistung_haus",
    "house_label": "Haus",
    "batterie": {
      "label": "E3DC",
      "soc_entity": "sensor.e3dc_batterie_soc",
      "capacity_kwh": 19.5,
      "power_entity": "",
      "power_sign": "positiv_laden",
      "charge_power_entity": "sensor.e3dc_leistung_batterie_laden",
      "discharge_power_entity": "sensor.e3dc_leistung_batterie_entladen"
    }
  },
  "devices": [
    {
      "id": "heizstab", "label": "Heizstab", "class": "controllable", "power_kind": "watt",
      "icon": "mdi:radiator", "farbe": "", "reihenfolge": 1,
      "power_entity": "sensor.elwa_modbus_istleistung",
      "power_sign": "", "switch_entity": "", "power_actual_entity": "", "static_power_w": null,
      "voltage_entities": ["", "", ""], "phases_entity": "", "phases_fallback": 3,
      "charge_power_entity": "", "discharge_power_entity": "", "soc_entity": "", "capacity_kwh": null,
      "control": {
        "freigabe": "input_boolean.ems_heizstab_freigabe",
        "technische_freigabe": "input_boolean.ems_heizstab_technische_freigabe",
        "modus": "input_select.ems_heizstab_modus",
        "prioritat": "input_number.ems_heizstab_prioritat",
        "anforderung": "input_number.ems_heizstab_anforderung_leistung_w"
      }
    },
    {
      "id": "wallbox_1", "label": "Wallbox", "class": "controllable", "power_kind": "ampere",
      "icon": "mdi:ev-station", "farbe": "", "reihenfolge": 2,
      "power_entity": "sensor.wallbox_1_istleistung",
      "power_sign": "", "switch_entity": "", "power_actual_entity": "", "static_power_w": null,
      "voltage_entities": ["", "", ""], "phases_entity": "input_number.ems_wallbox_anzahl_phase",
      "phases_fallback": 3,
      "charge_power_entity": "", "discharge_power_entity": "", "soc_entity": "", "capacity_kwh": null,
      "control": {
        "freigabe": "input_boolean.ems_wallbox_freigabe",
        "technische_freigabe": "input_boolean.ems_wallbox_technische_freigabe",
        "modus": "input_select.ems_wallbox_modus",
        "prioritat": "input_number.ems_wallbox_prioritat",
        "anforderung": "input_number.ems_wallbox_anforderung_leistung_a"
      }
    },
    {
      "id": "heizlufter_1", "label": "Heizlüfter 1", "class": "binary", "power_kind": "binary_static",
      "icon": "mdi:fan", "farbe": "", "reihenfolge": 3,
      "power_entity": "", "power_sign": "",
      "switch_entity": "switch.heizlufter", "power_actual_entity": "", "static_power_w": 1500,
      "voltage_entities": ["", "", ""], "phases_entity": "", "phases_fallback": 3,
      "charge_power_entity": "", "discharge_power_entity": "", "soc_entity": "", "capacity_kwh": null,
      "control": {
        "freigabe": "input_boolean.ems_heizlufter_1_freigabe",
        "technische_freigabe": "input_boolean.ems_heizlufter_1_technische_freigabe",
        "modus": "input_select.ems_heizlufter_1_modus",
        "prioritat": "input_number.ems_heizlufter_1_prioritat",
        "anforderung": "input_boolean.ems_heizlufter_1_anforderung_an"
      }
    }
  ],
  "hems": {
    "ems_enabled_entity": "input_boolean.ems_pv_regelung_aktiv",
    "regelmodus_entity": "input_select.ems_regelmodus",
    "panel_pfad": "/hassio/ingress/skytech_hems",
    "interval_s": 30
  }
}
```

**`sensor.skytech_hems_flow_status`** — `state: "3240"`

```json
{
  "schema_version": 1,
  "last_cycle_at": "23.08.2026 18:04:12",
  "cycle_count": 412,
  "ems_enabled": true,
  "global_mode": "manuell",
  "hard_lockout": false,
  "residual_w": 1840.0,
  "hems_last_w": 1400.0,
  "hausdefizit_w": 0.0,
  "pool_w": 3240.0,
  "devices": {
    "heizstab":     { "leistung_w": 1400.0, "runtime_active": true,  "inactive_reasons": [] },
    "wallbox_1":    { "leistung_w": 0.0,    "runtime_active": true,  "inactive_reasons": [] },
    "heizlufter_1": { "leistung_w": 0.0,    "runtime_active": false, "inactive_reasons": ["Freigabe aus"] }
  }
}
```

---

## 9. Gefahren und wie der Vertrag sie entschärft

### H-1 · Fehlende Messung sieht aus wie Stillstand (hoch)

Ein `unavailable`-Sensor, der als `0 W` gezeichnet wird, ist von einem ausgeschalteten Gerät nicht
zu unterscheiden. **Entschärfung:** Abschnitt 6 verbietet die Null-Ersetzung; unbekannte Werte
erscheinen als `—` und ohne Flusslinie.

### H-2 · Entität verschwindet nach HA-Neustart (hoch)

`POST /api/states` erzeugt keinen dauerhaften Eintrag. **Entschärfung:** Der Erzeuger prüft jeden
Zyklus, ob die Konfigurationsentität im Zustandsabbild vorhanden ist, und schreibt sie sonst neu
(Abschnitt 3). Die Karte zeigt in der Lücke ihren Klartexthinweis statt eines Fehlers.

### H-3 · Doppelte Zählung der Geräteleistung (mittel)

Die HEMS-Geräte sind Teil der Hausleistung. Werden sie zusätzlich zum Hausknoten gezeichnet,
erscheint mehr Verbrauch als vorhanden. **Entschärfung:** Die Karte hängt Geräte **am** Hausknoten
auf und zieht ihre Summe von der Hausleistung ab; der Rest ist „übriges Haus". Regel ausformuliert
in [`plan-card.md`](plan-card.md).

### H-4 · Vorzeichenverwechslung bei Netz und Batterie (mittel)

Anlagen zählen unterschiedlich. **Entschärfung:** `grid_power_sign` und `power_sign` sind
Pflichtangaben mit genau zwei erlaubten Werten; die Bezeichner sind mit den bestehenden
HEMS-Optionen wortgleich, damit keine zweite Konvention entsteht.

### H-5 · Auseinanderlaufen der beiden Repositories (mittel)

Zwei Repos, ein Vertrag. **Entschärfung:** `schema_version`, die Additivitätsregel aus Abschnitt 7
und die Vorgabe, dass diese Datei in beide Repos kopiert wird und dort die höhere Autorität hat
als jede lokale Beschreibung.

### H-6 · Recorder-Datenbank läuft voll (niedrig)

Eine Statusentität mit Attributobjekt alle 30 Sekunden. **Entschärfung:** Die Trennung in zwei
Entitäten hält die große Nutzlast aus dem Zyklus heraus; die Empfehlung zum `recorder`-Ausschluss
steht in der Dokumentation beider Repos.

### H-7 · Attributgrenze von Home Assistant (niedrig)

Home Assistant schließt Attribute jenseits von 16 KiB von der Aufzeichnung aus. Bei rund
zwanzig Geräten liegt die Nutzlast bei etwa 8 KiB. **Entschärfung:** Der Erzeuger protokolliert
eine Warnung, sobald die Nutzlast 12 KiB überschreitet.
