# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jedem Merge nach `main` automatisch
um eine Patch-Stelle erhöht (siehe `.github/workflows/bump-version.yaml`).

## [Unreleased]

### Hinzugefügt
- **`/api/status` liefert für Ampere-Geräte zusätzlich `schutz_a`.** Der effektive
  Mindestleistungs-Schutz (`schutz_w`, Watt) wird über Phasenanzahl × Spannung nach Ampere
  umgerechnet und im Gerätestatus mitgegeben – analog zum bestehenden `new_a`. Ohne dieses
  Feld konnten Ampere-Konsumenten (Energy Pilot) den Schutz nicht einheitengleich mit ihrem
  Ampere-Vorschlag (`geschutzte_mindestleistung_a_vorschlag`) vergleichen: Watt-Geräte hatten
  `schutz_w`, Ampere-Geräte (Wallbox) gar kein Pendant, sodass die Plan-Rückkopplung dort
  „unbekannt" statt eines Vergleichs zeigte.

### Geändert
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
