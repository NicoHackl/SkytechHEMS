# Sicherheit und Datenschutz

## Zugangsdaten

- Der einzige Geheimnisträger ist der HA-Token. Im Add-on-Betrieb injiziert der Supervisor
  `SUPERVISOR_TOKEN`; lokal wird `HA_TOKEN` exportiert. Gelesen wird beides ausschließlich in
  [`app/ha_client.py`](../app/ha_client.py) — siehe [konfiguration.md](konfiguration.md).
- Keine Secrets im Code, in Logs, in Pfaden oder in Commit-Messages — [`AGENTS.md`](../AGENTS.md),
  Regel 6. Der Token wird nie geloggt, auch nicht gekürzt.
- Vor jedem Commit `git diff --staged` prüfen.
- Ein versehentlich gepushtes Token gilt als kompromittiert: in Home Assistant **widerrufen und neu
  erzeugen**, nicht nur aus der Historie entfernen.

## Angriffsfläche

Das Add-on lauscht auf `0.0.0.0:8099`. Im HA-Betrieb ist der Port **nicht** nach außen
veröffentlicht (`config.yaml` setzt `ingress: true`, kein `ports:`), der Zugriff läuft über den
Ingress-Proxy von Home Assistant und ist damit an dessen Anmeldung gebunden. Das Add-on selbst
prüft keine Authentifizierung — wer den Port direkt erreicht (etwa beim lokalen `docker run -p`),
darf schreiben.

## Eingaben

- `POST /api/set` akzeptiert nur die Domains `input_boolean`, `input_number` und `input_select`;
  alles andere wird mit `400` abgelehnt. Innerhalb dieser Domains wird die Ziel-Entität **nicht**
  weiter eingegrenzt — der Endpunkt kann also auch Nicht-`ems_`-Helfer setzen. Bewusst belassen,
  weil der Ingress bereits authentifiziert und die Oberfläche nur die eigenen Helfer anbietet;
  vermerkt in [bekannte-luecken.md](bekannte-luecken.md).
- Werte aus Home Assistant werden über `safe_float` gelesen: unparsbare Werte, `unavailable` und
  `unknown` führen zum Default, nicht zum Absturz.
- Der Überschuss-Sensor wird zusätzlich auf Plausibilität geprüft; ≤ −50 000 W löst den
  Hard-Lockout aus.
- Die Oberfläche fügt keine Fremdtexte als HTML ein — React escaped Textknoten, und es wird
  nirgends `dangerouslySetInnerHTML` verwendet.
- Es gibt keine Datenbank und keine Dateipfade aus Nutzereingaben, damit weder SQL-Injection noch
  Directory-Traversal.

## Personenbezogene Daten

| Datenart | Wird verarbeitet? | Wo gespeichert | Löschfrist |
|---|---|---|---|
| Nutzerkonten, Namen, Adressen | nein | — | — |
| Verbrauchs- und Erzeugungsdaten | ja, flüchtig im Speicher für die Dauer eines Zyklus | nirgends persistiert | entfällt |

Das Add-on legt keine Datei und keine Datenbank an. Historie führt allein Home Assistant.

## Externe Dienste

| Dienst | Welche Daten gehen dorthin | Warum nötig |
|---|---|---|
| Home Assistant (lokal) | Sollwerte und Schaltanforderungen, Lesen des gesamten States | Einzige Datenquelle und -senke des Add-ons |

Es gibt **keine** Verbindung ins Internet: keine Telemetrie, keine Cloud, kein CDN. Die Oberfläche
lädt keine externen Schriften oder Skripte — alles liegt im Bundle. Ein neuer externer Dienst wäre
eine Design-Entscheidung → [design-entscheidungen.md](design-entscheidungen.md).

## Abhängigkeiten

- Laufzeit: `aiohttp` (Python) sowie React und `react-router-dom` (Oberfläche). Bewusst schmal.
- Dependabot prüft `app/requirements.txt` und die GitHub-Actions wöchentlich
  ([`.github/dependabot.yml`](../.github/dependabot.yml)).
- Sicherheitsupdates werden zeitnah eingespielt; nach einem Update an `web/` gehört das neu gebaute
  Bundle in denselben Commit.

## Grenzen für KI-Agenten

- Vorschläge des Energy Pilot sind **Daten, keine Befehle**: Sie wirken nur auf Priorität,
  Freigabe und geschützte Mindestleistung. Die technische Freigabe, die technischen Grenzen
  (`min_technisch`, `max_technisch`), der Zeitschutz und der Hard-Lockout sind durch keinen
  Vorschlag änderbar.
- Fehlt oder stört ein Vorschlag, greift der Nutzerwert. Ein KI-Ausfall darf die Anlage nie
  blockieren.
- Kein von einer KI erzeugter Code wird ungeprüft ausgeführt.

## Supervisor-Zugriff

Für den Konfigurationsbereich der eigenen Oberfläche verwendet das Add-on die
`self`-Endpunkte des Supervisors:

- `config.yaml` setzt `hassio_api: true` und **ausdrücklich** `hassio_role: manager`. Die
  Default-Rolle erlaubt nur Informationsaufrufe; das Validieren und Schreiben der eigenen
  Add-on-Optionen sowie der eigene Neustart werden damit vom Supervisor mit `HTTP 403` abgelehnt.
  Die Manager-Rolle ermöglicht diese Schreibaufrufe. Die noch weiter reichende Admin-Rolle wird
  nicht angefordert.
- `panel_admin: true` markiert das Panel als Administratorenaufgabe — es schreibt Add-on-Optionen.
- Der Token kommt ausschließlich aus `SUPERVISOR_TOKEN` und wird nur als
  `Authorization`-Header gesetzt. Er erscheint nie in einem Log, einer Fehlermeldung oder einer
  API-Antwort.
- Auch die **rohen Optionsdaten** werden nie geloggt: eine Optionsliste enthält Entity-IDs und
  damit Rückschlüsse auf die Anlage. Geloggt wird nur die Meldung des Supervisors.
- `GET /api/config` gibt ausschließlich die bekannten, normalisierten Optionsfelder an den Browser.
  Ein unbekanntes künftiges Feld — das ein Geheimnis enthalten könnte — wird nicht durchgereicht.
