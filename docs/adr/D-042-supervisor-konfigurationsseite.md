# D-042: Die Add-on-Optionen werden über die Supervisor-API verwaltet, nicht über eine eigene Datei

- **Datum:** 21.08.2026
- **Status:** Aktiv
- **Betrifft:** `app/supervisor_client.py`, `app/config_service.py`, `app/configuration.py`,
  `app/main.py`, `config.yaml`, `web/src/pages/Konfiguration*`,
  [api-referenz.md](../api-referenz.md), [konfiguration.md](../konfiguration.md)

## Kontext

Die Geräteliste war nur über die native Add-on-Seite von Home Assistant pflegbar. Weil das Schema
eine Objektliste enthält, zeigt der Supervisor sie als **YAML-Editor** an: ohne Feldbeschreibungen,
ohne Entitätssuche und ohne Rückmeldung, ob ein Eintrag überhaupt gültig ist. Ein Tippfehler in
einem Helfernamen fiel erst auf, wenn das Gerät im Betrieb nichts tat.

Gleichzeitig ist „keine eigene Persistenz" eine Kerneigenschaft des Projekts
([architektur.md](../architektur.md)). Eine bedienbare Konfigurationsseite darf sie nicht
aufweichen.

## Betrachtete Optionen

### Option A — eigene Konfigurationsdatei unter `/data/`

- Dafür: Einfach zu schreiben, keine zusätzliche Berechtigung nötig.
- Dagegen: Es gäbe **zwei** Quellen. Die native Add-on-Seite schriebe weiter `options.json`, die
  eigene Seite eine zweite Datei — und welche gilt, wäre eine Frage der Startreihenfolge. Genau
  diese Art von stiller Divergenz kostet später Tage.

### Option B — `/data/options.json` direkt beschreiben

- Dafür: Eine Quelle, kein neues API.
- Dagegen: Der Supervisor ist der Eigentümer dieser Datei. Er schreibt sie beim nächsten
  Optionswechsel neu und überschreibt dabei die Änderung. Außerdem entfiele die Schema-Prüfung des
  Supervisors.

### Option C — Supervisor-API `addons/self/options`

- Dafür: Dieselbe Quelle wie die native Seite, dieselbe Schema-Prüfung, kein neuer Zustand.
- Dagegen: Braucht `hassio_api: true`; Änderungen sind erst nach einem Neustart wirksam, und
  parallele Änderungen an beiden Stellen müssen erkannt werden.

## Entscheidung

Option C. `/data/options.json` wird nur noch **gelesen**. Geschrieben wird ausschließlich über
`http://supervisor/addons/self/…`.

Dazu gehören vier Festlegungen:

- **`hassio_role: default`.** Die `self`-Endpunkte sind laut Supervisor-Sicherheitsvertrag für das
  eigene Add-on freigegeben. Eine Manager- oder Admin-Rolle wäre deutlich mehr Zugriff, als die
  Aufgabe braucht.
- **Revisions-Hash über die ROHEN Optionen.** Nicht über die normalisierten: nur so fällt auch eine
  Änderung an einem Feld auf, das diese Oberfläche gar nicht anzeigt. Weicht die Revision beim
  Speichern ab, antwortet der Server mit `409`, statt die fremde Änderung zu überschreiben.
- **Bekannte Felder werden in die frisch gelesenen Optionen gemischt.** Ein vollständiges
  Überschreiben löschte ein unbekanntes künftiges Top-Level-Feld stillschweigend.
- **Speichern und Neustarten bleiben getrennt.** Eine gespeicherte Konfiguration wirkt erst nach
  einem Neustart; die laufende Regelung wird nicht heimlich im Prozess umgebaut. Vor einem
  Neustart werden geänderte oder gelöschte Altgeräte über ihre **alten** Schreibziele sicher
  deaktiviert — aus dem bearbeiteten Entwurf abgeleitet beschriebe man die neuen Entitäten und
  ließe die alten weiterlaufen. Scheitert die Deaktivierung, unterbleibt der Neustart. Das ist
  absichtlich strenger als der normale Regelzyklus: dort ist ein fehlgeschlagener Schreibvorgang
  ein Gerät weniger, hier bliebe ein Gerät unbeaufsichtigt auf seinem letzten Sollwert stehen.

Die Fachlogik liegt in `config_service.py` ohne HTTP-Kenntnis, die aiohttp-Handler übersetzen nur
noch Ausnahmen in Statuscodes. Ohne diese Trennung wäre der Ablauf nur gegen einen laufenden
Webserver testbar, und `main.py` wüchse weiter zu.

## Folgen

- **Positiv:** Eine Optionsquelle, dieselbe Schema-Prüfung wie die native Seite, keine neue
  Persistenz. Feldfehler mit Pfaden und deutschen Meldungen erscheinen dort, wo sie entstehen.
- **Negativ:** Das Add-on braucht `hassio_api`. Außerhalb von Home Assistant ist die Konfiguration
  schreibgeschützt — die Oberfläche sagt das ausdrücklich, statt einen Erfolg vorzutäuschen.
- **Aufwand:** `config.yaml` erhält `hassio_api`, `hassio_role` und `panel_admin`.

## Rücknahmebedingung

Wenn der Supervisor die `self`-Endpunkte für Add-ons ohne Manager-Rolle schließt oder das
Antwortformat unangekündigt bricht. Erkennbar an einem `403` auf `POST /addons/self/options`, das
nicht auf eine Fehlkonfiguration zurückgeht. Dann bleibt nur die native Add-on-Seite, und die
eigene Konfigurationsseite fällt dauerhaft in den Nur-Lese-Modus, den sie heute schon kennt.
