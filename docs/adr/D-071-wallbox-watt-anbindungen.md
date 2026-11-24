# D-071: Wallbox-Ladeziele in Watt mit drei Anbindungswegen

- Datum: 21.10.2026
- Status: HEMS implementiert; Gegenstellen vorbereitet, Hardware offen

## Entscheidung

Der Nutzer möchte HEMS → EVMS → Wallbox-Provider, HEMS → Wallbox-Provider sowie
HEMS → eigene HA-Automation. HEMS verteilt Wattbudgets. EVMS soll Fahrzeuge und
Anschlusszuordnungen verwalten; die technische Strom-/Phasenumsetzung liegt im
Provider beziehungsweise in der Eigenautomation. Das EVMS-Ladezielmodell ist offen.

## Umsetzung

Additives `charging_backend` an `controllable`, eigener `ChargingDevice` mit der
bestehenden Watt-Verteilung. Alte Watt-/Ampere-Geräte bleiben unverändert.
Die Gegenstelle liefert einen vollständigen, versionierten Rückmeldeschnappschuss.
Kein Ersatzwert bei fehlenden Fahrzeug-/Gerätedaten. Erst eine beobachtete weitere
Rückmeldung erlaubt Laden; monotone Frist pro Ladeziel.

Watt-Helfer bleiben Ausgabe. Zusätzlich bestätigt `sensor.hems_schnittstelle`
zu jedem Ladeziel Anbindung, Zuordnung und Budget nach der Schreibcharge. Bei
Fehler/Notabschaltung ist das Budget null. Diese additive Metadaten-Erweiterung
ändert weder den bestehenden Speicher-State noch die bisherige Vertragsversion 2.

## Folgen

Das Add-on wird auf 4.1.0 vorbereitet. Noch keine EVMS-Laufzeit, kein neuer Provider-
Regelweg und keine Datenbankmigration. Inbetriebnahme erst nach Gegenstellenumsetzung
und Hardwareabnahme. Alle offenen Fachentscheidungen bleiben dokumentiert.

[Konfiguration](../device_classes/charging.md) ·
[HEMS–EVMS-Vertrag](../../contract/contract_hems_evms/contract_hems_evms.md)
