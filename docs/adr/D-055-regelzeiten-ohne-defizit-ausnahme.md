# D-055: Regelzeiten und Totband ohne Defizit- und Entlade-Ausnahme

- **Datum:** 24.09.2026
- **Status:** Aktiv
- **Betrifft:** [`app/ems/devices.py`](../../app/ems/devices.py),
  [`app/ems/controller.py`](../../app/ems/controller.py),
  [device_classes/controllable.md](../device_classes/controllable.md),
  [device_classes/battery.md](../device_classes/battery.md)

## Kontext

Die Anlage läuft mit 2 s Zyklus, beide Speicher mit 3 s Hoch- und Runter-Regelzeit und 25 W
Mindeständerung. Die HA-Historie vom 24.09.2026 (19:45–21:45) zeigte eine Asymmetrie. Erhöhungen
der Entladung hielten Regelzeit und Totband immer ein. Rücknahmen der Entladung kamen dagegen
zu rund 75 % schon nach 2 s, und etwa die Hälfte war kleiner als 25 W. Das war so gebaut:

- `_ramp_entladen` prüfte nur die Hoch-Regelzeit;
- `get_write_ops` schaltete das Totband beim Zurücknehmen einer Entladung ab;
- jeder Netzbezug (`current_deficit_w > 0`) senkte Verbraucher und Speicherladung sofort und ohne
  Runter-Regelzeit ab;
- Ein- und Ausschalten umgingen das Totband, auch ein Start aus 0 auf wenige Watt.

Geregelt wird auf Netzpunkt ±0, dort rauscht die Bilanz ständig um 0 W. Jede Rücknahme kam sofort
durch, jede Erhöhung musste warten. Der Entlade-Sollwert lief deshalb als Sägezahn unter dem
Bedarf, und das Totband wirkte nur in eine Richtung.

## Entscheidung

- Hoch- und Runter-Regelzeit gelten für Laden **und** Entladen in beide Richtungen, auch bei
  Netzbezug. Die Ausnahme „bei Defizit sofort" entfällt für regelbare Geräte und Speicher.
- Das Totband gilt für jede Sollwertänderung. Sofort und ohne Totband gehen nur das Stoppen auf
  0 (Speicher: Standby) und ein direkter Richtungswechsel am Speicher durch.
- Ein Start aus 0 wird erst ab der Mindeständerung geschrieben. Bei regelbaren Geräten reicht
  alternativ ein technisches Minimum, das kleiner als das Totband ist. Solange der Start
  unterdrückt ist, bleibt am Speicher auch die Betriebsart auf `standby`.
- Unverändert bleiben die Notabschaltung der Binärgeräte (`binary_immediate_off`), der Lockout,
  die Sicherheits-Stopps des Speichers sowie Zwang und Zwang-Ende (D-053).

## Betrachtete Alternativen

- **Schwelle statt Wegfall:** Sofort abregeln erst ab einem Netzbezug über dem globalen Puffer.
  Verworfen: Bei einer Regelung auf ±0 soll die Regelzeit das einzige Tempo-Maß sein.
- **Nur die Regelzeit, Totband weiter ausnehmen:** verworfen. Kleinstschritte beim Zurücknehmen
  hätten weiter jeden Zyklus geschrieben.

## Folgen

- Bei plötzlichem Netzbezug senken Geräte nur noch im Takt ihrer Runter-Regelzeit und
  Schrittbegrenzung ab. Lange Runter-Regelzeiten (z. B. Wallbox 180 s bei 1 A pro Schritt) führen
  zu minutenlangem Netzbezug. Die Werte sind daraufhin zu prüfen.
- Ein kurzzeitig zu hoher Entlade-Sollwert speist bis zum Ablauf der Runter-Regelzeit
  Speicherenergie ins Netz ein.

## Rücknahmebedingung

Führt das zu dauerhaftem Netzbezug, der sich über die Helferwerte nicht beherrschen lässt, wird
eine Sofort-Schwelle über dem globalen Puffer eingeführt statt der alten Ausnahme bei jedem Watt.
