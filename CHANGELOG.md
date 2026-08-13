# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jedem Merge nach `main` automatisch
um eine Patch-Stelle erhöht (siehe `.github/workflows/bump-version.yaml`).

## [Unreleased]

### Hinzugefügt
- **Roher Schutz-Sockel im Gerätestatus (`geschuetzte_mindestleistung_w`/`_a`).**
  `ControllableDevice.to_status_dict` liefert jetzt zusätzlich zum effektiven Schutz
  `schutz_w`/`schutz_a` auch den **rohen**, vom User gepflegten Sockel
  `geschuetzte_mindestleistung_w` (Watt) bzw. `geschuetzte_mindestleistung_a` (Ampere).
  Hintergrund: `schutz_w = geschützte Mindestleistung + reserve_w + global_puffer_w`
  (geklemmt) ist der effektive Schutz und NICHT die vom User eingetragene geschützte
  Mindestleistung. Der Energy-Pilot verglich in der Plan-Rückkopplung fälschlich gegen
  `schutz_w` und zeigte so z.B. 900 W statt der eingetragenen 600 W. Rein additiv –
  `schutz_w`/`schutz_a` bleiben unverändert erhalten (weiter für die Regelung genutzt).
- **Energy-Pilot-Tab in der Weboberfläche (Anzeige der EP-Daten).** Neuer Tab
  „Energy Pilot" spiegelt die vom Energy Pilot gelieferten Daten – EP schreibt
  seine KI-Vorschläge und Statuswerte als HA-`sensor.ep_*`-Entitäten, HEMS liest
  sie wie den Rest über die HA-REST-API (neuer Endpunkt `GET /api/ep`, filtert
  `sensor.ep_*`) und stellt sie dar: Plan-Status (Label, Gültigkeits-Countdown,
  Zeitfenster, Abweichungen aus `sensor.ep_plan_status`), EP↔HEMS-Verbindung
  (online/offline, letzter Zyklus, Modus aus `sensor.ep_hems_verbindung`) sowie
  die Vorschläge je Gerät (Freigabe/Priorität/geschützte Mindestleistung/Extras,
  aus `sensor.ep_<gerät>_*_vorschlag`). **Rein additiv/Anzeige** – kein direkter
  Add-on-zu-Add-on-Aufruf, keine Änderung am Regelzyklus.
  - **Verwaiste Vorschläge werden ausgeblendet.** HEMS spiegelt nur und löscht keine
    HA-Entitäten; tauscht man in EP einen Quellsensor, schreibt EP eine neue
    `entity_id`, während die alte mit eingefrorenem Wert in HA verbleibt. Der EP-Tab
    blendet solche Altwerte aus: (1) abgelaufene Vorschläge (`valid_until` in der
    Vergangenheit) werden nicht angezeigt, (2) bei doppeltem Feld je Gerät wird nur
    der frischere (späteres `valid_until`) behalten – ohne Kopplung an die
    Publish-Reihenfolge von `sensor.ep_plan_status`.
- **Steuermodus-abhängige Energy-Pilot-Übernahme (EP → HEMS, D-033).** Der
  Regelmodus entscheidet pro Gerät, ob die Regelung die Nutzer-Helfer (`ems_*`)
  oder die KI-Vorschläge (`sensor.ep_*_vorschlag`) verwendet. Neuer Wert
  `manuell` in `input_select.ems_regelmodus`. Semantik überall: **auto = KI,
  manuell = normale Regeln, aus = aus**.
  - `regelmodus = auto` → alle Geräte folgen dem EP-Vorschlag.
  - `regelmodus = manuell` / `nur_heizen` / `nur_laden` → normale Regeln; pro
    Gerät über `input_select.ems_<gerät>_modus` verfeinerbar (`auto` = EP für
    dieses Gerät und überspringt das Typ-Gate, `manuell` = normale Regeln,
    `aus` = Gerät aus – gilt auch als Kill-Switch bei `regelmodus = auto`).
  - Übernommen werden **Priorität** (`ep_<p>_prio_vorschlag` → `prioritat`),
    **Freigabe** (`ep_<p>_freigabe_vorschlag` → `freigabe`) und **geschützte
    Mindestleistung** (`ep_<p>_geschutzte_mindestleistung_w_vorschlag`, nur
    Watt-Geräte). Die technische Freigabe (`ems_<p>_technische_freigabe`) bleibt
    in jedem Modus hartes Gate; harte Grenzen (min/max, Lockout) gelten weiter.
  - **Fallback:** Fehlt/stört ein `sensor.ep_*_vorschlag`, greift der Nutzerwert
    (KI-Ausfall blockiert die Anlage nie). Gerätestatus (`/api/status`) enthält
    neu das Feld `source` (`aus`/`user`/`ep`).
  - **Migration:** Bestandskonfigurationen mit `allowed_modes: "auto"` werden auf
    `manuell` abgebildet. Anlagen, die zuvor `regelmodus = auto` als normale
    Regelung nutzten, müssen auf `manuell` wechseln.
- **Responsive Darstellung (Handy/Tablet).** Die Ingress-Oberfläche passt sich an kleine
  Bildschirme an – **kein horizontales Scrollen mehr, nur vertikal**: Gerät- und Steuerungs-
  Kacheln werden am Handy (≤480 px) einspaltig (kein `minmax`-Überlauf schmaler Raster), die
  Tab-Leiste bricht um statt seitlich zu scrollen, Werte/Namen brechen um, größere Touch-Ziele.
  Tablet-Breakpoint (≤900 px). **Rein visuell/additiv** – Karten, IDs und `app.js` unverändert.
- **`/api/status` liefert für Ampere-Geräte zusätzlich `schutz_a`.** Der effektive
  Mindestleistungs-Schutz (`schutz_w`, Watt) wird über Phasenanzahl × Spannung nach Ampere
  umgerechnet und im Gerätestatus mitgegeben – analog zum bestehenden `new_a`. Ohne dieses
  Feld konnten Ampere-Konsumenten (Energy Pilot) den Schutz nicht einheitengleich mit ihrem
  Ampere-Vorschlag (`geschutzte_mindestleistung_a_vorschlag`) vergleichen: Watt-Geräte hatten
  `schutz_w`, Ampere-Geräte (Wallbox) gar kein Pendant, sodass die Plan-Rückkopplung dort
  „unbekannt" statt eines Vergleichs zeigte.

### Behoben
- **Fremdgesteuerte Verbraucher blähen den Pool nicht mehr auf.** Der Pool wird als
  `residual_w + Summe(current_w)` gebildet – diese Rückrechnung ist nur zulässig, wenn HEMS
  die Leistung selbst angefordert hat und sie daher auch wieder freigeben kann. Wurde ein
  Gerät extern („Force-Modus" außerhalb HEMS) eingeschaltet, rechnete HEMS diese Fremdlast
  als eigenen, abschaltbaren Überschuss gut, verteilte sie an weitere Verbraucher und erzeugte
  Netzbezug. Jetzt gilt:
  - `BinaryDevice.current_w` liefert `power_w` nur, wenn der Schalter AN **und** die
    HEMS-Anforderung (`input_boolean.ems_<prefix>_anforderung_an`) aktiv ist. Der
    Anforderungszustand wird dazu neu aus HA gelesen und als `anforderung_an` im
    Gerätestatus (`/api/status`) ausgegeben; die Oberfläche zeigt bei Fremdsteuerung
    den Hinweis „⚠ extern AN – zählt nicht zum Pool".
  - `ControllableDevice.current_w` wird auf den HEMS-Sollwert gedeckelt
    (`min(actual_w, anforderung_current_w)`, 0 wenn nicht freigegeben). Damit zählt auch
    ein Teil-Fremdbezug (HEMS fordert 3 kW an, extern laufen 11 kW) nur mit 3 kW.
    `max_relief_w` nutzt dieselbe gedeckelte Größe, sonst überschätzte die
    Defizit-Notabschaltung die tatsächlich abregelbare Leistung.

  Die Fremdlast bleibt implizit über `residual_w` berücksichtigt (dort ist sie bereits
  abgezogen); HEMS regelt konservativ um sie herum. Der Normalbetrieb ist unverändert.

### Geändert
- **Lesbare deutsche Anzeigetexte (UI-Audit).** Verbliebene englische/technische Bezeichner
  in der Oberfläche durch deutsche ersetzt: Status-Tab-Zeile `Ziel (alloc)` → `Ziel (Zuteilung)`;
  Warn-Chip `⚠ LOCKOUT` → `⚠ SPERRE`;
  Regelmodus-Chip zeigt den Wert lesbar (`nur_heizen` → „Nur Heizen", `auto` → „Automatik" …)
  statt in snake_case; Steuerung-Tab-Label `Deadband` → `Totband (Deadband)` (im Kontrollschema,
  `/api/device_controls_schema`). Rein anzeigeseitig – Entitäts-IDs unverändert.
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
