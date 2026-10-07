# Projektübergreifende Verträge

Die Verträge folgen der gemeinsamen Struktur der Skytech-Projekte:

```text
contract/
├── README.md
└── contract_<projektpaar>/
    ├── <vertragsdatei>.md
    └── <zugehoerige-plaene>.md  # falls vorhanden
```

Jedes Projektpaar besitzt einen eigenen Ordner. Der gemeinsame Vertrag liegt unter
demselben relativen Pfad und wortgleich in beiden beteiligten Repositories. Änderungen
an der Schnittstelle werden im selben Arbeitspaket in beiden Kopien nachgezogen.

Der Status im Vertrag unterscheidet implementierten Austausch, bekannte Grenzen
und Entwürfe. Ein Plan oder eine Dokumentationsänderung allein implementiert keine
Schnittstelle. Lokale Dokumentation verlinkt den Vertrag, statt eine abweichende
Beschreibung der gemeinsamen Felder zu führen.

| Gegenstelle | Vertrag | Stand / Hinweise |
|---|---|---|
| Powerflow-Card | [kontrakt.md](contract_powerflow_card_hems/kontrakt.md) | Implementierter Kartenvertrag mit zugehörigen Plänen. |
| Energy-Pilot | [contract_hems_energy_pilot.md](contract_hems_energy_pilot/contract_hems_energy_pilot.md) | Aktueller Austausch einschließlich dokumentierter Kompatibilitätsgrenzen. |
| Battery-Provider | [contract_hems_battery_provider.md](contract_hems_battery_provider/contract_hems_battery_provider.md) | Aktueller Austausch einschließlich dokumentierter Betriebsgrenzen; HEMS-Lebenszeichen als Entwurf (Version 1.1). |
| Wallbox-Provider | [contract_hems_wallbox_provider.md](contract_hems_wallbox_provider/contract_hems_wallbox_provider.md) | Entwurf, Version 1.1 (07.10.2026); nur die HEMS-Schreibreihenfolge für Phase und Strom ist implementiert. Umsetzung: `umsetzungsplan.md` im Repo Skytech-HEMS-Wallbox-Provider. |
