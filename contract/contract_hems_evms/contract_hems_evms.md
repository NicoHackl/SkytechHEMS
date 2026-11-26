# Vertrag: SkytechHEMS ↔ Skytech EVMS

**Version: 0.2 — 26.11.2026.**

| Seite | Status |
|---|---|
| HEMS | Watt-Anbindung implementiert und softwaregetestet. Eigene Geräteklasse Wallbox und Profilwahl sind geplant. |
| EVMS | Entwurf; Repository vorbereitet, keine Laufzeit |
| Gemeinsamer Betrieb | Nicht abgenommen; Hardware fehlt |

Autoritatives Austauschformat: [Watt-Ladeprotokoll 1](charging_protocol.md).
Beide Dateien liegen unter demselben relativen Pfad wortgleich in beiden Repositories.

## Ladepunkt und Regelungsquelle

Im HEMS richtet der Betreiber je unabhängig steuerbarem Anschluss einen dauerhaften
virtuellen Ladepunkt ein. Im EVMS verknüpft er diesen mit dem physischen Anschluss
des Providers. Beim Anstecken ordnet EVMS das erkannte Fahrzeug diesem Anschluss
für den laufenden Vorgang zu.

Für den Weg über EVMS wird am Ladepunkt gewählt, welche betrieblichen Einstellungen
gelten. Bei Ladepunktregelung stammt etwa die Priorität aus
`input_number.ems_<prefix>_prioritat`, bei Fahrzeugregelung aus dem Helfer des
zugeordneten virtuellen Fahrzeugplatzes, etwa `input_number.evms_fahrzeug1_prioritat`.
Eine kleinere Zahl hat in beiden Fällen Vorrang. Die gewählte Quelle soll auch
Ladeplan und betriebliche Soll- und Grenzwerte bestimmen. Weitere Helfer, Übergabe
der wirksamen Werte und eine mögliche Übersteuerung je Vorgang sind offen.

HEMS verteilt die Wattbudgets anhand der wirksamen Einstellungen. Der Befehlsweg
bleibt HEMS → EVMS → Provider. Fahrzeug- und Hardwaregrenzen gelten bei beiden
Regelungsquellen. Strom, Phasen und Gerätefreigabe setzt der Provider um.

## Zulassung am Ladepunkt

Unabhängig von der Regelungsquelle sind zwei Zugangsarten vorgesehen. Bei
„Nur bekannte Fahrzeuge“ setzt die Zulassung eine eindeutige Fahrzeugzuordnung
voraus. Im freien Modus darf auch ein Gast nach dem wirksamen Plan laden.
Fehlt das Fahrzeugprofil, gelten die Einstellungen des Ladepunkts.
Der Plan „Überschuss“ kann auch bei zugelassenem Fahrzeug ein Budget von 0 W ergeben.

Auch ein Gast braucht eine frische, für den aktuellen Anschlussvorgang gültige
Zuordnungskennung nach dem Watt-Ladeprotokoll. Eine Fahrzeug- oder RFID-Kennung
ist dafür im freien Modus entbehrlich. Ein Wechsel entwertet die vorherige
Bestätigung. Nach einem Neustart muss die aktuelle Verbindung erneut feststehen.

## Abgrenzung und offene Punkte

Die direkte HEMS-Anbindung an den Wallbox-Provider und die eigene HA-Automation
kommen ohne EVMS aus. Pro Anschluss gilt genau ein Befehlsweg. Die technische
Höchstleistung wird je Wallbox berücksichtigt. Eine gemeinsame Leistungsbegrenzung
mehrerer Ladepunkte liegt außerhalb dieses Arbeitspakets.

Offen sind unter anderem die Erkennung am konkreten Gerät, Scan-Zuordnungsfenster,
Wiederanlauf, weitere Fahrzeughelfer und Abfahrtszeiten. Data Insight liegt außerhalb
der Echtzeitfreigabe.
