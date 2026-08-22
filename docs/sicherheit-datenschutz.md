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

## Nutzerdefinierte Sensor-Formeln (D-045)

Der Bereich **Sensoren** im Ingress-Panel lässt den Nutzer eigenen Code hinterlegen, der
`ueberschuss` bzw. `hausbilanz` aus benannten HA-Entitäten berechnet
([konfiguration.md](konfiguration.md#formel-statt-einzel-entität),
[ADR](adr/D-045-formel-basierte-sensorwerte.md)). Das ist eine neue Angriffs- und Fehlerfläche, die
vor D-045 nirgends im Projekt existierte, und wird deshalb hier ausdrücklich dokumentiert statt
stillschweigend vorausgesetzt.

- **Kein `eval`/`exec` auf kompiliertem Python.** `app/formula.py` implementiert einen eigenen,
  baumwandelnden Auswerter über eine feste AST-Whitelist: nur Zuweisungen, Arithmetik, Vergleiche,
  boolesche Verknüpfungen und `if`/`else` sind erlaubt. Schleifen, Funktionsdefinitionen, `import`,
  `lambda`, Attributzugriffe (`.`), Indexzugriffe (`[…]`) und alle Container-Typen sind ausdrücklich
  verboten — nicht nur die Ausführung, schon das **Vorkommen** dieser Konstrukte im Quelltext wird
  vor jeder Ausführung abgelehnt.
- **Kein Netzwerk-, Datei- oder Prozesszugriff möglich**, strukturell — nicht weil er verboten
  wurde, sondern weil die Sprache keinen Import, keinen Attributzugriff und keinen Aufruf
  außerhalb der festen Funktions-Whitelist (`abs`, `min`, `max`, `round`) ausdrücken kann. Der
  `SUPERVISOR_TOKEN` und alle Umgebungsvariablen sind aus einer Formel heraus nicht erreichbar.
- **Kein Absturz, keine Blockade.** Der Regelzyklus läuft synchron in einem einzigen
  asyncio-Prozess (`app/main.py`); hängender Code würde dort auch die Notabschaltung blockieren.
  Ohne Schleifen ist die Ausführung strukturell auf die Anzahl der Ausdrucksbausteine im Quelltext
  beschränkt — kein Timeout, kein Thread- oder Prozesswechsel nötig. Jeder Fehler (Syntax, verbotenes
  Konstrukt, Laufzeitfehler, NaN/Unendlich) kommt als `valid: false` zurück statt eine Exception nach
  außen zu werfen; ein Regelzyklus bricht an einer kaputten Formel nie ab.
- **Zahlen bleiben durchgängig `float`.** Python-`int` hat beliebige Genauigkeit; wiederholtes
  Multiplizieren ganz ohne Schleife (`a = a * a`, wenige Dutzend Zuweisungen) ließe eine Ganzzahl auf
  eine Zahl mit Milliarden Stellen anwachsen. `float` ist IEEE 754 mit fester Breite und läuft bei
  Überlauf kontrolliert in `inf`.
- **Bezug zu „Grenzen für KI-Agenten" oben:** Die dortige Regel „Kein von einer KI erzeugter Code
  wird ungeprüft ausgeführt" bleibt unverändert gültig und betrifft einen anderen Fall — frei
  formulierten Code, den eine KI vorschlägt. Eine Formel hier ist **strukturell eingeschränkter
  Code, den der Nutzer selbst einträgt** und der vor jeder Ausführung gegen die Whitelist geprüft
  wird; das eine ersetzt das andere nicht.
- **Vertrauensgrenze bleibt dieselbe wie für jedes andere Konfigurationsfeld:** Wer den Ingress
  passiert, darf die Formel ändern — genau wie jede HA-Entity-Zuordnung. Es gibt keine zusätzliche
  Isolation gegenüber der übrigen Konfiguration, und keine wird gebraucht: die Sprache selbst kann
  nichts außerhalb der Berechnung eines einzelnen Sensorwerts bewirken.

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
