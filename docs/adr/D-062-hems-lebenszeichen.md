# D-062 — HEMS-Lebenszeichen für die Provider

**Datum:** 07.10.2026 · **Status:** Aktiv

## Kontext

Wallbox- und Battery-Provider übersetzen die HEMS-Sollwerthelfer in Gerätebefehle. Steht das HEMS
still, während Home Assistant weiterläuft, bleibt ein positiver Sollwert unbegrenzt stehen. Ein
unveränderter Helfer ist aber normaler Betrieb: das HEMS schreibt gleiche Werte bewusst nicht
erneut, weil sonst `last_changed` und damit Hoch-/Runter-Regelzeit zerstört würden.

## Entscheidung

- `app/status_publisher.py` veröffentlicht nach jedem durchlaufenen Zyklus
  `sensor.skytech_hems_status`; Felder und Auswertung legt der gemeinsame Vertrag fest
  (`contract/contract_hems_wallbox_provider/`, `contract/contract_hems_battery_provider/`).
- Der Zähler ändert sich bei jeder Veröffentlichung, auch nach einem fehlgeschlagenen Schreiben.
  Provider werten nur die Änderung mit ihrer eigenen Uhr aus.
- Auch während der Notabschaltung wird veröffentlicht: das HEMS lebt und hat die Helfer genullt.
- Ein Zyklus, der mit einer Ausnahme endet, veröffentlicht nichts. Bleibt das über die Frist so,
  stoppen die Provider.
- Ampere-Geräte (`controllable`, `output_unit: ampere`) ohne gültige Istleistung werden mit
  `istleistung_ungueltig` aus der Regelung genommen und auf `0` gesetzt — analog zum Speicher.

## Folgen

- Per `POST /api/states` erzeugte Entitäten überleben keinen HA-Neustart. Gewollt: der Provider
  stoppt bis zum ersten frischen Zyklus.
- Watt-Geräte behalten das bisherige Verhalten bei ungültiger Istleistung; eine Ausweitung ist
  eine eigene Entscheidung.
