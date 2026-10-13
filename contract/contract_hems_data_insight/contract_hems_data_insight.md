# Vertrag: SkytechHEMS ↔ Skytech Data Insight

**Version:** 0.3

**Status:** In beiden Projekten implementiert

**Stand:** 13.10.2026

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

Jeder Abschnitt nennt seinen Status je Seite. Data Insight erfüllt diese Version mit den
System-Migrationen `0003_hems_anbindung.sql` und `0004_hems_minuten.sql`, SkytechHEMS mit dem
Data-Insight-Client (Phasen P4 und P5). Geprüft am 13.10.2026 mit einem Integrationstest des HEMS
gegen eine von Data Insight migrierte Datenbank; 0.2 zusätzlich Ende-zu-Ende mit Live-Daten der
Referenzanlage.

**Änderung gegenüber 0.2:** Eigene Reihen `hems.*` kommen je Minute und werden von Data Insight
nicht mehr fortgeführt; Grund: Unter 0.2 führte Data Insight den einzigen Grundlast-Wert als
Konstante fort, und das HEMS hielt die Grundlast deshalb für aktuell (an der Referenzanlage am
13.10.2026 gesehen). Neu sind die Sicht `v_hems_rolle_1min`, das Zählerkennzeichen in
`hems_sensor_sichern` und die Rollen für Netzanschluss und Energiezähler.

**Änderung gegenüber 0.1:** Das HEMS schreibt nicht mehr direkt in Tabellen, sondern nur über
Datenbankfunktionen. Grund: Das HEMS schreibt den Mittelwert eines Slots erst nach dessen Ende,
datiert auf den Slot-Beginn. Die Minutenwerte sind zu diesem Zeitpunkt schon gerechnet. Die
Funktion meldet neue Werte deshalb Data Insight, das sie nachrechnet. Außerdem ist das zugelassene
Netz auf den Add-on-Bereich `172.30.33.0/24` begrenzt.

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
SkytechHEMS ── hems_sensor_sichern / _stilllegen / hems_zuordnen ──► Data Insight
SkytechHEMS ── hems_messwerte_schreiben, hems_lauf_schreiben ──────► Data Insight
SkytechHEMS ◄── Sichten (Verlauf je Rolle, Prognosen, Vertrag) ───── Data Insight
Home Assistant ── Zustände der Sensoren mit Quelle ha ─────────────► Data Insight (Collector)
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

**Status:** Data Insight implementiert · SkytechHEMS implementiert

| Punkt | Festlegung |
|---|---|
| Datenbank | `skytech` |
| Netz | Internes Add-on-Netz von Home Assistant, Port `5432` des Data-Insight-Containers. Der Weg funktioniert auch, wenn der LAN-Port 5432 abgeschaltet ist (Data Insight D-009) |
| Host im HEMS | Option `insight_host`, Voreinstellung `auto`. Bei `auto` ermittelt das HEMS über den Supervisor (`GET /addons`) das installierte Add-on mit dem Slug `*_skytech_data_insight` und bildet daraus den Hostnamen (`_` wird `-`). Ein fester Hostname ist ebenso zulässig |
| Port im HEMS | Option `insight_port`, Voreinstellung `5432` |
| Rolle | `skytech_hems`, Anmeldung mit Passwort (`scram-sha-256`) |
| Secret | Data Insight erzeugt es auf der Seite „Zugänge“ (Schlüssel `hems`) und speichert es in der Option `hems_password`. Im HEMS wird es als Option `insight_password` eingetragen. Ohne gesetztes Passwort ist die Anmeldung gesperrt |
| Zugelassene Adressen | Nur der Add-on-Bereich des Supervisor-Netzes, `172.30.33.0/24` (an der Referenzanlage am 12.10.2026 geprüft: HEMS `172.30.33.7`, Data Insight `172.30.33.8`). Bewusst nicht `172.30.32.0/23`: Verbindungen über den freigegebenen LAN-Port kommen mit der Absenderadresse des Docker-Gateways `172.30.32.1` an (im Containertest am 12.10.2026 geprüft) und wären sonst zugelassen |
| Geheimhaltung | Das Secret erscheint auf keiner Seite in Log, Status oder API |

**Bekannte Grenze:** Die Verbindung im internen Add-on-Netz ist nicht mit TLS verschlüsselt.

## Vertragsversion

**Status:** Data Insight implementiert · SkytechHEMS implementiert

Data Insight stellt die Sicht `skytech.v_hems_vertrag` mit genau einer Zeile und der Spalte
`version` (`text`) bereit; für diese Vertragsversion `0.3`. Das HEMS prüft sie bei jedem
Verbindungsaufbau. Weicht sie von der Version ab, die das HEMS kennt, liest und schreibt es nichts
und meldet die Abweichung in seinem Status.

## Rechte der Rolle `skytech_hems`

**Status:** Data Insight implementiert · SkytechHEMS implementiert

Die Rolle schreibt ausschließlich über die Funktionen unten (`SECURITY DEFINER`, für alle anderen
Rollen gesperrt). Direkte `INSERT`, `UPDATE` oder `DELETE` auf Tabellen sind ihr nicht erlaubt.

| Objekt | Recht |
|---|---|
| `skytech.hems_sensor_sichern`, `skytech.hems_sensor_stilllegen`, `skytech.hems_zuordnen`, `skytech.hems_messwerte_schreiben`, `skytech.hems_lauf_schreiben` | `EXECUTE` |
| `skytech.sensor`, `skytech.kategorie`, `skytech.groesse` | `SELECT` |
| `skytech.v_messwert_15min`, `skytech.v_messwert_1h` | `SELECT` |
| `skytech.hems_zuordnung`, `skytech.v_hems_zuordnung`, `skytech.v_hems_rolle_1min`, `skytech.v_hems_rolle_15min` | `SELECT` |
| `skytech.prognose_lauf`, `skytech.prognose_wert` und die Prognose-Sichten | `SELECT` |
| `skytech.v_hems_vertrag` | `SELECT` |

Kein Zugriff auf `skytech_config`, keine Schemaänderung. Die Funktionen melden Eingabefehler mit
SQLSTATE `22023` und einer deutschen Meldung.

## Verwaltete Sensoren

**Status:** Data Insight implementiert · SkytechHEMS implementiert

`skytech.sensor` hat die Spalte `verwaltet_von` (`text`, `NULL` oder `'hems'`).

```text
skytech.hems_sensor_sichern(entity_id text, attribut text, name text, kategorie text,
                            groesse text, einheit text, quelle text,
                            energie_zaehler boolean) → integer (Sensor-ID)
skytech.hems_sensor_stilllegen(sensor_id integer) → void
```

- `hems_sensor_sichern` legt den Sensor an (`verwaltet_von = 'hems'`). Gibt es die Entität mit
  gleichem `attribut` schon, **übernimmt** es die Zeile: `verwaltet_von = 'hems'`, die vorhandenen
  Messwerte bleiben. Es setzt `name`, `kategorie`, `groesse`, `einheit`, `energie_zaehler` und
  `aktiv = true`; andere Spalten (z. B. `anlage`) bleiben unverändert. Mit `energie_zaehler = true`
  rechnet Data Insight je Minute den Zuwachs (`zuwachs`); eigene Reihen `hems.*` sind nie Zähler. Wiederholte Aufrufe mit gleichen Werten ändern
  nichts. `quelle` ist `ha` oder `hems`; Reihen mit Quelle `hems` heißen `hems.<name>`,
  HA-Sensoren nie. Hat eine vorhandene Zeile eine andere Quelle, wird abgelehnt.
- `hems_sensor_stilllegen` setzt einen verwalteten Sensor auf `aktiv = false`. Er bleibt
  verwaltet, seine Messwerte bleiben erhalten.
- Nicht verwaltete Sensoren ändert das HEMS nie, außer durch die Übernahme.

**Data-Insight-Seite:**

- Ein Trigger auf `skytech.sensor` lehnt `UPDATE` und `DELETE` an verwalteten Zeilen ab
  (SQLSTATE `SKY01`). Nur die Funktionen oben heben die Sperre innerhalb ihres Aufrufs auf. Damit
  gilt die Sperre für Oberfläche, MCP und direktes SQL gleichermaßen.
- Oberfläche: eigener Abschnitt „Über Vertrag verwaltet — Skytech HEMS“ auf der Seite „Sensoren“
  mit Rolle und Zustand; die Detailseite zeigt den Sensor nur an.
- API: `PUT` und `DELETE api/sensors/{id}` antworten bei verwalteten Sensoren mit `409` und dem
  Grund; `GET api/sensors` liefert `verwaltet_von` und `hems_rollen` (aktuelle Rollen).
- MCP: Änderungen an verwalteten Sensoren werden mit derselben Begründung abgelehnt.
- Änderungsprotokoll: Anlegen, Übernehmen, Aktualisieren, Stilllegen und Zuordnungswechsel
  erscheinen mit `quelle = 'hems'`.
- Der Collector zeichnet verwaltete Sensoren mit `quelle = 'ha'` wie jeden anderen HA-Sensor auf.

## Rollen und Austausch

**Status:** Data Insight implementiert · SkytechHEMS implementiert. Die Rollen `schalter_*` belegt das
HEMS nur, wenn der jeweilige Helfer in Home Assistant existiert.

Das HEMS spricht Sensoren nur über Rollen an. So kann es die Entität hinter einer Rolle tauschen
(neues Home Assistant, umbenannte Entität, anderer Sensor im HEMS-Tab), ohne dass die Historie
abreißt.

```text
skytech.hems_zuordnen(rolle text, sensor_id integer) → void
```

- `skytech.hems_zuordnung(rolle, sensor_id, gueltig_ab)` wird nur ergänzt, nie geändert. Eine
  Zuordnung gilt bis zum nächsten Eintrag derselben Rolle. Die erste Zuordnung einer Rolle gilt ab
  `-infinity`, damit auch die Historie eines übernommenen Sensors zählt.
- Nur verwaltete Sensoren lassen sich zuordnen; eine unveränderte Zuordnung ändert nichts.
- Sicht `skytech.v_hems_zuordnung`: `rolle`, `sensor_id`, `entity_id`, `attribut`, `name`,
  `gueltig_ab`, `gueltig_bis` (`NULL` = aktuell).
- Sichten `skytech.v_hems_rolle_1min` und `skytech.v_hems_rolle_15min`: `rolle`, `zeit`,
  `sensor_id`, `einheit` und die Spalten von `messwert_1min` bzw. `messwert_15min` (`mittel`,
  `minimum`, `maximum`, `letzter`, `zuwachs`, `anzahl`, `abdeckung_s`), über Sensorwechsel hinweg
  zusammengesetzt. `anzahl` zählt die Rohwerte; `0` heißt, der Wert wurde nur fortgeführt.
- Tausch: neuen Sensor sichern → `hems_zuordnen` → alten Sensor stilllegen. Das HEMS gleicht beim
  Start und nach jeder Konfigurationsänderung ab.

**Rollenkatalog 0.3** (Syntax `^[a-z_]+(:[a-z0-9_]+)?$`). Rollen mit Größe `leistung` haben die
Einheit `W`, Zählerrollen (`*_energie`) `kWh` oder `Wh`. Das HEMS ordnet einen Sensor mit anderer
Einheit nicht zu und meldet das in seinem Status. Alle Rollen ab `netz_leistung` sind optional.

| Rolle | Quelle | Kategorie / Größe | Bedeutung |
|---|---|---|---|
| `hausverbrauch` | `ha` | verbraucher / leistung | Hausverbrauch-Sensor des HEMS-Tabs |
| `pv_ist` | `ha` | pv / leistung | gemessene PV-Leistung |
| `netz_leistung` | `ha` | netz / leistung | Leistung am Netzanschluss, **positiv = Bezug** (seit 0.3) |
| `netz_bezug_energie`, `netz_einspeisung_energie` | `ha` | netz / energie, Zähler | Zähler für Netzbezug und Einspeisung (seit 0.3) |
| `pv_ist_energie` | `ha` | pv / energie, Zähler | Zähler des PV-Ertrags (seit 0.3) |
| `hausverbrauch_energie` | `ha` | verbraucher / energie, Zähler | Zähler des Hausverbrauchs (seit 0.3) |
| `speicher_laden_energie:<geraet>`, `speicher_entladen_energie:<geraet>` | `ha` | speicher / energie, Zähler | Zähler der geladenen bzw. entladenen Energie je HEMS-Speicher (seit 0.3) |
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

**Status:** Data Insight implementiert · SkytechHEMS implementiert. `hems.reichweite_h` fehlt in Slots,
in denen die Speicher über den Prognosehorizont hinaus reichen oder keine Reichweite berechenbar ist.

```text
skytech.hems_messwerte_schreiben(sensor_id integer, zeiten timestamptz[],
                                 werte double precision[]) → integer (neu geschriebene Werte)
```

- Nur für aktive, verwaltete Sensoren mit `quelle = 'hems'` (`hems.<name>`).
- Das HEMS schreibt je Minute höchstens einen Wert mit `zeit` = Minutenbeginn. Zustände
  (`netzladen_zulaessig`) als `1`/`0`.
  - `hems.grundlast_w`: aus den Minutenwerten der Rollen (`v_hems_rolle_1min`) für jede
    abgeschlossene Minute, sobald ihr Ende mindestens 2 min zurückliegt. Eine Minute entfällt, wenn
    ein Summand fehlt oder unter 48 s abdeckt; Leistungen müssen in `W` vorliegen. Den Fortschritt
    misst das HEMS nur an Minuten mit echtem Rohwert (`anzahl > 0`).
  - `hems.nutzbar_kwh`, `hems.reichweite_h`, `hems.netzladen_zulaessig*`: der Momentanwert des
    Auswertungstakts (60 s) zum Minutenbeginn.
- **Keine Fortführung:** Ein Rohwert einer Reihe mit Quelle `hems` gilt genau für seine Minute.
  Fehlt ein Wert, gibt es für diese Minute keinen Minutenwert – eine Lücke, keine Konstante.
  Sensoren mit Quelle `ha` führt Data Insight wie bisher fort, bis der nächste Wert kommt.
- Zeitpunkte dürfen nicht in der Zukunft liegen; Werte müssen endlich sein; höchstens 10 000 Werte
  je Aufruf. Bereits vorhandene Zeitpunkte bleiben unverändert (kein Überschreiben).
- Neue Werte meldet die Funktion per `NOTIFY skytech_hems_werte`. Data Insight rechnet die
  Minutenwerte ab dem frühesten neuen Zeitpunkt nach, höchstens 10 Tage zurück. Aus Home Assistant
  holt Data Insight für diese Sensoren nichts.
- Nach einem Ausfall füllt das HEMS Lücken von `hems.grundlast_w` aus den aufgezeichneten
  Einzelsensoren nach (höchstens 10 Tage zurück, je Aufruf höchstens ein Tag); die übrigen
  `hems.*`-Reihen bleiben lückenhaft.

## Prognose- und Auswertungsläufe

**Status:** Data Insight implementiert · SkytechHEMS implementiert. Verbrauchslauf mit Methode
`profil_v1` stündlich ab 7 Tagen Grundlast-Historie; Auswertungslauf (Methode `kennzahlen_v1`)
stündlich oder nach jedem neuen Preis-, PV- oder Verbrauchslauf.

```text
skytech.hems_lauf_schreiben(art text, quelle text, erstellt timestamptz, raster_min integer,
                            gueltig_ab timestamptz, gueltig_bis timestamptz, einheit text,
                            methode text, details jsonb, zeiten timestamptz[],
                            werte double precision[], p10 double precision[] DEFAULT NULL,
                            p90 double precision[] DEFAULT NULL) → bigint (Lauf-ID)
```

Gespeichert wird in `skytech.prognose_lauf` (`id`, `art`, `quelle`, `erstellt`, `raster_min`,
`gueltig_ab`, `gueltig_bis`, `einheit`, `methode`, `details`) und `skytech.prognose_wert`
(`lauf_id`, `zeit` = Slot-Beginn, `wert`, `p10`, `p90`; Hypertable).

| `art` | `quelle` | Raster | Werte | Pflichtschlüssel in `details` |
|---|---|---|---|---|
| `preis` | Entity-ID des Preissensors | 15 oder 60 | Endpreis in €/kWh je Slot | `entity` |
| `pv` | Entity-ID der Prognosekurve | 15 | mittlere Leistung in W je Slot, mit `p10`/`p90` | `entity`, `ist_rolle`, `heute_kwh`, `morgen_kwh`, `rest_heute_kwh` |
| `verbrauch` | `hems:<methode>` | 15 | mittlere Leistung in W je Slot, mit `p10`/`p90` | `ist_rolle`, `historie_tage`, `parameter` |
| `auswertung` | `hems:kennzahlen` | 15 | keine Werte | Kennzahlen (Reichweite, PV im Reichweitenfenster, Preisfenster …) |

- Ein Lauf entsteht in **einem** Aufruf und wird danach nie geändert; gelöscht wird er nur durch
  die Aufbewahrung.
- Die Funktion prüft: `details` ist ein Objekt mit den Pflichtschlüsseln, `gueltig_bis` liegt
  nach `gueltig_ab`, alle Zeitpunkte liegen in diesem Zeitraum, Werte sind endlich, Werte, `p10`
  und `p90` sind gleich lang, ein Auswertungslauf hat keine Werte.
- Ein Preislauf entsteht nur, wenn sich die Preiskurve geändert hat (Pflicht des HEMS).
- Sichten: `v_prognose_aktuell` (jüngster Lauf je Art und Slot, mit `bis` und `ist_rolle`),
  `v_prognose_vortag` (jüngster Lauf, der mindestens 24 h vor dem Slot erstellt wurde), `v_preis`
  (`zeit`, `bis`, `preis_eur_kwh`), `v_prognose_vs_ist` (PV und Verbrauch: aktuell, Vortag mit
  Band, Ist aus `v_hems_rolle_15min`), `v_prognose_guete_tag` (je Berliner Tag und Art: Slots,
  mittlerer Fehler in W, Prognose-, Ist- und Fehlerenergie in kWh, Anteil im p10–p90-Band, jeweils
  für die Vortagsprognose).

## Aufbewahrung

**Status:** Data Insight implementiert

Schlüssel `aufbewahrung_prognose_tage` in `skytech_config.einstellung`, Voreinstellung `365`,
`null` = nie. Eine tägliche Aufgabe löscht `pv`-, `verbrauch`- und `auswertung`-Läufe, die älter
sind; Preisläufe bleiben ohne Ablauf. `hems.*`-Messreihen folgen der normalen Aufbewahrung von
Data Insight.

**Bekannte Grenze:** Den Schlüssel ändert man per SQL; die Seite „Speicher“ zeigt ihn noch nicht.

## Fehlerverhalten

**Status:** Data Insight implementiert · SkytechHEMS implementiert

- Data Insight nicht erreichbar, Anmeldung abgelehnt oder Vertragsversion abweichend: Das HEMS
  meldet das in seinem Status und versucht es im nächsten Takt erneut. Läufe werden nicht
  gepuffert, sie entstehen beim nächsten Takt neu.
- Ein Fehler im Datenaustausch beeinflusst den Regelzyklus des HEMS nie.
- Lehnt eine Funktion einen Aufruf ab (SQLSTATE `22023`), ist nichts davon gespeichert. Das HEMS
  verwirft den betroffenen Lauf bzw. die betroffenen Werte und meldet den Grund.

## Zuständigkeiten und Nicht-Ziele

| Thema | Zuständig |
|---|---|
| Prognosen, Kennzahlen, Rollenwahl, Austausch von Sensoren | SkytechHEMS |
| Schema, Funktionen, Rechte, Sperre verwalteter Sensoren, Aufzeichnung der HA-Sensoren, Nachrechnen der Minutenwerte, Sichten, Aufbewahrung | Skytech Data Insight |
| Grafana-Dashboards | nicht Vertragsteil; sie lesen die Sichten oben |

Nicht Teil dieses Vertrags: Steuerentscheidungen (Netzladen, Entladesperre), der Energy Pilot und
jede Schreibverbindung von Data Insight zum HEMS.

## Kompatibilität und Änderungen

- Jede Änderung wird in beiden Kopien im selben Arbeitspaket nachgezogen, mit Changelog-Eintrag in
  beiden Repos.
- Vertragsversion und `skytech.v_hems_vertrag` werden gemeinsam erhöht.
- Solange die Version mit `0.` beginnt, sind inkompatible Änderungen zulässig; das HEMS arbeitet
  nur mit genau der Version, die es kennt.

## Implementierungsstellen

| Seite | Stellen |
|---|---|
| Skytech Data Insight | `app/sql/0003_hems_anbindung.sql` (Schema, Funktionen, Sichten, Rechte, Aufbewahrung), `app/sql/0004_hems_minuten.sql` (Sicht `v_hems_rolle_1min`, Zählerkennzeichen, Vertragsversion 0.3, Bereinigung fortgeführter Minuten), `app/minute_values.py` (keine Fortführung für `hems.*`), `rootfs/usr/share/skytech/bootstrap.sql` und `bootstrap_skytech.sql` (Rolle), `templates/pg_hba.conf` (Netz), `app/access_service.py` (Zugang `hems`), `app/sensor_service.py`, `app/main.py`, `app/mcp_tools.py` (Sperre, `409`), `app/collector.py` (keine HA-Werte für `hems.*`, Nachrechnen), Seiten „Sensoren“, „Sensor“, „Zugänge“, „Protokoll“; Tests in `tests/test_db_integration.py` |
| SkytechHEMS | `app/insight_client.py` (einzige Stelle mit Datenbankzugriff, Vertragsversion), `app/tariff/insight_sync.py` (Rollen, Austausch, Läufe, Grundlast, eigene Reihen), `app/tariff/load_forecast.py` (Verbrauchsprognose `profil_v1`), `app/tariff/analysis.py` (Reichweite, Kennzahlen, Netzlade-Freigabe), `app/main.py` (Takt, Host über Supervisor `GET /addons`), `app/configuration.py` und `app/config_service.py` (Optionen `insight_*`, Netzanschluss und Zähler, Passwort nie an die Oberfläche), Bereich „Dynamischer Strompreis“; Tests in `tests/test_insight.py` und `tests/test_tariff_p5.py` |
