# D-057: Wirksames Ladelimit je AC-Speicher als HA-Sensor

- **Datum:** 29.09.2026
- **Status:** Aktiv
- **Betrifft:** [`app/battery_publisher.py`](../../app/battery_publisher.py),
  [`app/main.py`](../../app/main.py),
  [`app/ems/devices.py`](../../app/ems/devices.py),
  [device_classes/battery.md](../device_classes/battery.md),
  [datenmodell.md](../datenmodell.md)

## Kontext

Seit den Ladestufen (D-056) hängt die maximale Ladeleistung eines Speichers von mehreren Größen
ab: der Wechselrichtergrenze `available_charge_power_w`, der greifenden Ladestufe, der Freigabe
`laden_erlaubt` und dem SoC. Das Ergebnis stand nur im Ingress-Status (`lade_limit_w`). In Home
Assistant — für Dashboards, Historie und Automationen — war es nicht sichtbar.

## Entscheidung

- Nach jedem Regelzyklus schreibt das Add-on je Speicher (`class: battery`) den Sensor
  `sensor.ems_<prefix>_lade_limit_w` über `POST /api/states`.
- State ist das Statusfeld `lade_limit_w` desselben Zyklus, auf ganze Watt gerundet — genau der
  Wert aus `BatteryDevice._lade_limit_w()`, mit dem die Zuteilung rechnet. Der Publisher rechnet
  nichts selbst.
- Attribute: `ladestufe_aktiv`, `ladestufe_max_w`, `wr_max_ladeleistung_w`, `blockiert_grund`,
  `soc_prozent`, dazu `unit_of_measurement: W`, `device_class: power`,
  `state_class: measurement`. Kein Zeitstempel, damit unveränderte Werte keine neuen
  Zustandsänderungen erzeugen.
- Immer aktiv, keine Add-on-Option, unabhängig von `flow_publish`.
- Der Speicherstatus trägt dafür zusätzlich `entity_prefix`.
- Wie D-046: nach dem Zyklus statt darin, ohne eigene HA-Abfrage, jeder Fehler wird verschluckt.
  Invariante 4 gilt weiterhin nur für den Regelpfad.

## Betrachtete Alternativen

- **Template-Sensor in Home Assistant:** verworfen. Er müsste die HEMS-Rechnung (Stufenauswahl,
  SoC-Latch, Freigaben) nachbauen und kann still davon abweichen.
- **Eigene Option `battery_sensor_publish`:** verworfen. Ein POST je Speicher und Zyklus kostet
  nichts; eine Option bringt nur Konfigurations- und Doku-Aufwand.
- **Kopplung an `flow_publish`:** verworfen. Die Übersicht soll auch ohne Flow Card funktionieren.
- **Andere Namen** (`_max_ladeleistung_aktuell_w`, `_ladeleistung_max_w`): verworfen.
  `lade_limit_w` ist identisch mit dem Statusfeld und nicht mit dem Stufen-Helfer
  `ladestufe_<n>_max_ladeleistung_w` oder dem Statusfeld `max_ladeleistung_w` (statische WR-Grenze)
  zu verwechseln.

## Folgen

- Per `POST /api/states` erzeugte Entitäten überleben keinen HA-Neustart; da jeder Zyklus schreibt,
  ist der Sensor spätestens ein Regelintervall später wieder da.
- Wird ein Speicher entfernt oder sein Präfix geändert, bleibt der alte Sensor bis zum HA-Neustart
  stehen. Steht das Add-on oder schlägt ein Zyklus fehl, behält der Sensor den letzten Wert.
