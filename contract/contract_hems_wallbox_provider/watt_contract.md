# Ergänzender Vertrag: HEMS ↔ Wallbox-Provider in Watt

**Version: 0.1 — 21.10.2026.**

| Seite | Stand |
|---|---|
| HEMS | `charging_backend: wallbox_provider` implementiert und softwaregetestet |
| Wallbox-Provider | Watt-Empfänger und neue Rückmeldung noch nicht implementiert |
| Hardware | go-e noch nicht geliefert; Modell/Firmware und Verhalten offen |

Das [Watt-Ladeprotokoll 1](charging_protocol.md) ist die neue Schnittstelle.
Der [bisherige Ampere-Vertrag 2.1](contract_hems_wallbox_provider.md) bleibt bis zur
bewussten Migration aktiv. Keine stillschweigende Konvertierung bestehender Konfiguration.

Der Provider muss eine vollständige Rückmeldung inklusive Istleistung, dynamischen
Wattgrenzen, Prozess-/Zuordnungskennung und Zähler unter seiner bestehenden einen
Schnittstellen-Entität veröffentlichen. Ältere Freigabeattribute allein genügen nicht.

HEMS liefert Watt-Helfer und Zuordnungsbestätigung. Der Provider übernimmt Stromwahl,
Phasenwahl, technische Umschaltabläufe und erneute Prüfung vor jedem Gerätebefehl.
Genau eine Quelle je Anschluss: direkter HEMS-Weg, EVMS oder manuell. Die endgültige
Provider-Konfiguration und Migration dieser Quellenauswahl werden mit der Umsetzung festgelegt.

Die zusätzlichen HEMS-Attribute `ladevertrag_version` und `ladeziele` können von
bestehenden Ampere-Empfängern ignoriert werden; sie ändern den alten Vertrag nicht.

## Noch zu implementieren und abzunehmen

Wattumsetzung ohne Aufrunden über das Budget, dynamische Grenzen, Zuordnungsbindung,
Lebenszeichen, manuelle Übergabe, Ausfälle und Phasenwechsel. Für automatische
Fahrzeugzuordnung zusätzlich RFID gemäß EVMS–Provider-Vertrag.
