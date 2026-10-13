# D-065: Preis- und Prognosemodul im HEMS für den dynamischen Strompreis

- **Datum:** 12.10.2026
- **Status:** Aktiv, teilweise umgesetzt (P3 seit 13.10.2026: Preis- und PV-Quelle, eigener Takt, Anzeige-Sensoren, Bereich „Dynamischer Strompreis“; seit 13.10.2026 auch P4: Speicherung in Data Insight samt Grundlast, und P5: Verbrauchsprognose, Reichweite, Kennzahlen, Netzlade-Freigabe als Anzeige, P6: Grafana-Dashboard in Data Insight; Vertrag 0.3: Grundlast je Minute, Netzanschluss und Energiezähler; Beobachtung (P7) und Steuerung offen)
- **Betrifft:** künftig `app/tariff/`, `app/insight_client.py`, `app/tariff_publisher.py`,
  Add-on-Optionen, neuer Tab „Dynamischer Strompreis“, Vertrag
  [`contract_hems_data_insight`](../../contract/contract_hems_data_insight/contract_hems_data_insight.md)
  (Version 0.3); löst den Entwurf
  `erweiterungen/erweiterung_ac_speicher_1.md` §11.1 und die Abgrenzung „Prognose und Planung“ in
  [architektur.md](../architektur.md) ab

> Ausführlicher, mit dem User abgestimmter Plan: `dynamischer_strompreis_plan_claude.md` im
> gemeinsamen Arbeitsordner der Skytech-Repos (Entscheidungen E-1 bis E-19). Dieses ADR hält die
> Grundsatzentscheidungen fest; Details stehen dort, bis sie gebaut und in `docs/` beschrieben sind.

## Kontext

Speicher sollen bei wenig PV in günstigen Stunden aus dem Netz laden und die Energie in teuren
Stunden für das Haus liefern. Bisher galt (§11.1): „Das HEMS bewertet keine Preise“; Preislogik
sollte der Energy Pilot oder eine HA-Automation liefern. Der Energy Pilot ist optional und
KI-gestützt; der dynamische Strompreis soll aber auch ohne ihn und deterministisch funktionieren.
Inzwischen regelt das HEMS zwei Speicher (`acspeicher1`, `e3dc_speicher`, D-063).

## Betrachtete Optionen

### Option A — Eigenes Modul im HEMS, außerhalb des Regelzyklus (gewählt)

- Dafür: läuft ohne Energy Pilot; deterministisch und nachvollziehbar; kennt die Speicher und
  deren Grenzen direkt.
- Dagegen: das HEMS bekommt Prognose- und Preislogik und eine Datenbank-Abhängigkeit.

### Option B — Energy Pilot plant, HEMS führt aus (Stand §11)

- Dafür: Planung bleibt beim Planer.
- Dagegen: dynamischer Strompreis nur mit installiertem, KI-gestütztem EP.

### Option C — Data-Insight rechnet die Prognosen

- Dagegen: Fachlogik im Speicherdienst; Data-Insight ist optional und nur amd64.

## Entscheidung

Option A. Festgelegt mit dem User am 12.10.2026:

1. **Eigener Takt, nicht im Regelzyklus.** Ein Fehler in Preis, Prognose oder Datenbank beeinflusst
   den Regelzyklus nie.
2. **Preisquelle:** ein frei wählbarer HA-Sensor im Format von `sensor.epex_spot_data_total_price_2`
   (Attribut `data` mit `start_time`, `end_time`, `price_per_kwh`), Endpreis. Raster 15/60 min aus
   dem Sensor ermittelt oder fest gewählt. Das HEMS rechnet keine Aufschläge auf.
3. **PV-Prognose:** Helios (heute, morgen, Rest heute, 15-min-Kurve).
4. **Verbrauchsprognose:** deterministisches Profil aus der Grundlast (Hausverbrauch ohne
   HEMS-Verbraucher und ohne Speicher, die im Hausverbrauch-Sensor stecken).
5. **Datenhaltung in Data-Insight** über eine eigene Rolle `skytech_hems` (Weg B des
   Data-Insight-Umsetzungsplans), intern über den Add-on-Hostnamen. Das HEMS legt die benötigten
   Sensoren dort an, übernimmt bereits vorhandene und kennzeichnet sie als verwaltet; Data-Insight
   sperrt sie gegen Änderungen. Das HEMS kann die Entitäten über eine Rollen-Zuordnung austauschen,
   ohne dass die Historie abreißt. Data-Insight bleibt optional. Maßgeblich für Verbindung,
   Rechte, Rollen und Tabellen ist der
   [Vertrag](../../contract/contract_hems_data_insight/contract_hems_data_insight.md).
6. **DB-Treiber:** `psycopg` 3 (reine Python-Variante, async) mit `libpq5` aus Debian, weil das Image
   auch für `armhf`, `armv7` und `i386` gebaut wird.
7. **Schalter:** `input_boolean.ems_netzladen_freigabe` (UND), `input_boolean.ems_netzladen_manuell`
   (ODER mit dem PV-Kriterium), je Speicher `input_boolean.ems_<prefix>_netzladen_erlaubt`.
8. **Steuerung offen:** Wann und wie viel geladen wird (Restlaufzeit, PV im Reichweitenfenster,
   günstigstes Fenster, Teilladung) wird gesondert festgelegt. Bis dahin ist das Modul reine
   Datenerhebung und schaltet nichts.

## Folgen

- **Positiv:** dynamischer Strompreis ohne Energy Pilot; Prognosegüte in Grafana messbar, bevor
  eine Steuerung darauf vertraut.
- **Negativ:** erste Laufzeit-Abhängigkeit neben `aiohttp`; neue Gegenstelle Data-Insight mit
  eigenem Vertrag.
- **Aufwand:** Phasen P1 bis P7 laut Plan, siehe [roadmap.md](../roadmap.md) M6.

## Rücknahmebedingung

Erreicht die Prognosegüte nach der Beobachtungsphase das vereinbarte Abnahmekriterium nicht
(14 Tage Daten, Verbrauch ±15 % Tagesenergie, PV in 80 % der Slots im p10–p90-Band) und lässt
sie sich auch nicht verbessern, wird keine Steuerung darauf gebaut.
