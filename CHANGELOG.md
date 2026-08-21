# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jedem Merge nach `main` automatisch
um eine Patch-Stelle erhöht (siehe `.github/workflows/bump-version.yaml`).

## [Unreleased]

### Hinzugefügt
- **Doppelte Fallback-Auflösung mit Ursache und Quelle.** `StateProxy` kann jetzt zwischen
  `missing` (Entity-ID im HA-Schnappschuss nicht vorhanden), `unavailable` (Entität da, State
  `unknown`/`unavailable`/`null`), `invalid` (State da, aber falscher Typ, nicht endlich oder
  außerhalb eines zwingenden Bereichs) und `valid` unterscheiden. Jeder aufgelöste Wert meldet
  zusätzlich seine Quelle: `ha`, `addon` oder `internal`. Die neuen Methoden `has()`,
  `availability()`, `resolve_number()`, `resolve_bool()` und `resolve_select()` sind ab sofort der
  einzige Weg, einen HA-State in einen Regelwert zu verwandeln.
  - **Ein gültiger Wert `0` wird nie mehr verworfen.** Wahrheitswert-Ausdrücke wie
    `wert or fallback` konnten eine ausdrücklich eingetragene Null nicht von „kein Wert"
    unterscheiden. Zahlen laufen zusätzlich durch `math.isfinite`, damit `NaN` und `±inf` nicht als
    Regelgröße in die Anlage gelangen.
  - **Fehlend und ausgefallen sind trennbar.** `resolve_bool()` kennt dafür einen eigenen
    `missing_fallback` — eine gar nicht angelegte Freigabe darf anders behandelt werden als eine
    ausgefallene.
- **Zentrales Konfigurationsmodell `app/configuration.py`.** Normalisierung, Validierung mit
  Feldpfaden (`devices[2].technical_maximum`) und deutschen Meldungen, stabiler Parser und
  Serializer für Modus-Listen, Eindeutigkeitsprüfung von Gerätename und Präfix, kanonischer
  Revisions-Hash über die rohen Optionen und der Diff, der vor einem Neustart sagt, welche alten
  Geräte sicher zu deaktivieren sind. Die gemischte Objektliste im Supervisor-Schema kann keine
  bedingten Pflichtfelder je Geräteklasse ausdrücken — die Anwendung ist deshalb die autoritative
  Validierung, und Oberfläche wie Controller bekommen dieselbe Antwort auf „ist dieser Eintrag
  gültig".
- **Verpflichtende Add-on-Fallbacks für `controllable` und `binary`.** Ein regelbares Gerät bringt
  jetzt `technical_minimum`, `technical_maximum`, `increase_delay_s`, `decrease_delay_s`,
  `maximum_step_change` und `minimum_step_change` mit, ein binäres `power_w`, `on_reserve_w`,
  `min_runtime_s`, `min_offtime_s` und `off_delay_s`. Die gleichnamigen HA-Helfer bleiben optional
  und haben bei einem gültigen State weiterhin Vorrang; fehlt der Helfer, fällt oder ist er
  unbrauchbar, greift der konfigurierte Wert. Bisher lief ein Gerät ohne seine Helfer still mit
  Nullwerten weiter — ein binäres Gerät mit `leistung_w = 0` machte die Pool-Rechnung fachlich
  unbrauchbar, ohne dass irgendwo etwas zu sehen war.
  - Die Werte eines Ampere-Geräts liegen in **Ampere**, nicht in Watt; die Umrechnung über
    Phasenzahl × Spannung erfolgt erst danach.
  - `phase_switch_delay_s` behält seine eigene Kette HA → Add-on → intern, verwirft aber keine
    gültige `0` mehr: sie bedeutet jetzt „keine Sperrzeit" statt „nimm den Default".
- **Globale Option `available_modes`.** Sie legt fest, welche der drei normalen Regelmodi
  (`manuell`, `nur_heizen`, `nur_laden`) in dieser Anlage überhaupt verwendet werden; Default sind
  alle drei, Bestandsanlagen verhalten sich also unverändert. `devices[].allowed_modes` muss eine
  Teilmenge davon sein. Meldet `input_select.ems_regelmodus` einen normalen, nicht aktivierten
  Modus, bleibt der Zyklus sicher inaktiv; der rohe HA-State bleibt als `global_mode` sichtbar und
  `global_mode_configured: false` nennt die Ursache. Die Optionen des HA-Helfers legt oder ändert
  das Add-on weiterhin nicht.
- **Ein leeres `allowed_modes` ist ein unterstütztes Gerät.** Es bedeutet **Nur Energy Pilot**:
  normale Nutzerregeln aktivieren das Gerät nie, der Energy Pilot erreicht es weiterhin. Fehlt das
  Feld ganz, gilt wie bisher `manuell`.
- **`inactive_devices` im Status.** Geräteeinträge mit fehlenden oder unbrauchbaren Pflichtfeldern
  werden beim Start nicht instanziiert, verschwinden aber nicht mehr in einer Log-Zeile: sie stehen
  mit Geräte-ID, Klasse, Label und konkreten Feldfehlern in `/api/status`. Für sie werden
  ausdrücklich **keine** Ist-, SoC- oder Schaltwerte erfunden, und sie beeinflussen den Pool nicht.
- **`entity_diagnostics` je Gerät.** `{entity_id: {role, state, source}}` beantwortet je gelesener
  Entität, welcher Wert gerade wirkt und warum nicht der aus Home Assistant.

- **Geräteklassen-Referenz unter `docs/device_classes/`.** Je eine Seite für `controllable`,
  `binary`, `battery` und globale Werte dokumentiert den tatsächlichen HA-Lese-/Schreibvertrag,
  Pflichtfelder der Add-on-Konfiguration, externe Entitätszuordnungen, Defaults und echte
  Add-on-Fallbacks. Die Prüfung hat außerdem B-4 sichtbar gemacht: Die reservierte
  Netzlade-Schnittstelle ist entgegen der bisherigen Dokumentation nicht hart gesperrt und muss
  bis zur vollständigen Implementierung deaktiviert bleiben.
- **AC-gekoppelte Speicher als eigene Geräteklasse (D-040, 1.1.0 → 1.2.0).** Mit
  `class: battery` verwaltet das HEMS jetzt auch Batteriespeicher: geladen wird aus
  PV-Überschuss und in derselben Prioritätsreihenfolge wie jeder andere Verbraucher, entladen
  wird zur Deckung des **normalen Hausverbrauchs** — ausdrücklich nicht für Heizstab, Wallbox
  oder Heizlüfter. Der Heizstab läuft damit nie aus der Batterie.
  - **Der Pool wird bereinigt, bevor er verteilt wird.** Ein Speicher ist der erste Teilnehmer,
    der den Messwert verfälscht, auf dem das HEMS aufbaut: seine Entladung erhöht den
    Überschuss-Sensor, ist aber kein Überschuss. `residual_bereinigt_w` zieht die gemessene
    Entladung ab; erst darauf laufen Pool und Defizit. Ohne das läse das HEMS die eigene
    Entladung als Überschuss, schaltete Verbraucher zu — und der Speicher wäre in einem Zyklus
    leer.
  - **Die weggeworfene Hälfte des Pools ist der Entladebedarf.** Bisher klemmte
    `max(residual + Σ current_w, 0)` alles Negative weg. Diese Hälfte heißt jetzt
    `hausdefizit_w` und ist das Entladeziel. Die Überschussverbraucher sind per Konstruktion
    draußen, weil ihre Leistung zurückaddiert wird — es braucht dafür keine Sonderregel.
  - **Zwei Summen statt einer.** `current_w` filtert den Force-Modus heraus, `gemessene_last_w`
    filtert nichts. Ein von Hand eingeschalteter Heizstab bleibt damit Überschussverbraucher und
    wird vom Speicher nicht gedeckt. Weil je Gerät `gemessene_last_w ≥ current_w` gilt,
    schließen Pool und Hausdefizit einander **strukturell** aus: „nie gleichzeitig laden und
    entladen" ist eine Eigenschaft der Formeln, keine nachträgliche Prüfung.
  - **Getrennte Lade- und Entladepriorität.** `prioritat` gilt fürs Laden,
    `entlade_prioritat` fürs Entladen. „Lade mich zuletzt, entlade mich zuerst" ist damit
    konfigurierbar — mit einer Zahl wäre es nicht ausdrückbar.
  - **Ausgabe: ein signierter Sollwert plus Betriebsart.**
    `input_number.ems_<prefix>_anforderung_leistung_w` trägt „+ laden / − entladen",
    `input_select.ems_<prefix>_anforderung_betriebsart` die Betriebsart. Die Übersetzung nach
    Modbus oder MQTT macht eine HA-Automation, nicht das Add-on. **Der Zahlen-Helfer braucht ein
    negatives Minimum**, sonst klemmt Home Assistant jede Entladeanforderung auf 0.
  - **SoC-Grenzen mit Drosselband und Hysterese**, Geräte-Derating über optionale
    `available_*_power_entity` mit Vorrang, Totzone um Null, Sperrzeit nach Richtungswechsel und
    eine asymmetrische Entladerampe: ein echter Lastabwurf wird sofort zurückgenommen, eine
    kleine Abweichung gedämpft — sonst wird aus Sensor-Versatz ein Grenzzyklus.
  - **Der sichere Zustand wird aktiv geschrieben.** Bei Lockout, fehlender Freigabe oder
    unbrauchbaren Messwerten schreibt das HEMS `0 W` und `standby`, statt den letzten Sollwert
    stehen zu lassen. Ein Speicher ohne gültigen Leistungsmesswert fällt aus der Regelung, die
    übrigen laufen weiter.
  - **Neue Statuskacheln und eine Speicherkarte** in der Oberfläche: Speicher netto,
    kapazitätsgewichteter SoC-Schnitt und Hausdefizit, dazu ein Ladezustandsbalken mit Markern
    für Minimum, Notstromreserve und Ladeschluss. Läuft ein HEMS-Gerät fremdgesteuert, benennt
    die Hausdefizit-Kachel den ausgenommenen Betrag — sonst sähe das im Energiedashboard wie ein
    Regelfehler aus.
  - **Ohne konfigurierten Speicher bleibt das Verhalten unverändert.** `netz_support_w` ist
    dann 0, die Bereinigung eine Identitätsoperation und die Entladeplanung läuft über eine
    leere Liste. Abgesichert durch `test_pool_ohne_speicher_unveraendert` und die Property P7.
  - Neue Add-on-Option `speicher_in_residual_enthalten` (Default `an`) und acht optionale
    Gerätefelder. Bestehende Konfigurationen bleiben gültig.
- **Versionierter Gerätevertrag für den Energy Pilot (D-039, 1.0.25 → 1.1.0).**
  `/api/device_controls_schema` bleibt in seiner bisherigen Listen-/Gruppenform kompatibel und
  ergänzt Geräteklasse, Entitätspräfix, Einheit, erlaubte Modi, Überschuss-Regelprinzip,
  Istleistungs- beziehungsweise Schaltentität und HEMS-Anforderung. Jedes `ems_*`-Item trägt nun
  einen stabilen Schlüssel, Datentyp, Einheit, semantische Rolle und die Angabe, ob es für die
  Planung relevant ist. Damit muss Energy Pilot keine Entity-Suffixe mehr erraten und kann
  Regelparameter aus dem KI-Kontext heraushalten.
- **Atomare, ablaufende EP-Vorschläge.** HEMS akzeptiert einen `sensor.ep_*_vorschlag` nur noch,
  wenn `sensor.ep_plan_commit` dieselbe `plan_id` und ein aktuelles Zeitfenster bestätigt.
  Fehlende, fehlerhafte, teilweise geschriebene oder abgelaufene Vorschläge fallen feldweise
  auf den Nutzerwert zurück. `/api/status` zeigt je Gerät den Diagnosewert
  `ep_proposal_status`; die bestehende Moduslogik bleibt unverändert.

### Geändert
- **Gerätename und effektives Entitätspräfix müssen eindeutig sein.** Zwei Geräte mit demselben
  Präfix schrieben bisher unbemerkt auf dieselben HA-Helfer.
- **`/api/status` liefert die Zwischengrößen der Pool-Rechnung mit.** Neu sind
  `residual_bereinigt_w`, `netz_support_w`, `hems_last_w`, `hems_last_gemessen_w`, `pool_roh_w`,
  `entlade_basis_w` und `hausdefizit_w`. Rein additiv — bestehende Felder ändern weder Namen noch
  Bedeutung. Für Planer wichtig: Regelentscheidungen beziehen sich jetzt auf
  `residual_bereinigt_w`, nicht mehr auf `residual_w`.
- **`current_deficit_w` rechnet gegen den bereinigten Überschuss.** Ohne diese Änderung
  verschwände das Defizit, sobald ein Speicher die Hauslast deckt — und die Verbraucher liefen
  faktisch aus der Batterie. Ohne Speicher ist der Wert unverändert.
- **Neue Weboberfläche (React + TypeScript + Vite).** Die Bedienung ist dieselbe
  geblieben, nur besser: Aus den drei Tabs sind drei Seiten mit eigener Adresse
  geworden (Status, Steuerung, Energy Pilot), die Navigation sitzt links und
  fährt auf schmalen Bildschirmen als Menü aus. **Neu ist ein sichtbarer
  Schalter zwischen Hell- und Dunkel-Modus**; die Wahl bleibt über das Neuladen
  hinweg erhalten, voreingestellt ist die Systemvorgabe. Es gibt keine
  Funktionseinbuße: Live-Zähler für Mindestlauf-/Mindestauszeit,
  Abschaltverzögerung und Phasenwechsel-Sperre laufen weiterhin sekündlich
  herunter, Zahlenfelder speichern wie bisher verzögert (700 ms) und beim
  Verlassen des Felds, die Vorschläge des Energy Pilot werden weiterhin um
  verwaiste Altwerte bereinigt. Neu ist außerdem, dass ein fehlgeschlagenes
  Speichern als Meldung erscheint statt nur als Zeichen in der Zeile.
- **Rückmeldung zum letzten Zyklus in deutschem Zeitformat.**
  `/api/status.last_cycle_at` liefert jetzt `TT.MM.JJJJ hh:mm:ss` in Berliner
  Zeit. Das bisherige Maschinenformat bleibt zusätzlich erhalten und steht neu
  in `last_cycle_at_iso` — bestehende Auswertungen lesen unverändert weiter.
- **Beschreibung des Log-Levels korrigiert.** Der Helfer
  `input_boolean.ems_pyems_debug_output` schaltet das zusätzliche
  Regelentscheidungs-Logging, nicht den Log-Level. Die Add-on-Optionen sagten
  bisher etwas anderes.

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
