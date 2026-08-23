# D-046: Anzeigedaten der Power Flow Card als eigene HA-Sensoren veröffentlichen

- **Datum:** 23.08.2026
- **Status:** Aktiv
- **Betrifft:** `app/flow_publisher.py`, `app/ha_client.py`, `app/main.py`,
  `app/configuration.py`, `config.yaml`, Invariante 4 in
  [../architektur.md](../architektur.md), Datenvertrag
  [`vertrag_powerflow_card_hems/kontrakt.md`](../../vertrag_powerflow_card_hems/kontrakt.md)

## Kontext

Die **Skytech Power Flow Card** zeichnet den Leistungsfluss im Haus — Erzeugung, Netz, Speicher,
Haus und die einzelnen Verbraucher. Ihr Vorbild
[`power-flow-card-plus`](https://github.com/flixlix/power-flow-card-plus) verlangt, dass jede
Entität im Dashboard-Editor verdrahtet wird.

Für eine HEMS-Anlage ist das eine zweite Pflegestelle: die „Individual Devices" des Vorbilds sind
exakt die Geräte, die das HEMS ohnehin kennt und regelt. Wird ein Gerät angelegt, umbenannt oder
entfernt, müsste das Dashboard nachgezogen werden — zwei Wahrheiten über dieselbe Anlage.

Ziel war deshalb eine Karte, die mit `type: custom:skytech-power-flow-card` auskommt und ihre
gesamte Konfiguration vom HEMS bezieht. Offen war nur: auf welchem Weg.

Randbedingung: Das HEMS hat keine eigene Persistenz, und der Regelzyklus läuft synchron in einem
einzigen asyncio-Prozess. Was auch immer der Weg kostet, er darf den Zyklus nicht aufhalten.

## Betrachtete Optionen

### Option A — Die Karte ruft das Add-on über Ingress auf

- Dafür: Das Add-on kennt seine Daten bereits, ein Endpunkt wäre schnell gebaut. Kein zweiter
  Datenvertrag, keine Entitäten in der HA-Zustandsmaschine, keine Recorder-Last.
- Dagegen: Eine Lovelace-Karte läuft im HA-Frontend, nicht unter
  `/api/hassio_ingress/<token>/`. Um dorthin zu gelangen, müsste sie sich per WebSocket die
  Ingress-URL des Add-ons besorgen und eine Ingress-Session samt Cookie unterhalten — nur für
  Administratoren möglich, an HA-Interna gekoppelt und auf Polling angewiesen. Ein
  Nicht-Administrator sähe eine leere Karte, und jede Änderung an HA-Interna bräche sie.

### Option B — Das Add-on veröffentlicht zwei `sensor.*`-Entitäten

- Dafür: HA-nativ, für jeden Benutzer sichtbar, ereignisgesteuert statt Polling. Die Karte macht
  keinen einzigen HTTP-Aufruf und braucht keine Adminrechte. Trennt man Konfiguration und Status
  in zwei Entitäten, bleibt die große Nutzlast aus dem Zyklustakt heraus.
- Dagegen: Es bricht Invariante 4 in ihrer bisherigen Formulierung. Per `POST /api/states`
  erzeugte Entitäten überleben keinen HA-Neustart. Die Statusentität ändert sich jeden Zyklus und
  belastet den Recorder.

## Entscheidung

**Option B.** Ausschlaggebend war nicht der Aufwand, sondern wer die Karte sehen kann: Option A
funktioniert nur für Administratoren und nur, solange HA seine Ingress-Interna nicht ändert. Eine
Karte, die für den halben Haushalt leer bleibt, ist keine Karte.

Der Preis wird ausdrücklich bezahlt und benannt:

1. **Invariante 4 wird präzisiert**, nicht aufgegeben: *im Regelpfad schreibt das Add-on
   ausschließlich `input_*`-Helfer; darüber hinaus veröffentlicht es reine Anzeigedaten als eigene
   `sensor.*`-Entitäten, die kein Gerät schalten.* Aus dem Publisher wird nichts geschaltet, und
   keine Regelentscheidung liest die beiden Entitäten.
2. **Der Neustart-Verlust wird erkannt statt hingenommen.** Der Publisher prüft jeden Zyklus, ob
   die Konfigurationsentität im Zustandsabbild steht, und schreibt sie sonst neu. Das kostet
   nichts: der Abzug liegt ohnehin vor. Nach einem HA-Neustart ist die Karte spätestens nach einem
   Regelintervall wieder vollständig.
3. **Die Recorder-Last wird dokumentiert.** Die Trennung in zwei Entitäten hält die große Nutzlast
   aus dem Zyklus heraus; die Empfehlung zum `recorder`-Ausschluss steht in
   [../konfiguration.md](../konfiguration.md).

Zwei weitere Festlegungen fielen bei der Umsetzung an, weil der Vertrag eine andere Frage
beantwortet als der interne Status:

- **`addon_version` kommt vom Supervisor**, einmal beim Start gelesen und gecacht. `config.yaml`
  liegt nicht im Image (`COPY app/ .`), und ein YAML-Parser ist zur Laufzeit nicht installiert.
  Eine Konstante im Code wurde verworfen: `.github/workflows/bump-version.yaml` zählt nur
  `config.yaml` hoch, die Konstante liefe unweigerlich auseinander. Ohne Supervisor bleibt das
  Feld leer statt geraten.
- **`runtime_active` und `inactive_reasons` werden übersetzt.** Der Vertrag fragt „regelt gerade
  mit" und verlangt deutschen Klartext. Intern meldet `runtime_active` nur die
  Schreibziel-Gesundheit, die Freigabeentscheidung steht in `eligible`, und die Gründe sind
  bewusst stabile snake_case-Tokens. Der Publisher bildet beides ab: `eligible and runtime_active`
  und eine Übersetzungstabelle. Ein unbekannter Token wird unverändert durchgereicht — ein
  inaktives Gerät ohne jede Begründung wäre schlimmer als ein technischer Text.

## Folgen

- **Positiv:** Die Karte braucht null Dashboard-Konfiguration und zieht bei jeder Änderung im HEMS
  von selbst nach. Sie liest ausschließlich `hass.states`, aktualisiert damit im Takt von Home
  Assistant statt im Regelintervall und bleibt lesbar, wenn das Add-on gerade steht.
- **Negativ:** Zwei Entitäten mehr in der Zustandsmaschine, eine davon mit Änderung je Zyklus. Ein
  zweiter Datenvertrag, der gepflegt werden muss. Nach einem HA-Neustart zeigt die Karte für bis
  zu ein Regelintervall ihren Klartexthinweis.
- **Aufwand:** Neues Modul `app/flow_publisher.py`, `HAClient.set_state()`, ein Aufruf am Ende von
  `HEMSApp._run_cycle()`, die `flow_*`-Optionen, der Diagnoseendpunkt `GET api/flow/preview` und
  der Panel-Bereich „Flow Card".

## Rücknahmebedingung

Diese Entscheidung ist zurückzunehmen, wenn eines davon eintritt:

- Home Assistant unterbindet `POST /api/states` für Add-ons oder verwirft die so erzeugten
  Entitäten häufiger als beim Neustart. Dann trägt der Transportweg nicht mehr.
- Die Konfigurationsnutzlast überschreitet dauerhaft 16 KiB, sodass Home Assistant sie nicht mehr
  aufzeichnet. Der Publisher warnt ab 12 KiB; bleibt die Warnung stehen, muss die Geräteliste
  aufgeteilt oder ausgedünnt werden.
- Es zeigt sich, dass die Statusentität den Recorder auch mit Ausschlussregel spürbar belastet.
  Dann gehört der Statusteil in ein Attribut der Konfigurationsentität oder in ein
  Ereignis statt in einen Zustand.
