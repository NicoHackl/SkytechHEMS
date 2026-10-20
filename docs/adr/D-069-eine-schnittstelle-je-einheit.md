# D-069: Eine Schnittstellen-Entität je Einheit

- **Datum:** 20.10.2026
- **Status:** Aktiv
- **Ersetzt:** [D-068](D-068-geraetefreigabe-provider-schnittstelle.md) (Feld `provider_entity`);
  ändert [D-062](D-062-hems-lebenszeichen.md) (Entität des Lebenszeichens)
- **Betrifft:** [`app/status_publisher.py`](../../app/status_publisher.py), [`app/main.py`](../../app/main.py),
  [`app/ems/controller.py`](../../app/ems/controller.py), [`app/ems/devices.py`](../../app/ems/devices.py)
  (`BatteryDevice`), [`app/configuration.py`](../../app/configuration.py), `web/src/`,
  [Vertrag Battery 2.0](../../contract/contract_hems_battery_provider/contract_hems_battery_provider.md),
  [Vertrag Wallbox 2.0](../../contract/contract_hems_wallbox_provider/contract_hems_wallbox_provider.md)

## Kontext

D-068 band Speicher über einen Schnittstellen-Sensor **je Speicher** an, den das HEMS über das
Feld `provider_entity` fand. Der User will einen anderen Grundsatz: Jede Einheit (HEMS, jeder
Provider) veröffentlicht genau **eine** Entität `sensor.<einheit>_schnittstelle`, die alle
Informationen für alle anderen Teilnehmer enthält.

## Entscheidung (User, 20.10.2026)

1. Das HEMS veröffentlicht nach jedem durchlaufenen Zyklus `sensor.hems_schnittstelle`:
   State = `entity_prefix` aller Speicher, durch Komma getrennt; Attribute = Lebenszeichen
   (`zyklus_zaehler`, `zyklus_intervall_s`, `erzeugt_am`, `vertrag_version` 2) und je Speicher
   `<prefix>_ladeleistung`/`<prefix>_entladeleistung` aus den eigenen Sensoren. Ohne gültige
   Messung (oder während der Notabschaltung) fehlen diese beiden Attribute.
2. `sensor.skytech_hems_status` entfällt. Der Wallbox-Provider wird im selben Arbeitspaket
   umgestellt.
3. Das HEMS liest die Freigaben aus `sensor.battery_provider_schnittstelle`
   (`<entity_prefix>_ladefreigabe`/`_entladefreigabe`). Fehlend oder kein Bool = erlaubt. Die
   Sperrgründe zeigt die Statuskarte.
4. SoC und Istleistung kommen wieder nur aus `soc_entity` und Variante A/B. `provider_entity`
   entfällt; das Schemafeld bleibt in `config.yaml`, damit eine gespeicherte Bestandsoption den
   Start nicht verhindert, und wird mit einer Warnung ignoriert.
5. Version 3.0.0 (bricht Schnittstellen).

## Folgen

- HEMS, Battery-Provider und Wallbox-Provider müssen zusammen aktualisiert werden. Ein Provider
  ohne passendes Lebenszeichen hält sein Gerät im sicheren Zustand (0 W bzw. Stopp).
- `sensor.hems_schnittstelle` ändert sich jeden Zyklus; der Recorder speichert jede Änderung samt
  Attributen. Empfehlung: im Recorder ausschließen.
- Die übrigen Paare (Energy-Pilot, Powerflow-Card, Data-Insight) folgen dem Grundsatz in eigenen
  Arbeitspaketen.
