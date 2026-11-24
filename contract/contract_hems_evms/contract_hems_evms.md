# Vertrag: SkytechHEMS ↔ Skytech EVMS

**Version: 0.1 — 21.10.2026.**

| Seite | Status |
|---|---|
| HEMS | Watt-Anbindung implementiert, Softwaretests vorhanden |
| EVMS | Entwurf; Repository vorbereitet, keine Laufzeit |
| Gemeinsamer Betrieb | Nicht abgenommen; Hardware fehlt |

Autoritatives Austauschformat: [Watt-Ladeprotokoll 1](charging_protocol.md).
Beide Dateien liegen unter demselben relativen Pfad wortgleich in beiden Repositories.

## Rollen

HEMS verteilt Wattbudgets und setzt Prioritäten um. EVMS verwaltet bekannte Fahrzeuge,
RFID-Zuordnungen und aktuelle physische Anschlüsse. EVMS veröffentlicht die Rückmeldung
unter `sensor.evms_schnittstelle`. Im HEMS wird `charging_backend: evms` gewählt.

EVMS bestätigt ein Ladeziel nur bei eindeutig zugeordnetem bekannten Fahrzeug und
verfügbarer Wallbox. Ein Modus „unbekanntes Fahrzeug“ ist vorerst ausgeschlossen.
Die Verwaltung des HEMS-Ladeziels (dauerhaft je Fahrzeug oder anderes Modell) ist noch
nicht entschieden. Der Vertrag legt deshalb keine automatische Geräteanlage fest.

EVMS begrenzt Vorgaben durch Fahrzeugvorgaben, leitet sie zum richtigen Anschluss und
übermittelt Rückmeldungen. Der Provider übernimmt die Strom-/Phasenwahl und Gerätebefehle.

## Offene Punkte

Ladezielmodell, Scan-Zuordnungsfenster, Konfigurations-/Betriebszustand nach Neustart,
gemeinsame Anschlusslimits und Ladeziele/Abfahrtszeiten vor EVMS-Implementierung klären.
Kein direkter neuer Energy-Pilot-Vertrag im Erstumfang. Data Insight liegt außerhalb
jeder Echtzeitfreigabe.
