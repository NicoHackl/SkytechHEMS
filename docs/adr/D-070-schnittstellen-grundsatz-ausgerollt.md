# D-070: Grundsatz „eine Schnittstellen-Entität je Einheit“ auf alle Bestandteile ausgerollt

- **Datum:** 20.10.2026
- **Status:** Aktiv
- **Baut auf:** [D-069](D-069-eine-schnittstelle-je-einheit.md)
- **Betrifft:** [`app/ems/devices.py`](../../app/ems/devices.py), [`app/main.py`](../../app/main.py)
  (`/api/ep`), `web/src/pages/EnergyPilotVorschlaege.tsx`, `web/src/pages/Status.tsx`,
  [Vertrag Energy Pilot 2.0](../../contract/contract_hems_energy_pilot/contract_hems_energy_pilot.md),
  [Vertrag Wallbox 2.1](../../contract/contract_hems_wallbox_provider/contract_hems_wallbox_provider.md),
  `contract/README.md` (Grundsatz und Ausnahmen)

## Kontext

D-069 führte den Grundsatz ein: Jede Einheit veröffentlicht genau eine Entität
`sensor.<einheit>_schnittstelle` mit allen Informationen für die anderen Teilnehmer. Umgesetzt
waren HEMS und Battery-Provider. Der User will den Grundsatz auf alle Bestandteile ausrollen.

## Entscheidung (User, 20.10.2026)

1. **Energy Pilot → HEMS:** Vorschläge stehen in `sensor.energy_pilot_schnittstelle` als
   Attribute `<prefix>_<feld>` mit globalem `valid_from`/`valid_until`. Der EP schreibt den Plan in
   einem Schreibvorgang; `sensor.ep_plan_commit` und die Einzelsensoren entfallen. Die
   Diagnosecodes von `ep_proposal_status` bleiben (`mismatched_plan` entfällt).
2. **HEMS → Energy Pilot** bleibt REST (Schema und Status sind groß und werden nur bei Bedarf
   gelesen).
3. **Wallbox-Provider → HEMS:** `sensor.wallbox_provider_schnittstelle` mit `<prefix>_freigabe`
   und `<prefix>_sperrgrund`. Gesperrt bei: nicht erreichbar, Gerätefehler, kein Fahrzeug
   verbunden. Das HEMS nimmt die Wallbox dann aus der Regelung (`wallbox_gesperrt`, 0 A,
   Überschuss an den nächsten Verbraucher). Fehlend = frei.
4. **Ausnahmen:** Flow-Card-Sensoren (Anzeigedaten, große Konfiguration nur bei Änderung),
   Anzeige-Entitäten (`sensor.ems_*_lade_limit_w`, `sensor.ems_notabschaltung_aktiv`,
   `sensor.ems_dyn_*`, `sensor.ep_plan_status`, `sensor.ep_hems_verbindung`, EP-Zusatz-Vorschläge),
   der DB-Austausch mit Data Insight.
5. Version 4.0.0: die EP-Schnittstelle ist inkompatibel.

## Folgen

- HEMS und Energy Pilot müssen zusammen aktualisiert werden; mit einem alten EP fällt jedes Gerät
  auf die Nutzerwerte zurück (sicher).
- Die Wallbox-Freigabe gilt für jedes regelbare Gerät, dessen Präfix der Wallbox-Provider meldet;
  Präfixe müssen eindeutig sein.
