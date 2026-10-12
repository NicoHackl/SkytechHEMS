# Vertrag: SkytechHEMS ↔ Skytech Data Insight

**Version:** 0.1

**Status:** Entwurf — in keinem der beiden Projekte implementiert

**Stand:** 12.10.2026

**Grundlage:** SkytechHEMS D-065 (`docs/adr/D-065-preis-und-prognosemodul.md`, Preis- und
Prognosemodul für den dynamischen Strompreis) und Skytech Data Insight D-027
(`docs/adr/D-027-hems-anbindung.md`, HEMS-Anbindung über eine eigene Datenbankrolle), jeweils im
eigenen Repository.

### Statuskennzeichnung

| Kennzeichen | Bedeutung |
|---|---|
| **Entwurf** | Vereinbart, aber noch nicht implementiert. Ein Plan oder eine Doku-Änderung implementiert keine Schnittstelle. |
| **Implementiert** | In der genannten Gegenstelle umgesetzt und getestet. |
| **Bekannte Grenze** | Bewusst nicht gelöst; wird nicht als Zusage gelesen. |

Alle Abschnitte dieser Version sind **Entwurf**. Die Umsetzung erfolgt in Skytech Data Insight
(Schema, Rolle, Sperre, Oberfläche) und danach in SkytechHEMS (Client, Prognosen). Mit jeder
Umsetzung wird der Status je Abschnitt hier nachgetragen.

Die Datei liegt wortgleich in beiden Repositories unter
`contract/contract_hems_data_insight/contract_hems_data_insight.md`. Bei einer Änderung müssen
beide Kopien im selben Arbeitspaket angepasst werden.

## Zweck und Architekturgrenze

SkytechHEMS wertet für den dynamischen Strompreis Preis, PV-Prognose und Verbrauch aus und
rechnet daraus Prognosen und Kennzahlen. Skytech Data Insight speichert sie, zeichnet die dafür
nötigen Home-Assistant-Sensoren auf und stellt alles in Grafana, per SQL und per MCP bereit.

- **Data Insight rechnet keine Prognosen** und trifft keine Entscheidung für das HEMS.
- **Das HEMS regelt nie über Data Insight.** Der Regelzyklus des HEMS liest und schreibt die
  Datenbank nicht; nur das Preis- und Prognosemodul des HEMS (eigener Takt) tut das.
- **Data Insight ist optional.** Ist es nicht installiert oder nicht erreichbar, läuft das HEMS
  unverändert weiter. Es fehlen dann die Verbrauchsprognose und die Speicherung.

```text
SkytechHEMS ── Sensoren anlegen/übernehmen, Zuordnungen ──► Data Insight
SkytechHEMS ── eigene Messreihen (hems.*), Prognoseläufe ─► Data Insight
SkytechHEMS ◄── Verlauf der zugeordneten Sensoren (15 min) ─ Data Insight
Home Assistant ── Zustände der angelegten Sensoren ───────► Data Insight (Collector)
```

## Bezeichner

| Bezeichner | Bedeutung |
|---|---|
| `<geraet>` | Technische Geräte-ID des HEMS (`devices[].name`), nicht das Präfix und nicht der Anzeigename |
| Rolle | Fester fachlicher Name, unter dem das HEMS einen Sensor anspricht, z. B. `hausverbrauch` |
| Lauf | Eine vollständige Prognose- oder Auswertungsrechnung des HEMS zu einem Zeitpunkt |
| Slot | Zeitabschnitt von 15 oder 60 min, bezeichnet durch seinen Beginn |
| Zeiten | `timestamptz`, gespeichert in UTC; für Menschen in Berliner Zeit dargestellt |
| Einheiten | `W`, `kWh`, `€/kWh`, `%`; Werte werden nie still umgerechnet |

## Verbindung und Anmeldung

**Status: Entwurf**

| Punkt | Festlegung |
|---|---|
| Datenbank | `skytech` |
| Netz | Internes Add-on-Netz von Home Assistant, Port `5432` des Data-Insight-Containers. Der Weg funktioniert auch, wenn der LAN-Port 5432 abgeschaltet ist (Data Insight D-009) |
| Host im HEMS | Option `insight_host`, Voreinstellung `auto`. Bei `auto` ermittelt das HEMS über den Supervisor (`GET /addons`) das installierte Add-on mit dem Slug `*_skytech_data_insight` und bildet daraus den Hostnamen (`_` wird `-`). Ein fester Hostname ist ebenso zulässig |
| Port im HEMS | Option `insight_port`, Voreinstellung `5432` |
| Rolle | `skytech_hems`, Anmeldung mit Passwort (`scram-sha-256`) |
| Secret | Data Insight erzeugt es auf der Seite „Zugänge“ (Schlüssel `hems`) und speichert es in der Option `hems_password`. Im HEMS wird es als Option `insight_password` eingetragen. Ohne gesetztes Passwort ist die Anmeldung gesperrt |
| Zugelassene Adressen | Nur das interne Add-on-Netz (Supervisor-Standard `172.30.32.0/23`; vor der Umsetzung am System zu bestätigen) |
| Geheimhaltung | Das Secret erscheint auf keiner Seite in Log, Status oder API |

**Bekannte Grenze:** Die Verbindung im internen Add-on-Netz ist nicht mit TLS verschlüsselt.

## Vertragsversion

**Status: Entwurf**

Data Insight stellt die Sicht `skytech.v_hems_vertrag` mit genau einer Zeile und der Spalte
`version` (`text`) bereit; für diese Vertragsversion `0.1`. Das HEMS prüft sie bei jedem
Verbindungsaufbau. Weicht sie von der Version ab, die das HEMS kennt, liest und schreibt es nichts
und meldet die Abweichung in seinem Status.

## Rechte der Rolle `skytech_hems`

**Status: Entwurf**

Die Liste ist abschließend.

| Objekt | Recht | Einschränkung |
|---|---|---|
| `skytech.sensor` | `SELECT` | — |
| `skytech.sensor` | `INSERT` | nur Zeilen mit `verwaltet_von = 'hems'` |
| `skytech.sensor` | `UPDATE` | nur die Spalten `aktiv`, `name`, `einheit` an Zeilen mit `verwaltet_von = 'hems'`; dazu einmalig `verwaltet_von` von `NULL` auf `'hems'` (Übernahme) |
| `skytech.kategorie`, `skytech.groesse` | `SELECT` | — |
| `skytech.v_messwert_15min`, `skytech.v_messwert_1h` | `SELECT` | — |
| `skytech.messwert` | `INSERT` | nur für Sensoren mit `quelle = 'hems'` (Row-Level-Security) |
| `skytech.hems_zuordnung` | `SELECT`, `INSERT` | — |
| `skytech.v_hems_zuordnung`, `skytech.v_hems_rolle_15min` | `SELECT` | — |
| `skytech.prognose_lauf`, `skytech.prognose_wert` | `SELECT`, `INSERT` | — |
| Prognose-Sichten, `skytech.v_hems_vertrag` | `SELECT` | — |

Kein `DELETE`, keine Schemaänderung, kein Zugriff auf `skytech_config`.

## Verwaltete Sensoren

**Status: Entwurf**

`skytech.sensor` erhält die Spalte `verwaltet_von` (`text`, `NULL` oder `'hems'`).

**HEMS-Seite:**

- Das HEMS legt jeden Sensor, den es für eine Rolle braucht, selbst an (`verwaltet_von = 'hems'`).
- Gibt es die Entität (gleiche `entity_id` und gleiches `attribut`) bereits, **übernimmt** das HEMS
  die Zeile: Es setzt `verwaltet_von = 'hems'`, die vorhandenen Messwerte bleiben erhalten.
- Es setzt `name`, `kategorie` und `groesse` aus den Katalogen, `einheit`, `quelle` und `aktiv`.
  Andere Spalten setzt es nicht.
- Braucht das HEMS einen Sensor nicht mehr, setzt es ihn auf `aktiv = false`. Er bleibt verwaltet,
  seine Messwerte bleiben erhalten.
- Nicht verwaltete Sensoren ändert das HEMS nie, außer durch die Übernahme oben.

**Data-Insight-Seite:**

- Ein Trigger auf `skytech.sensor` lehnt `UPDATE` und `DELETE` an Zeilen mit
  `verwaltet_von IS NOT NULL` für jede andere Rolle als `skytech_hems` ab. Damit gilt die Sperre
  für Oberfläche, MCP und direktes SQL gleichermaßen.
- Oberfläche: eigener Abschnitt „Über Vertrag verwaltet — Skytech HEMS“, Kennzeichnung je Sensor,
  Bearbeiten und Löschen gesperrt, Hinweis auf den HEMS-Tab „Dynamischer Strompreis“.
- API: `PUT` und `DELETE api/sensors/{id}` antworten bei verwalteten Sensoren mit `409` und dem
  Grund; `GET api/sensors` liefert `verwaltet_von` und die aktuelle Rolle.
- MCP: Änderungen an verwalteten Sensoren werden mit derselben Begründung abgelehnt.
- Änderungsprotokoll: Anlegen, Übernehmen, Stilllegen und Zuordnungswechsel durch das HEMS
  erscheinen mit `quelle = 'hems'`.
- Der Collector zeichnet verwaltete Sensoren mit `quelle = 'ha'` wie jeden anderen HA-Sensor auf.

## Rollen und Austausch

**Status: Entwurf**

Das HEMS spricht Sensoren nur über Rollen an. So kann es die Entität hinter einer Rolle tauschen
(neues Home Assistant, umbenannte Entität, anderer Sensor im HEMS-Tab), ohne dass die Historie
abreißt.

```sql
CREATE TABLE skytech.hems_zuordnung (
  rolle      text        NOT NULL CHECK (rolle ~ '^[a-z_]+(:[a-z0-9_]+)?$'),
  sensor_id  integer     NOT NULL REFERENCES skytech.sensor(id),
  gueltig_ab timestamptz NOT NULL,
  PRIMARY KEY (rolle, gueltig_ab)
);
```

- Die Tabelle wird nur ergänzt, nie geändert. Eine Zuordnung gilt bis zum nächsten Eintrag
  derselben Rolle.
- Sicht `skytech.v_hems_zuordnung`: `rolle`, `sensor_id`, `entity_id`, `gueltig_ab`, `gueltig_bis`
  (`NULL` = aktuell).
- Sicht `skytech.v_hems_rolle_15min`: Spalten wie `v_messwert_15min`, aber je `rolle` statt je
  Sensor, über Sensorwechsel hinweg zusammengesetzt.
- Tausch: neuen Sensor anlegen oder übernehmen → Zuordnung mit `gueltig_ab = jetzt` einfügen →
  alten Sensor auf `aktiv = false`. Das HEMS gleicht beim Start und nach jeder
  Konfigurationsänderung ab.

**Rollenkatalog 0.1:**

| Rolle | Quelle | Kategorie / Größe | Bedeutung |
|---|---|---|---|
| `hausverbrauch` | `ha` | verbraucher / leistung | Hausverbrauch-Sensor des HEMS-Tabs |
| `pv_ist` | `ha` | pv / leistung | gemessene PV-Leistung |
| `preis` | `ha` | netz / preis | aktueller Endpreis des Preissensors |
| `pv_prognose_heute`, `pv_prognose_morgen`, `pv_prognose_rest_heute` | `ha` | pv / energie | Tageswerte der PV-Prognose |
| `speicher_soc:<geraet>` | `ha` | speicher / ladezustand | SoC je HEMS-Speicher |
| `speicher_leistung:<geraet>` | `ha` | speicher / leistung | Istleistung je HEMS-Speicher |
| `verbraucher_ist:<geraet>` | `ha` | verbraucher / leistung | Istleistung je regelbarem HEMS-Verbraucher |
| `verbraucher_schaltzustand:<geraet>` | `ha` | verbraucher / zustand | Schaltzustand je binärem HEMS-Verbraucher |
| `schalter_netzladen_freigabe`, `schalter_netzladen_manuell` | `ha` | sonstiges / zustand | globale Schalter |
| `schalter_netzladen_erlaubt:<geraet>` | `ha` | sonstiges / zustand | Schalter je Speicher |
| `grundlast` | `hems` | verbraucher / leistung | `hems.grundlast_w` |
| `nutzbar` | `hems` | speicher / energie | `hems.nutzbar_kwh` |
| `reichweite` | `hems` | speicher / sonstiges | `hems.reichweite_h` |
| `netzladen_zulaessig`, `netzladen_zulaessig:<geraet>` | `hems` | sonstiges / zustand | `hems.netzladen_zulaessig`, `hems.netzladen_zulaessig_<geraet>` |

Neue Rollen kommen mit einer neuen Vertragsversion dazu.

## HEMS-eigene Messreihen

**Status: Entwurf**

- Sensoren mit `quelle = 'hems'` und `entity_id = 'hems.<name>'`, angelegt und verwaltet vom HEMS.
- Das HEMS schreibt je 15-min-Slot genau einen Rohwert in `skytech.messwert`, mit
  `zeit` = Slot-Beginn und dem Mittelwert des Slots. Zustände (`netzladen_zulaessig`) als `1`/`0`.
- Data Insight holt für `quelle = 'hems'` nichts aus Home Assistant und berechnet Minutenwerte und
  Verdichtungen wie für jeden anderen Sensor.
- Nach einem Ausfall füllt das HEMS Lücken von `hems.grundlast_w` aus den aufgezeichneten
  Einzelsensoren nach; die übrigen `hems.*`-Reihen bleiben lückenhaft.

## Prognose- und Auswertungsläufe

**Status: Entwurf**

```sql
CREATE TABLE skytech.prognose_lauf (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  art         text        NOT NULL CHECK (art IN ('preis','pv','verbrauch','auswertung')),
  quelle      text        NOT NULL,
  erstellt    timestamptz NOT NULL,
  raster_min  smallint    NOT NULL CHECK (raster_min IN (15,60)),
  gueltig_ab  timestamptz NOT NULL,
  gueltig_bis timestamptz NOT NULL,
  einheit     text        NOT NULL,
  methode     text,
  details     jsonb       NOT NULL DEFAULT '{}'
);

CREATE TABLE skytech.prognose_wert (       -- Hypertable auf zeit
  lauf_id bigint           NOT NULL REFERENCES skytech.prognose_lauf(id),
  zeit    timestamptz      NOT NULL,       -- Slot-Beginn
  wert    double precision NOT NULL,
  p10     double precision,
  p90     double precision,
  PRIMARY KEY (lauf_id, zeit)
);
```

| `art` | `quelle` | Werte | Pflichtschlüssel in `details` |
|---|---|---|---|
| `preis` | Entity-ID des Preissensors | Endpreis in €/kWh je Slot | `entity` |
| `pv` | Entity-ID der Prognosekurve | mittlere Leistung in W je Slot, mit `p10`/`p90` | `entity`, `ist_rolle`, `heute_kwh`, `morgen_kwh`, `rest_heute_kwh` |
| `verbrauch` | `hems:<methode>` | mittlere Leistung in W je Slot, mit `p10`/`p90` | `ist_rolle`, `historie_tage`, `parameter` |
| `auswertung` | `hems:kennzahlen` | keine Wertezeilen | Kennzahlen (Reichweite, PV im Reichweitenfenster, Preisfenster …) |

- Ein Lauf wird in **einer** Transaktion geschrieben und danach nie geändert oder gelöscht (außer
  durch die Aufbewahrung).
- Ein Preislauf entsteht nur, wenn sich die Preiskurve geändert hat.
- Sichten in Data Insight: `v_prognose_aktuell` (jüngster Lauf je Art und Slot), `v_prognose_vortag`
  (jüngster Lauf, der mindestens 24 h vor dem Slot erstellt wurde), `v_preis`, `v_prognose_vs_ist`
  (Prognose neben dem Ist der `ist_rolle` aus `v_hems_rolle_15min`), `v_prognose_guete_tag`
  (je Berliner Tag und Art: mittlerer absoluter Fehler, Energiefehler, Anteil im p10–p90-Band).

## Aufbewahrung

**Status: Entwurf**

Neuer Schlüssel `aufbewahrung_prognose_tage` in `skytech_config.einstellung`, Voreinstellung `365`.
Er gilt für `pv`, `verbrauch` und `auswertung`; Preisläufe bleiben ohne Ablauf. `hems.*`-Messreihen
folgen der normalen Aufbewahrung von Data Insight.

## Fehlerverhalten

**Status: Entwurf**

- Data Insight nicht erreichbar, Anmeldung abgelehnt oder Vertragsversion abweichend: Das HEMS
  meldet das in seinem Status und versucht es im nächsten Takt erneut. Läufe werden nicht
  gepuffert, sie entstehen beim nächsten Takt neu.
- Ein Fehler im Datenaustausch beeinflusst den Regelzyklus des HEMS nie.
- Lehnt Data Insight eine Zeile ab (Rechte, Prüfregel), verwirft das HEMS den betroffenen Lauf
  vollständig und meldet den Grund.

## Zuständigkeiten und Nicht-Ziele

| Thema | Zuständig |
|---|---|
| Prognosen, Kennzahlen, Rollenwahl, Austausch von Sensoren | SkytechHEMS |
| Schema, Rechte, Sperre verwalteter Sensoren, Aufzeichnung der HA-Sensoren, Sichten, Aufbewahrung | Skytech Data Insight |
| Grafana-Dashboards | nicht Vertragsteil; sie lesen die Sichten oben |

Nicht Teil dieses Vertrags: Steuerentscheidungen (Netzladen, Entladesperre), der Energy Pilot und
jede Schreibverbindung von Data Insight zum HEMS.

## Kompatibilität und Änderungen

- Jede Änderung wird in beiden Kopien im selben Arbeitspaket nachgezogen, mit Changelog-Eintrag in
  beiden Repos.
- Vertragsversion und `skytech.v_hems_vertrag` werden gemeinsam erhöht.
- Solange die Version mit `0.` beginnt, sind inkompatible Änderungen zulässig; das HEMS arbeitet
  nur mit genau der Version, die es kennt.
- Mit der Umsetzung werden je Abschnitt Status und die betroffenen Codestellen eingetragen.
