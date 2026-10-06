# Vertrag: SkytechHEMS ↔ Skytech HEMS Wallbox Provider

**Version:** 1.0

**Status:** Entwurf für V1

**Gültig ab:** Implementierung des ersten Providers `go-e Charger Gemini 11 kW`

Dieser Vertrag beschreibt ausschließlich den Austausch zwischen SkytechHEMS und einer
Wallbox-Provider-Integration in Home Assistant. Herstellerprotokolle, Register, MQTT-Topics
und App-Einstellungen sind ausdrücklich nicht Teil dieses Vertrags.

Die Datei liegt wortgleich in beiden Repositories. Bei einer Änderung müssen beide Kopien im
selben Arbeitspaket angepasst werden.

## Zweck und Architekturgrenze

SkytechHEMS bleibt die alleinige Instanz für die Überschussberechnung, Priorisierung,
Rampenbegrenzung, Freigaben und Phasenentscheidung. Es schreibt nur seine eigenen
`input_*`-Helfer und greift niemals direkt auf eine Wallbox zu.

Der Wallbox-Provider beobachtet diese Helfer, übersetzt sie in die herstellerspezifische
Ansteuerung und stellt Mess- und Diagnose-Entities bereit. Er verändert weder die
HEMS-Sollwerthelfer noch die HEMS-Freigaben, Prioritäten oder Regelparameter.

Für V1 verwendet SkytechHEMS unverändert die Geräteklasse `controllable` im
Ampere-Modus. Eine eigene HEMS-Geräteklasse `wallbox` ist nicht Teil dieses Vertrags.

```text
SkytechHEMS ── Sollwerte über input_* ──► Wallbox-Provider ──► Wallbox
SkytechHEMS ◄── Messwerte über sensor.* ─ Wallbox-Provider ◄── Wallbox
```

## Bezeichner

| Platzhalter | Bedeutung |
|---|---|
| `<hems_prefix>` | `devices[].entity_prefix` der HEMS-Gerätekonfiguration; fehlt er, ist es `devices[].name`. Beispiel: `wallbox`. |
| `<provider_prefix>` | Entity-Präfix der Provider-Instanz, aus ihrem Anzeigenamen abgeleitet. Beispiel: `go_e_garage`. |
| `A` | ganze Ampere |
| `W` | Watt |
| `V` | Volt |

`<hems_prefix>` und `<provider_prefix>` sind bewusst unabhängig. Der Provider erhält
`<hems_prefix>` als optionale Konfiguration `hems_entity_prefix`. Leer bedeutet: keine
SkytechHEMS-Anbindung; der Provider liefert dann nur seine eigenen Entities.

## HEMS-Konfiguration

Für eine go-e Gemini 11-kW-Instanz wird das HEMS wie folgt konfiguriert. Die
`sensor.*`-Namen rechts stammen aus einer Provider-Instanz mit dem Präfix
`go_e_garage` und sind nur ein Beispiel.

```yaml
- name: wallbox_1
  label: Wallbox
  class: controllable
  entity_prefix: wallbox
  actual_power_entity: sensor.go_e_garage_istleistung
  output_unit: ampere
  phases: "1,3"
  phase_switch_delay_s: 300
  voltage_l1_entity: sensor.go_e_garage_spannung_l1
  voltage_l2_entity: sensor.go_e_garage_spannung_l2
  voltage_l3_entity: sensor.go_e_garage_spannung_l3
  technical_minimum: 6
  technical_maximum: 16
  increase_delay_s: 60
  decrease_delay_s: 60
  maximum_step_change: 2
  minimum_step_change: 1
```

Die technischen Grenzen und Regelzeiten sind HEMS-Konfiguration. Der Provider darf sie nicht
durch Schreiben an HEMS-Helfer verändern. Er validiert sie zusätzlich gegen die realen
Gerätefähigkeiten.

## HEMS → Provider: Sollwerthelfer

Der Provider liest nur diese HEMS-Entities; er legt sie nicht an und schreibt sie nie.

| Entity | Pflicht | Typ und gültige Werte | Semantik |
|---|---:|---|---|
| `input_number.ems_<hems_prefix>_anforderung_leistung_a` | ja | ganze Zahl: `0` oder `min_current_a..max_current_a` | Gewünschter Ladestrom. `0` bedeutet: Laden sicher unterbinden. Ein positiver Wert bedeutet: Laden mit diesem Strom erlauben, soweit Fahrzeug und Wallbox es zulassen. |
| `input_number.ems_<hems_prefix>_anzahl_phase` | nur bei HEMS `phases: "1,3"` | `1` oder `3` | Vom HEMS gewünschte Phasenzahl. Es ist ein Sollwert, nicht die Rückmeldung der tatsächlich geschalteten Phasen. |

SkytechHEMS schreibt die Phasenzahl vor dem Stromsollwert, wenn sich beides im selben Zyklus
ändert. Das ist nur eine bevorzugte Reihenfolge, keine atomare Transaktion. Der Provider muss
beide Entities beobachten, Änderungen kurz bündeln und anschließend einen konsistenten
Schnappschuss anwenden.

### Validierung und sicherer Fall

- `unknown`, `unavailable`, fehlende, nicht-endliche oder nicht-ganzzahlige Werte sind ungültig.
- `1..5 A`, negative Werte sowie Werte oberhalb der vom Adapter gemeldeten Obergrenze sind
  ungültig.
- Bei einem ungültigen Stromsollwert darf der Provider ihn nie auf einen anderen positiven Wert
  runden oder hochsetzen. Er verwirft den Befehl, meldet den Fehler und unterbindet das Laden,
  soweit die Wallbox erreichbar ist.
- Bei fehlender oder ungültiger Phasenanzahl darf keine Phasenumschaltung erfolgen. Der Provider
  behält die letzte bestätigte Phasenanzahl bei und wendet nur dann einen neuen Stromsollwert an,
  wenn dies sicher möglich ist.
- Nach Provider- oder Wallbox-Neustart liest der Provider den aktuellen HEMS-Schnappschuss erneut
  und synchronisiert ihn. Er darf keinen alten, nur im Arbeitsspeicher befindlichen Sollwert
  voraussetzen.

## Provider → HEMS: Messwerte

Der Provider stellt die folgenden Entities je Instanz bereit. SkytechHEMS konsumiert in V1 die
erste Zeile zwingend und die drei Spannungen, wenn sie in `devices[]` eingetragen sind.

| Entity | Einheit | Pflicht Provider | HEMS-Verwendung | Semantik |
|---|---:|---:|---|---|
| `sensor.<provider_prefix>_istleistung` | W | ja | ja | Tatsächlich an der Wallbox aufgenommene Gesamtwirkleistung. Positiv; `0` ist ein gültiger Messwert. |
| `sensor.<provider_prefix>_spannung_l1` | V | ja | optional | Gemessene Spannung L1. |
| `sensor.<provider_prefix>_spannung_l2` | V | ja | optional | Gemessene Spannung L2. |
| `sensor.<provider_prefix>_spannung_l3` | V | ja | optional | Gemessene Spannung L3. |
| `sensor.<provider_prefix>_aktuelle_phasenanzahl` | – | ja | Diagnose | Tatsächlich hinter dem Schütz aktive Phasenzahl. Sie ersetzt nicht den HEMS-Sollwerthelfer. |
| `sensor.<provider_prefix>_hems_soll_ladestrom` | A | nur mit HEMS-Anbindung | Diagnose | Zuletzt erfolgreich an die Wallbox gesendeter HEMS-Stromsollwert. Bis zum ersten Erfolg und nach einem Schreibfehler nicht verfügbar. |
| `sensor.<provider_prefix>_hems_soll_phasenanzahl` | – | nur mit HEMS-Anbindung und Phasenwechsel | Diagnose | Zuletzt erfolgreich angeforderte Phasenzahl. Sie wird erst nach bestätigter Umschaltung aktualisiert. |
| `binary_sensor.<provider_prefix>_fahrzeug_verbunden` | – | ja | Diagnose | Ein Fahrzeug ist angeschlossen beziehungsweise vom Ladepunkt erkannt. |
| `binary_sensor.<provider_prefix>_laedt` | – | ja | Diagnose | Das Fahrzeug bezieht tatsächlich Energie. |
| `sensor.<provider_prefix>_wallbox_status` | – | ja | Diagnose | Normalisierter Ladepunktstatus. |
| `sensor.<provider_prefix>_fehler` | – | ja | Diagnose | Normalisierter Gerätefehler; kein Fehler ist ein gültiger, expliziter Zustand. |
| `sensor.<provider_prefix>_ladestrom_l1`, `_l2`, `_l3` | A | ja | Diagnose | Gemessener Strom je Phase. |
| `sensor.<provider_prefix>_ladeenergie_sitzung` | Wh | ja | Anzeige | Energie des laufenden beziehungsweise letzten Ladevorgangs. |
| `sensor.<provider_prefix>_ladeenergie_gesamt` | Wh | ja | Anzeige | Lebensdauerzähler der Wallbox. |
| `switch.<provider_prefix>_hems_steuerung_aktiv` | – | nur mit HEMS-Anbindung | Steuerung | Aktiviert oder pausiert ausschließlich die automatische Übersetzung der beiden HEMS-Sollwerthelfer. Standard nach Neustart: aktiv. |

Für alle Messwerte gilt: Ein fehlender Messwert ist nicht `0`. Bei Kommunikationsfehlern wird
die Provider-Entity nicht verfügbar; sie darf keine geschätzte Leistung veröffentlichen.

## Befehlsausführung im Provider

Der Provider serialisiert Polling, HEMS-Synchronisierung und manuelle Befehle über eine gemeinsame
Sperre. Ein Schreibfehler darf nicht durch einen parallel laufenden Poll verdeckt werden.

Bei unveränderter gewünschter Phasenzahl gilt:

1. `0 A`: Ladefreigabe sicher zurücknehmen.
2. Positiver, gültiger Sollwert: Ladestrom setzen und gemäß konfigurierter Steuerpolitik
   freigeben.
3. Erfolg bedeutet mindestens: Der Herstellertransport hat die Änderung bestätigt. Die
   `hems_soll_*`-Entities dürfen keinen bloß geplanten Wert zeigen.

Bei geänderter gewünschter Phasenzahl gilt:

1. Strom- und Phasenwert gemeinsam einlesen und weitere Änderungen bis zum Abschluss sammeln.
2. Den Strom für den Übergang auf einen sicheren Wert begrenzen; die Wallbox nicht durch einen
   zusätzlichen externen Stop-/Start-Zyklus unterbrechen.
3. Den herstellerspezifischen Phasenwechsel anfordern und die tatsächlich geschalteten Phasen
   prüfen.
4. Erst nach bestätigtem Wechsel den neuen Stromsollwert anwenden.
5. Bei Timeout oder Fehler: weiteren Stromanstieg verhindern, sicheren Ladezustand herstellen,
   Fehler veröffentlichen und keinen Phasenwechsel als erfolgreich melden.

Die kurze Unterbrechung im Leistungspfad, die ein AC-Ladepunkt beim physischen Umschalten selbst
benötigt, ist nicht vermeidbar. Der Provider löst jedoch keinen zusätzlichen `force off`-Zyklus
aus. SkytechHEMS verhindert wiederholtes Umschalten bereits über
`min_umschaltzeit_s`; der Provider ergänzt nur die gerätespezifische Bestätigung und Fehlerbehandlung.

## Zuständigkeiten und Nicht-Ziele

| Thema | SkytechHEMS | Wallbox-Provider |
|---|---|---|
| PV-Überschuss, Netzbezug, Prioritäten, Rampen | entscheidet | konsumiert nicht |
| Technische Mindest- und Höchstwerte in der Regelung | konfiguriert und nutzt | validiert gegen reale Hardware |
| Schreiben der HEMS-`input_*`-Helfer | ausschließlich | nie |
| Herstellerprotokoll und Wallboxzugriff | nie | ausschließlich |
| Istleistung, Spannungen, Status und Fehler | liest als HA-Entities | ermittelt und veröffentlicht |
| Freigabe an der realen Wallbox | indirekt durch Sollwert | übersetzt und bestätigt |
| RFID, Nutzerverwaltung, Scheduler, Tarif- und PV-Funktion der Hersteller-App | konfiguriert nicht | verändert in V1 nicht |
| Notabschaltung | schreibt den HEMS-Sollwert auf `0 A` | setzt `0 A` sicher auf die reale Wallbox um |

V1 setzt voraus, dass keine konkurrierende herstellereigene Überschuss-, Zeitplan- oder
Fremdsteuerung die vom Provider gesteuerten Ladefreigaben überschreibt. RFID und sonstige
Zugangskontrolle bleiben unangetastet. Das konkrete Zusammenspiel der go-e-Freigabe mit RFID wird
vor dem produktiven Betrieb an Hardware geprüft und dokumentiert.

## Kompatibilität und Änderungen

Der Vertrag wächst additiv: neue optionale Diagnose-Entities oder optionale Provider-Fähigkeiten
brechen V1 nicht. Das Entfernen, Umbenennen oder die Bedeutungsänderung einer verpflichtenden
Entity, ihrer Einheit oder ihrer Sicherheitssemantik ist eine inkompatible Vertragsänderung und
erfordert eine neue Vertragsversion sowie die gemeinsame Anpassung beider Kopien.
