# HEMS ↔ eigene HA-Automation

**Stand: 21.10.2026. HEMS implementiert; Automation vom Betreiber bereitzustellen.**

Es gibt kein zweites Repository für die individuelle HA-Automation. Deshalb liegt
hier ausdrücklich ein einseitiger Integrationsvertrag, keine fehlende Gegenkopie.

Die Automation implementiert [Watt-Ladeprotokoll 1](charging_protocol.md) mit
`charging_backend: automation` und `sensor.wallbox_automation_schnittstelle`.
Sie verantwortet Frische, Messwerte, Watt-/Strom-/Phasenumsetzung, Grenzen und Stopp.
Das HEMS schreibt den Watt-Helfer und veröffentlicht die Zuordnungsbestätigung.
Eine Automation, die ausschließlich einen Watt-Helfer liest, erfüllt diesen Vertrag nicht.

Es wird noch keine gerätespezifische Beispielautomation ausgeliefert, weil Gerät,
Firmware und sichere Umsetzung noch nicht verifiziert sind. Die bestehende generische
`controllable`-Anbindung ohne `charging_backend` bleibt separat nutzbar.
