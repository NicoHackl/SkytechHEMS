# D-059: Notabschaltung mit Quittierung und eigenem Merker

- **Datum:** 01.10.2026
- **Status:** Aktiv
- **Betrifft:** [`app/emergency.py`](../../app/emergency.py),
  [`app/emergency_rules.py`](../../app/emergency_rules.py), [`app/main.py`](../../app/main.py),
  [`app/ha_client.py`](../../app/ha_client.py), [`app/configuration.py`](../../app/configuration.py),
  [`web/src/pages/Notabschaltung.tsx`](../../web/src/pages/Notabschaltung.tsx),
  [`web/src/pages/Status.tsx`](../../web/src/pages/Status.tsx)

## Kontext

Speicher und Geräte wie ein E3DC oder eine Wallbox haben einen eigenen Automatikmodus. Das HEMS
übersteuert ihn nur. Bei einem Stromausfall oder einer anderen Extremsituation muss das HEMS
sofort alle Lasten abwerfen, die Geräte zurück in ihre Automatik schicken und danach stillhalten,
bis ein Mensch die Lage geprüft hat. Keine der vorhandenen Sperren deckt das ab:

- **Regelung aus, Modus `aus`, Lockout:** Sie wirken erst im nächsten Zyklus und ignorieren den
  Zwang (D-053) nicht. Binärgeräte bremst weiter das One-Change-Limit, und sie lösen sich von
  selbst wieder.
- **Kein Merker:** Nach einem Neustart von Add-on, HA oder Host regelte das HEMS sofort wieder.

Der Begriff „Notabschaltung" war bis zum 01.10.2026 für `binary_immediate_off` belegt; das heißt
seitdem „Mehrfachabschaltung erlaubt" und ist hiervon unabhängig.

## Entscheidung

- **Bedingung:** Eine konfigurierte Bedingung aus Entität, Operator (`=`, `≠`, `>`, `≥`, `<`,
  `≤`) und Sollwert. Ein eigener Wächter fragt sie jede Sekunde ab (`GET /api/states/<id>`), der
  Regelzyklus prüft sie zusätzlich als Rückfall. `unavailable`, `unknown` oder eine fehlende
  Entität lösen **nicht** aus.
- **Abschaltfolge:** Trifft die Bedingung zu, läuft einmal:
  1. Alle konfigurierten Geräte gehen auf ihren sicheren Zustand (`safe_shutdown_ops`: 0 W, aus,
     Speicher 0 W und `standby`). Das gilt ohne Zeitschutz, Rampe, Totband, Kaskade und
     One-Change und auch für Zwangsgeräte.
  2. Das Post-Cycle-Skript läuft.
  3. Die konfigurierten Zielzeilen werden in eingetragener Reihenfolge geschrieben.
- **Danach still:** Das HEMS schreibt nichts mehr, damit es die Automatik der Geräte nicht
  überschreibt. Nur fehlgeschlagene Befehle werden je Zyklus wiederholt, bis sie durchgehen.
- **Wiederanlauf nach Neustart:** Nach jedem Add-on-Start mit gesetztem Merker läuft die Folge
  einmal erneut.
- **Merker:** Er liegt in `/data/notabschaltung.json` und ist die **erste eigene Persistenz** des
  Add-ons. Eine fehlende Datei heißt „nicht aktiv", eine unlesbare „aktiv" (fail-safe).
  `sensor.ems_notabschaltung_aktiv` spiegelt den Merker nur und wird jeden Zyklus neu gesetzt.
- **Quittieren:** Nur über den Button im Tab Status (`POST api/emergency/acknowledge`), und nur,
  wenn eine frische Prüfung die Bedingung als auswertbar **und** nicht zutreffend ergibt. Danach
  baut das HEMS seinen Controller neu auf und regelt wieder.
- **Schreib-Lock:** Der Regelzyklus und die Notabschaltung teilen sich einen Schreib-Lock. Eine
  laufende Regel-Charge bricht vor dem nächsten Befehl ab. Kein Sollwert des Zyklus landet nach
  dem Abwurf.

## Betrachtete Alternativen

- **Merker als HA-Helfer (`input_boolean`):** verworfen. HA stellt ihn zwar wieder her, aber der
  Merker hinge an einem Helfer, den der Nutzer anlegen, löschen oder per `initial:` zurücksetzen
  kann. Ein über `POST /api/states` gesetzter Sensor überlebt keinen HA-Neustart.
- **Jeden Zyklus 0 W/aus wiederholen:** verworfen. Die HEMS-Schreibziele (z. B. Speicher auf
  `standby`) kämpften gegen die Automatik, in die die Zielzeilen die Geräte gerade versetzt haben.
- **WebSocket-Abo auf `state_changed`:** verworfen zugunsten des Sekundentakts. Der Takt reagiert
  in ≤ 2 s, ist robust und braucht keine Reconnect-Logik.
- **Quittieren jederzeit:** verworfen. Bei andauerndem Stromausfall liefe das HEMS sonst kurz an
  und löste sofort wieder aus.
- **Nicht auswertbare Bedingung löst aus:** verworfen. Jeder HA-Neustart erzeugte sonst eine
  Notabschaltung samt Quittierpflicht.

## Folgen

- `AGENTS.md` und `architektur.md` nennen den Merker als einzige Ausnahme vom Grundsatz „keine
  eigene Persistenz".
- Während der Notabschaltung zeigt das Status-Panel den letzten Regelzyklus davor. Die Flow Card
  wird nicht aktualisiert, die Ladelimit-Sensoren stehen auf 0 W.
- HA-Automationen, die HEMS-Helfer an echte Geräte weiterreichen, laufen asynchron. Ein
  Helferwechsel aus Schritt 1 kann eine Automation auslösen, die erst nach den Zielzeilen schaltet.
  Solche Automationen sollten `sensor.ems_notabschaltung_aktiv` als Bedingung prüfen.
- Die Konfiguration ist eine Add-on-Option und wirkt wie alle Optionen erst nach dem Neustart.

## Rücknahmebedingung

Erweist sich der Sekundentakt als zu langsam oder zu teuer, wird er durch ein WebSocket-Abo
ersetzt, der Regelzyklus bleibt Rückfall. Der Merker wandert nur dann in HA, wenn das Add-on eine
eigene, wiederherstellbare Entität anlegen kann.
