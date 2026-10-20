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

## Grundsatz: eine Schnittstellen-Entität je Einheit

Seit 20.10.2026 (Entscheidung des Users) gilt für den Austausch über Home Assistant: Jede Einheit,
die anderen Teilnehmern etwas mitteilt, veröffentlicht dafür genau **eine** Entität
`sensor.<einheit>_schnittstelle` mit allen Informationen für alle anderen Teilnehmer. Werte stehen
als Attribute, je Gerät mit dessen Präfix vorne; der State nennt die Präfixe, durch Komma getrennt.
Sollwerte des HEMS laufen weiter über seine `input_*`-Ausgabehelfer.

| Einheit | Schnittstellen-Entität | Inhalt | Leser |
|---|---|---|---|
| SkytechHEMS | `sensor.hems_schnittstelle` | Lebenszeichen, Istwerte der Speicher | Battery-Provider, Wallbox-Provider |
| Battery-Provider | `sensor.battery_provider_schnittstelle` | Lade-/Entladefreigabe und Sperrgrund je Speicher | SkytechHEMS |
| Wallbox-Provider | `sensor.wallbox_provider_schnittstelle` | Freigabe und Sperrgrund je Wallbox | SkytechHEMS |
| Energy Pilot | `sensor.energy_pilot_schnittstelle` | Vorschläge je Gerät mit Gültigkeitsfenster | SkytechHEMS |

Dokumentierte Ausnahmen:

- **Powerflow-Card:** `sensor.skytech_hems_flow_config` und `sensor.skytech_hems_flow_status`
  bleiben getrennt. Sie sind Anzeigedaten für eine Karte, und die große Konfiguration soll nur bei
  Änderung geschrieben werden. Die Karte selbst veröffentlicht nichts.
- **Anzeige-Entitäten** für Nutzer und Dashboards bleiben einzeln, z. B.
  `sensor.ems_<prefix>_lade_limit_w`, `sensor.ems_notabschaltung_aktiv`, `sensor.ems_dyn_*`,
  `sensor.ep_plan_status`, `sensor.ep_hems_verbindung` und die EP-Zusatz-Vorschläge
  `sensor.ep_<obj>_vorschlag`.
- **HEMS → Energy Pilot** bleibt REST (`/api/device_controls_schema`, `/api/status`): groß und nur
  bei Bedarf gelesen.
- **Data Insight** tauscht über die Datenbank aus (Funktionen und Sichten), nicht über
  HA-Entitäten; der Grundsatz betrifft diesen Weg nicht.

| Gegenstelle | Vertrag | Stand / Hinweise |
|---|---|---|
| Powerflow-Card | [kontrakt.md](contract_powerflow_card_hems/kontrakt.md) | Implementierter Kartenvertrag mit zugehörigen Plänen. |
| Energy-Pilot | [contract_hems_energy_pilot.md](contract_hems_energy_pilot/contract_hems_energy_pilot.md) | Version 2.0: Vorschläge über `sensor.energy_pilot_schnittstelle`; dokumentierte Kompatibilitätsgrenzen. |
| Battery-Provider | [contract_hems_battery_provider.md](contract_hems_battery_provider/contract_hems_battery_provider.md) | Aktueller Austausch einschließlich dokumentierter Betriebsgrenzen; Version 2.0: je Einheit eine Schnittstellen-Entität (`sensor.hems_schnittstelle`, `sensor.battery_provider_schnittstelle`); Marstek-Freigaben per Soll/Ist-Vergleich mit HEMS-Istwerten; E3DC-Statusbits noch nicht negativ getestet. |
| Wallbox-Provider | [contract_hems_wallbox_provider.md](contract_hems_wallbox_provider/contract_hems_wallbox_provider.md) | Version 2.1 (Lebenszeichen aus `sensor.hems_schnittstelle`, Freigaben aus `sensor.wallbox_provider_schnittstelle`); in beiden Projekten implementiert, Hardware-Abnahme des Providers offen. |
| Data-Insight | [contract_hems_data_insight.md](contract_hems_data_insight/contract_hems_data_insight.md) | Version 0.3: Datenhaltung für den dynamischen Strompreis (D-065), HEMS-Reihen je Minute, Netzanschluss und Energiezähler. In beiden Projekten implementiert (HEMS-Phasen P4 und P5). |
