# D-043: Speichergrenzen sind direkte Wattwerte in der Add-on-Konfiguration

- **Datum:** 21.08.2026
- **Status:** Aktiv
- **Betrifft:** `app/configuration.py`, `app/ems/devices.py`, `config.yaml`, Konfigurationsseite,
  `/api/device_controls_schema`, [device_classes/battery.md](../device_classes/battery.md)
- **Ersetzt:** den `available_*`-Sensor-Teil von D-041

## Kontext

D-041 legte `available_charge_power_entity` und `available_discharge_power_entity` als
verpflichtende HA-Sensorzuordnungen fest. Für den tatsächlichen Gerätevertrag werden diese beiden
Grenzen jedoch nicht als laufende Home-Assistant-Messwerte bereitgestellt. Sie werden bei der
Gerätepflege als feste Wattwerte vorgegeben, beispielsweise `0 W` für eine gesperrte Richtung und
`1500 W` als erlaubte Obergrenze.

Die Sensorfelder zwangen den User dadurch, Entity-IDs einzutragen, obwohl an dieser Stelle Werte
gemeint sind. Fehlende oder nicht verfügbare Sensorzustände waren ein künstlicher Fehlerfall des
falschen Datenvertrags.

## Betrachtete Optionen

### Option A — verpflichtende HA-Sensoren beibehalten

- Dafür: Ein Wechselrichter könnte seine Grenze zur Laufzeit dynamisch melden.
- Dagegen: Die konkrete Anlage stellt diese Werte nicht als Sensorvertrag bereit. Die
  Gerätekonfiguration bliebe unnötig von zwei zusätzlichen HA-Entitäten abhängig.

### Option B — zwei direkte Wattwerte in den Add-on-Optionen

- Dafür: Das Formular bildet den tatsächlich gepflegten Wert ab; keine erfundene Entity-ID und
  kein Laufzeitausfall eines statischen Grenzwerts.
- Dagegen: Eine dynamische Reduzierung durch den Wechselrichter erreicht das HEMS nicht über
  diese beiden Felder. Eine solche Anbindung wäre eine neue, ausdrückliche Funktion.

## Entscheidung

Option B. Ein Speicher braucht die beiden Add-on-Felder:

- `available_charge_power_w`
- `available_discharge_power_w`

Beide sind endliche Zahlen ab `0 W` und verpflichtend. Ein Wert `0` sperrt nur die betreffende
Richtung. Ein fehlender, negativer oder nicht endlicher Wert macht den Geräteeintrag ungültig; es
gibt dafür keinen HA- oder internen Laufzeit-Fallback. Neue Formulare starten sicher mit `0 W`,
aber der User kann jede Grenze direkt ändern.

Die Felder `available_charge_power_entity` und `available_discharge_power_entity` werden aus
Manifest, API, Steuerschema, UI, Regelung und aktueller Dokumentation entfernt. Die
Bestands-Statusfelder `max_ladeleistung_w` und `max_entladeleistung_w` spiegeln die konfigurierten
Werte weiterhin. `lade_limit_w` und `entlade_limit_w` enthalten wie bisher die nach Freigaben und
SoC-Grenzen wirksamen Werte.

SoC-Taper, Notstromreserve, Entlade-Sofort-Schwelle und die beiden Energy-Pilot-Maximalvorschläge
bleiben entsprechend D-041 entfernt.

## Folgen

- **Positiv:** Die Gerätepflege erwartet an den beiden Stellen Wattwerte statt Entity-IDs und kann
  beispielsweise Laden mit `0 W` deaktivieren, während Entladen mit `1500 W` aktiv bleibt.
- **Positiv:** `limit_sensor` und die Entity-Diagnosen für diese beiden Grenzen entfallen.
- **Negativ:** Bestandsentwürfe mit den beiden `_entity`-Feldern müssen auf `_w` migriert werden.
- **Aufwand:** Manifest, Backend, Frontend, Tests, Dokumentation und das eingecheckte Bundle werden
  gemeinsam geändert.

## Rücknahmebedingung

Soll eine dynamische Wechselrichtergrenze wieder einfließen, braucht sie einen neuen, eindeutig
benannten Vertrag mit dokumentiertem Vorrang gegenüber den statischen Sicherheitsgrenzen. Die
beiden `_w`-Felder dürfen nicht still wieder als Entity-IDs interpretiert werden.
