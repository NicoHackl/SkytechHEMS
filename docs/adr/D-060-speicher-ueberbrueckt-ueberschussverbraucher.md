# D-060: Speicher überbrückt freigegebene Überschussverbraucher

- **Datum:** 05.10.2026
- **Status:** Aktiv
- **Betrifft:** [`app/ems/devices.py`](../../app/ems/devices.py),
  [`app/ems/controller.py`](../../app/ems/controller.py), [`app/main.py`](../../app/main.py),
  [device_classes/global.md](../device_classes/global.md),
  [device_classes/battery.md](../device_classes/battery.md),
  [datenmodell.md](../datenmodell.md), [architektur.md](../architektur.md)

## Kontext

D-B14 (in D-040) legt fest: ein Speicher deckt nur den Hausverbrauch, nie eine HEMS-Last. Die
einzige Ausnahme war bisher die Zwangslast (D-053). Technisch rechnet `entlade_basis_w` jede
gemessene HEMS-Last zurück, deshalb steht sie nie in `hausdefizit_w`.

Bei einem abrupten PV-Einbruch regelt ein Überschussverbraucher aber nicht sofort ab: Runter-Regelzeit
und Schrittbegrenzung gelten auch bei Netzbezug (D-055), ein Binärgerät hält Mindestlaufzeit und
Abschaltverzögerung ein. Bis dahin kommt die Lücke aus dem Netz, obwohl ein voller Speicher
daneben steht.

## Betrachtete Optionen

### Option A — Nur überbrücken

Die Last eines freigegebenen Verbrauchers wird für freigegebene Speicher als zusätzlicher
Fehlbetrag ausgewiesen. Der Pool bleibt unverändert, der Verbraucher regelt normal ab.

- Dafür: Die Speicherentladung wird weiter über `netz_support_w` aus dem Pool herausgerechnet, die
  Rückkopplung H-1 bleibt ausgeschlossen. Der Speicher entlädt nur so lange, wie die Lücke besteht.
- Dagegen: Ein Verbraucher kann nicht dauerhaft aus dem Speicher laufen.

### Option B — Dauerhaft versorgen

Die Entladung zählt als verfügbare Leistung im Pool.

- Dafür: Ein Heizstab läuft weiter, bis der Speicher leer ist.
- Dagegen: Die Entladung sieht wie PV-Überschuss aus (H-1). Das braucht eine eigene Begrenzung und
  eine eigene SoC-Logik. Vom User verworfen.

### Ablageort: HA-Helfer statt Add-on-Option

Zur Laufzeit schaltbar, ohne Neustart, und automatisch im Steuerung-Tab. Gleiches Muster wie
`laden_erlaubt` und `force`.

## Entscheidung

Option A mit zwei optionalen Opt-in-Helfern:

- `input_boolean.ems_<prefix>_aus_speicher_decken` am regelbaren oder binären Verbraucher.
- `input_boolean.ems_<prefix>_uberschussverbraucher_versorgen` am Speicher.

Fehlt ein Helfer oder ist er ausgefallen, gilt er als `off`. Bestandsanlagen verhalten sich
dadurch unverändert.

Rechnung je Zyklus:

```text
speicher_deckbar_w   = Σ current_w der Verbraucher mit aus_speicher_decken
verbraucherdefizit_w = max(−(entlade_basis_w − speicher_deckbar_w), 0) − hausdefizit_w
```

- Gedeckt wird nur die **vom HEMS angeforderte** Last (`current_w`). Fremdsteuerung bleibt nach
  D-B14 ungedeckt, eine Zwangslast steckt bereits im Hausdefizit.
- `verbraucherdefizit_w` gibt es nur mit Speicher und gültiger Hausleistungsbilanz, sonst `0`.
- Verteilung: zuerst `hausdefizit_w` über alle entladebereiten Speicher nach `entlade_prioritat`,
  danach `verbraucherdefizit_w` nur über Speicher mit `uberschussverbraucher_versorgen`, in
  derselben Reihenfolge, mit deren Restkapazität.
- Der Entlade-Abschlag wirkt weiter genau einmal: zuerst vom Hausdefizit, ein Rest davon vom
  Verbraucheranteil.
- Untergrenze ist `soc_min_prozent`; eine eigene SoC-Grenze für die Überbrückung gibt es nicht.

## Folgen

- **Positiv:** Bei einem PV-Einbruch bleibt das Netz frei, solange der Verbraucher abregelt.
  Pool, Rampen, Zeitschutz und Mehrfachabschaltung sind unverändert.
- **Negativ:** Der Speicher folgt mit eigener Rampe. Schaltet ein Binärgerät ab, entlädt er noch
  bis zu einer Runter-Regelzeit weiter und speist kurz ein. Die Plausibilitätswarnung „Entladung
  und Pool gleichzeitig" muss die Überbrückung abziehen, sonst wäre sie hier ein Fehlalarm.
- **Aufwand:** Zwei Helfer, die Statusfelder `speicher_deckbar_w`, `verbraucherdefizit_w`,
  `aus_speicher_decken`, `uberschussverbraucher_versorgen` und `verbraucher_anteil_w`.
  `hausdefizit_anteil_w` ist jetzt nur noch der Hausanteil.

## Rücknahmebedingung

Pendelt die Anlage im Betrieb zwischen Speicherentladung und Einspeisung, weil der Speicher einem
abschaltenden Verbraucher regelmäßig hinterherläuft, ist die Überbrückung in dieser Form falsch.
Dann gehört der Verbraucheranteil an die Abschaltzeitpunkte gekoppelt, statt an die gemessene Last.
