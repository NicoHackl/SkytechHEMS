# Wallbox-Ladeziele in Watt

**Stand: 26.11.2026. Die Watt-Anbindung im HEMS ist implementiert und softwaregetestet.
EVMS, Watt-Umsetzung im Provider und Hardwareabnahme stehen aus.**

Ein Ladeziel verwendet heute `class: controllable`, `output_unit: watt` und eine explizite
`charging_backend`. Bestehende Geräte ohne dieses Feld bleiben unverändert.

| Auswahl im Formular | Konfiguration | Gegenstelle |
|---|---|---|
| Über EVMS | `evms` | Fahrzeugzuordnung über EVMS, Laufzeit noch Entwurf |
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

Ohne passenden Empfänger bleibt dieses Ziel gestoppt. Das Zielbild sieht einen dauerhaft
konfigurierten virtuellen Ladepunkt je unabhängig steuerbarem Anschluss vor.

## Geplante Geräteklasse Wallbox

EVMS verknüpft den HEMS-Ladepunkt mit dem physischen Provider-Anschluss. Der
Betreiber wählt am Ladepunkt, ob Priorität, Plan und betriebliche Vorgaben aus
Ladepunkt- oder Fahrzeughelfern stammen. So kann die Priorität der Garage gelten
oder die des erkannten Fahrzeugs an den jeweiligen Ladepunkt mitwandern.
Zugang für bekannte Fahrzeuge und freier Modus sind separat wählbar.
Die Geräteklasse und die Profilwahl sind Planungsstand.
[Fachlicher Vertrag](../../contract/contract_hems_evms/contract_hems_evms.md).

## Wallbox ohne EVMS steuern

- **Direkt in Ampere (Bestandsbetrieb).** Ein regelbares Gerät mit
  `output_unit: ampere` ohne Watt-Anbindung einrichten und das HEMS-Präfix im
  Provider hinterlegen. Der Provider liest Ladestrom und bei automatischem
  Phasenbetrieb auch die Phasenvorgabe. Beide Softwareseiten sind implementiert,
  die Hardwareabnahme steht aus.
  [Konfigurationsbeispiel und Ampere-Vertrag 2.1](../../contract/contract_hems_wallbox_provider/contract_hems_wallbox_provider.md).
- **Direkt in Watt (vorbereitet).** Bei „Direkt über Wallbox-Provider“ kommt die
  Rückmeldung vom Provider. HEMS liefert sein bestätigtes Wattbudget unmittelbar
  an diesen Empfänger. Die Watt-Umsetzung im Provider steht aus.
  [Direkter Watt-Vertrag](../../contract/contract_hems_wallbox_provider/watt_contract.md).
- **Eigene HA-Automation.** Der Betreiber stellt den Empfänger und die technische
  Ansteuerung gemäß [Automationsvertrag](../../contract/contract_hems_automation/README.md).

Alle drei Varianten kommen ohne EVMS-Fahrzeugplätze oder Fahrzeughelfer aus.
Die Auswahl des Wegs erfolgt bei der Einrichtung. Ein EVMS-Ausfall löst keinen
automatischen Wechsel auf Direktsteuerung aus.

## Regelverhalten der Watt-Anbindungen

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
Wallbox-Anbindung möglich; der geplante EVMS-Gastmodus gehört zum EVMS-Weg.

Ein physischer Anschluss darf nicht zugleich direkt und über EVMS konfiguriert sein.
Eine automatische systemweite Duplikatprüfung ist noch offen. Gemeinsame Anschlusslimits,
RFID, Sessions, Kosten und Energiequellen werden durch die HEMS-Vorbereitung nicht implementiert.
