# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jedem Merge nach `main` automatisch
um eine Patch-Stelle erhöht (siehe `.github/workflows/bump-version.yaml`).

## [Unreleased]

### Geändert
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
