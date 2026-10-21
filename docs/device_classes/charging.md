# Wallbox-Ladeziele in Watt

**Stand: 21.10.2026. HEMS implementiert und softwaregetestet; Gegenstellen und
Hardwarebetrieb noch nicht freigegeben.**

Ein Ladeziel verwendet `class: controllable`, `output_unit: watt` und eine explizite
`charging_backend`. Bestehende Geräte ohne dieses Feld bleiben unverändert.

| Auswahl im Formular | Konfiguration | Gegenstelle |
|---|---|---|
| Über EVMS | `evms` | Bekannte Fahrzeuge über EVMS, Laufzeit noch Entwurf |
| Direkt über Wallbox-Provider | `wallbox_provider` | Physischer Ladepunkt; Provider bisher nur Ampere |
| Eigene HA-Automation | `automation` | Vom Betreiber implementierter Empfänger |

Das Formular steht unter **Konfiguration → Geräte → Regelbar → Wallbox-Anbindung**.
Beim Aktivieren werden Ausgabeeinheit und Sensorbezug umgestellt und die Leistungsgrenzen
zur Neueingabe zurückgesetzt. Amperewerte dürfen nicht als Wattwerte übernommen werden.

Gemeinsamer Datenvertrag: [Watt-Ladeprotokoll](../../contract/contract_hems_evms/charging_protocol.md).
HEMS–EVMS: [Paarvertrag](../../contract/contract_hems_evms/contract_hems_evms.md).
Eigenautomation: [Integrationsvertrag](../../contract/contract_hems_automation/README.md).

## Konfiguration

`actual_power_entity` bleibt leer; Messung, Freigabe und dynamische Grenzen kommen
zusammen aus der jeweiligen Schnittstellen-Entität. `charging_feedback_timeout_s`
begrenzt das Alter einer unveränderten Rückmeldung, Standard 90 Sekunden.

Beispiel einer vorbereiteten EVMS-Anbindung; Leistungswerte sind illustrative
Konfiguration und vor Verwendung an Fahrzeug und Anlage anzupassen:

```yaml
devices:
  - name: ladeziel_1
    label: Ladeziel 1
    class: controllable
    entity_prefix: ladeziel_1
    allowed_modes: manuell,nur_laden
    charging_backend: evms
    charging_feedback_timeout_s: 90
    output_unit: watt
    technical_minimum: 0
    technical_maximum: 11000
    increase_delay_s: 60
    decrease_delay_s: 60
    maximum_step_change: 1000
    minimum_step_change: 0
```

Ohne passenden Empfänger bleibt dieses Ziel gestoppt. Der HEMS-Verteiler muss nicht
wissen, ob ein Ziel einem Auto oder einem Anschluss entspricht; das EVMS-Zielmodell
ist noch offen. Eine automatische Anlage von HEMS-Geräten wird nicht behauptet.

## Regelverhalten

Bestehende Freigaben, Prioritäten, Zwang und Rampen gelten weiter. Zusätzlich sperren
fehlende/veraltete Rückmeldung, fehlende Zuordnung, falsche Protokollversion,
ungültige Messung und unbrauchbare Grenzen. Auch Zwang umgeht diese Sperren nicht.
Dynamische Grenzen begrenzen Nutzerwerte; ein abgesenktes Maximum wirkt trotz Totband.

HEMS schreibt nur Watt. Strom-/Phasenwahl wird im Provider beziehungsweise der
Automation umgesetzt. Die bestätigte Vorgabe wird im HEMS-Schnittstellensensor an die
aktuelle Zuordnung gebunden. Damit reicht ein alter positiver Ausgabehelfer nach
Fahrzeugwechsel nicht aus, um die neue Ladung freizugeben.

## Migration und Grenzen

Kein automatisches Umstellen von Ampere-Bestandsgeräten. Zunächst Empfänger implementieren
und prüfen, Watt-Helfer anlegen, Leistungsgrenzen neu festlegen, konkurrierende Steuerung
entfernen und erst dann die neue Anbindung aktivieren. Ohne EVMS bleibt direkte
Wallbox-Anbindung möglich; für EVMS gibt es vorerst keine unbekannten Fahrzeuge.

Ein physischer Anschluss darf nicht zugleich direkt und über EVMS konfiguriert sein.
Eine automatische systemweite Duplikatprüfung ist noch offen. Gemeinsame Anschlusslimits,
RFID, Sessions, Kosten und Energiequellen werden durch die HEMS-Vorbereitung nicht implementiert.
