# Vertrag: SkytechHEMS ↔ Skytech HEMS Wallbox Provider

**Version:** 1.1

**Status:** Entwurf für V1; einzelne Punkte sind je Abschnitt gekennzeichnet

**Stand:** 07.10.2026

**Gültig ab:** Implementierung des ersten Providers `go-e Charger Gemini 11 kW`

### Statuskennzeichnung

| Kennzeichen | Bedeutung |
|---|---|
| **Entwurf** | Vereinbart, aber noch nicht implementiert. Ein Plan oder eine Doku-Änderung implementiert keine Schnittstelle. |
| **Implementiert** | In der genannten Gegenstelle umgesetzt und getestet. |
| **Bekannte Grenze** | Bewusst nicht gelöst; wird nicht als Zusage gelesen. |

Zum Stand dieser Fassung ist ausschließlich die HEMS-Schreibreihenfolge für Phase und Strom
**implementiert** (SkytechHEMS `23856d8`). Der Provider und das HEMS-Lebenszeichen sind **Entwurf**.
Die Registerebene des go-e-Geräts gehört nicht in diesen Vertrag; sie steht im Plan des Providers.

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
| `<min_a>` / `<max_a>` | HEMS `technical_minimum` und `technical_maximum` (Ampere-Modus), zusätzlich begrenzt durch die vom Adapter gemeldete Geräteobergrenze. |
| `A` | ganze Ampere |
| `W` | Watt |
| `V` | Volt |

`<hems_prefix>` und `<provider_prefix>` sind bewusst unabhängig. Die Pflege einer eindeutigen,
zueinander passenden Zuordnung (kein doppelt verwendetes Präfix, Umbenennungen) liegt beim
Anwender; der Provider prüft sie nicht (**Bekannte Grenze**). Der Provider erhält
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

`phase_switch_delay_s` ist der Add-on-Konfigurationsschlüssel; der zugehörige HA-Helfer heißt
`input_number.ems_<hems_prefix>_min_umschaltzeit_s`. Beide meinen dieselbe Sperrzeit zwischen
Phasenwechseln.

Die technischen Grenzen und Regelzeiten sind HEMS-Konfiguration. Der Provider darf sie nicht
durch Schreiben an HEMS-Helfer verändern. Er validiert sie zusätzlich gegen die realen
Gerätefähigkeiten.

## HEMS → Provider: Sollwerthelfer

Der Provider liest nur diese HEMS-Entities; er legt sie nicht an und schreibt sie nie.

| Entity | Pflicht | Typ und gültige Werte | Semantik |
|---|---:|---|---|
| `input_number.ems_<hems_prefix>_anforderung_leistung_a` | ja | ganze Zahl: `0` oder `<min_a>..<max_a>` | Gewünschter Ladestrom. `0` bedeutet: Laden sicher unterbinden. Ein positiver Wert bedeutet: Laden mit diesem Strom erlauben, soweit Fahrzeug und Wallbox es zulassen. |
| `input_number.ems_<hems_prefix>_anzahl_phase` | nur bei HEMS `phases: "1,3"` (Phasenbetrieb `automatisch`) | `1` oder `3` | Vom HEMS gewünschte Phasenzahl. Es ist ein Sollwert, nicht die Rückmeldung der tatsächlich geschalteten Phasen. |

SkytechHEMS schreibt die Phasenzahl vor dem Stromsollwert, wenn sich beides im selben Zyklus
ändert, und schreibt bei **jedem** Phasenwechsel den Stromsollwert im selben Zyklus mit, auch
innerhalb von Totband und Rampe. **Implementiert** (SkytechHEMS `23856d8`; früher blieb der Strom
bei kleinen Änderungen unverändert). Beides sind getrennte HA-Aufrufe, keine atomare Transaktion
(**Bekannte Grenze**): Scheitert der Stromwert nach erfolgreicher Phase, bleibt kurz der alte Strom
mit der neuen Phasenzahl stehen. Der Provider schreibt den aktuellen Schnappschuss ohnehin
wiederholt (siehe [Befehlsausführung](#befehlsausführung-im-provider)) und begrenzt den Zeitraum so.

### Phasenbetrieb

Der Provider kennt die Phasenbetriebsart über seine eigene Konfiguration `phasenbetrieb`, nie
durch Rückschluss aus einem fehlenden Helfer. Status: **Entwurf**.

| Wert | HEMS-Seite | Verhalten des Providers |
|---|---|---|
| `automatisch` | `phases: "1,3"`, Phasenhelfer ist Pflicht | Wertet den Phasenhelfer aus und schaltet den Phasenmodus der Wallbox. |
| `fest_1`, `fest_3` | `phases: "1"` beziehungsweise `"3"` | Schaltet nie; der eingestellte Phasenmodus der Wallbox bleibt unverändert. Ein vorhandener Phasenhelfer wird ignoriert. |

### Validierung und sicherer Fall

Status: **Entwurf**.

- `unknown`, `unavailable`, fehlende, nicht-endliche oder nicht-ganzzahlige Werte sind ungültig.
- `1..5 A`, negative Werte sowie Werte oberhalb der vom Adapter gemeldeten Obergrenze sind
  ungültig.
- Bei einem ungültigen Stromsollwert darf der Provider ihn nie auf einen anderen positiven Wert
  runden oder hochsetzen. Er verwirft den Befehl, meldet den Fehler und unterbindet das Laden,
  soweit die Wallbox erreichbar ist.
- Bei `phasenbetrieb: automatisch` und fehlender oder ungültiger Phasenanzahl (nicht `1` oder `3`)
  gilt der gesamte Schnappschuss als ungültig: Laden unterbinden, Fehler melden, keine
  Phasenumschaltung. Ein positiver Strom wird nie zusammen mit einer unbekannten Phasenzahl
  angewendet.
- Nach Provider- oder Wallbox-Neustart liest der Provider den aktuellen HEMS-Schnappschuss erneut
  und synchronisiert ihn. Er darf keinen alten, nur im Arbeitsspeicher befindlichen Sollwert
  voraussetzen. Ein positiver Sollwert wird erst nach einem frischen HEMS-Zyklus angewendet
  (siehe [HEMS-Lebenszeichen](#hems-lebenszeichen)).

## HEMS-Lebenszeichen

Status: **Entwurf** — weder im HEMS noch im Provider implementiert. Entität, Attribute und Frisch-Regel
sind im Vertrag HEMS ↔ Battery-Provider identisch; nur die Reaktion bei nicht frischem
Lebenszeichen ist gerätespezifisch.

Ein unverändert bleibender Sollwert ist normaler Betrieb. Ein HEMS-Ausfall ist deshalb nicht am
Alter eines Sollwerthelfers erkennbar. Das HEMS veröffentlicht stattdessen in jedem Zyklus eine
eigene Statusentität:

```
POST {HA_URL}/api/states/sensor.skytech_hems_status
```

| Feld | Typ | Bedeutung |
|---|---|---|
| `state` | Zahl als Text | Zyklus-Zähler; wird in jedem Zyklus verändert (Überlauf erlaubt). |
| `attributes.zyklus_zaehler` | Ganzzahl | Gleicher Wert wie `state`. |
| `attributes.zyklus_intervall_s` | Zahl > 0 | Aktuell konfigurierte Zykluslänge des HEMS in Sekunden. |
| `attributes.erzeugt_am` | Text | `TT.MM.JJJJ hh:mm:ss`, Berliner Zeit; nur Anzeige, nicht zur Auswertung. |
| `attributes.vertrag_version` | Ganzzahl | `1`. Unbekannte zusätzliche Attribute ignoriert der Provider. |

Das HEMS aktualisiert die Entität in jedem Zyklus, auch bei deaktivierter PV-Regelung. Wie bei der
Flow-Card-Entität überlebt ein per `POST /api/states` angelegter Sensor keinen HA-Neustart; sein
Fehlen bedeutet "kein frischer Zyklus".

**Auswertung im Provider** (nur bei `hems_steuerung_aktiv` = an):

- Der Provider misst mit seiner **eigenen** Uhr, wann er zuletzt eine Änderung von
  `zyklus_zaehler` gesehen hat. Er wertet weder `erzeugt_am` noch die Uhr des HEMS aus.
- Das Lebenszeichen gilt als **frisch**, solange die letzte gesehene Änderung höchstens
  `hems_timeout_faktor × zyklus_intervall_s` zurückliegt. `hems_timeout_faktor` ist eine
  Provider-Option (Standard `3`, zulässig `2..10`). Fehlt `zyklus_intervall_s` oder ist ungültig,
  gilt ein fester Wert von `90 s`.
- Ist die Entität nicht vorhanden, `unknown` oder `unavailable`, ist das Lebenszeichen nicht frisch.
- **Nicht frisch:** Der Provider wendet **keinen** positiven Sollwert an und setzt die Wallbox auf
  Stopp (siehe Abschnitt Befehlsausführung). Sobald ein frisches Lebenszeichen vorliegt, wird der
  aktuelle Schnappschuss automatisch angewendet.
- **Nach Start des Providers** (Neustart, Neuladen, Entry-Setup) gilt das Lebenszeichen erst als
  frisch, nachdem der Provider **nach seinem Start** eine Änderung von `zyklus_zaehler` gesehen hat.
  Ein wiederhergestellter oder alter Wert löst keinen Ladestart aus.
- Im Modus `manuell` wird das Lebenszeichen nicht ausgewertet.

`binary_sensor.<provider_prefix>_hems_lebenszeichen` bildet diesen Zustand ab (an = frisch).

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
| `binary_sensor.<provider_prefix>_hems_lebenszeichen` | – | nur mit HEMS-Anbindung | Diagnose | An = frisches HEMS-Lebenszeichen (siehe [HEMS-Lebenszeichen](#hems-lebenszeichen)). **Entwurf.** |
| `switch.<provider_prefix>_hems_steuerung_aktiv` | – | nur mit HEMS-Anbindung | Steuerung | Betriebsart `HEMS` (an) oder `manuell` (aus). Siehe [Betriebsart](#betriebsart-hems-und-manuell). Standard nach Neustart: an. |

Die Tabelle beschreibt den Soll-Umfang des Providers (**Entwurf**). Für alle Messwerte gilt: Ein fehlender Messwert ist nicht `0`. Bei Kommunikationsfehlern wird
die Provider-Entity nicht verfügbar; sie darf keine geschätzte Leistung veröffentlichen.

## Betriebsart HEMS und manuell

Status: **Entwurf**.

`switch.<provider_prefix>_hems_steuerung_aktiv` (Anzeigename "HEMS Steuerung") wählt, woher der
Provider seinen Sollwert nimmt:

| Schalter | Betriebsart | Quelle des Sollwerts |
|---|---|---|
| an | `HEMS` | Die zwei HEMS-Sollwerthelfer, nur bei frischem Lebenszeichen. |
| aus | `manuell` | Die manuellen Provider-Entities (siehe unten). HEMS-Helfer und Lebenszeichen werden nicht ausgewertet. |

Manuelle Entities (Standardwerte beim Anlegen: Strom `0`, Phasen `1`):

| Entity | Werte | Bedeutung |
|---|---|---|
| `number.<provider_prefix>_manueller_ladestrom` | `0` oder `<min_a>..<max_a>` (Gerätegrenze), ganze Ampere | Gewünschter Ladestrom. `0` = Laden unterbinden. Gleiche Validierung wie beim HEMS-Sollwert. |
| `select.<provider_prefix>_manuelle_phasenanzahl` | `1`, `3` | Gewünschte Phasenzahl; nur bei `phasenbetrieb: automatisch`. |

- Beim Umschalten auf `manuell` wird der Wert der manuellen Entities sofort angewendet, das heißt
  bei Standardwert `0` stoppt das Laden. Beim Umschalten auf `HEMS` wird sofort der aktuelle
  HEMS-Schnappschuss synchronisiert, sofern das Lebenszeichen frisch ist, sonst gilt Stopp.
- Ohne HEMS-Anbindung (leeres `hems_entity_prefix`) existieren der Schalter und die
  HEMS-Sollwert-Entities nicht; die Betriebsart ist dauerhaft `manuell` und die manuellen
  Entities sind vorhanden.
- Ein Schalter aus pausiert die automatische Übersetzung vollständig. Auch die HEMS-Notabschaltung
  übersteuert die Betriebsart `manuell` **nicht** (**Bekannte Grenze**, bewusst so entschieden).

## Befehlsausführung im Provider

Status: **Entwurf**.

Der Provider serialisiert jeden einzelnen Transportzugriff (Lesen oder Schreiben) über eine Sperre.
Es gibt keine Bestätigungswartezeit unter dieser Sperre, ein Stopp wartet deshalb höchstens auf den
gerade laufenden Einzelzugriff. Vor jedem Einzelschritt prüft der Provider den aktuellen
Schnappschuss neu; wird er zu Stopp, entfallen alle noch ausstehenden positiven Schritte. Ein
Schreibfehler darf nicht durch einen parallel laufenden Poll verdeckt werden.

Der Provider arbeitet mit dem **wirksamen Sollwert**: Betriebsart `manuell` → manuelle Entities;
Betriebsart `HEMS` → HEMS-Schnappschuss bei frischem Lebenszeichen, sonst Stopp.

| Wirksamer Sollwert | Befehlsfolge an die Wallbox |
|---|---|
| `0 A`, ungültiger Sollwert oder nicht frisches Lebenszeichen | Laden unterbinden: Freigabe auf **Aus** (go-e `frc` = 1). Der gespeicherte Ladestrom bleibt unverändert. |
| Positiver, gültiger Strom, Phasenzahl unverändert | Ladestrom setzen, danach Freigabe auf **Ein** (`frc` = 2). |
| Positiver, gültiger Strom, geänderte Phasenzahl (nur `automatisch`) | Phasenmodus setzen, danach Ladestrom setzen, danach Freigabe auf **Ein**. Die Schritte werden ohne Zwischenwert und ohne Bestätigung der aktiven Phasen aufeinander folgend ausgeführt ("durchreichen"). |

- Erfolg bedeutet: Der Herstellertransport hat jeden Schritt bestätigt. Die `hems_soll_*`-Entities
  zeigen nur einen erfolgreich gesendeten Wert, nie einen bloß geplanten. Im Stoppzustand wegen
  fehlendem Lebenszeichen zeigen sie `0`.
- Der Provider löst keinen zusätzlichen Stop-/Start-Zyklus für den Phasenwechsel aus. Die kurze
  Unterbrechung, die der Ladepunkt beim physischen Umschalten selbst braucht, ist nicht vermeidbar.
- Der Provider **überwacht** die tatsächlich aktiven Phasen (`aktuelle_phasenanzahl`), prüft sie
  aber nicht als Voraussetzung für den Strom. Eine Abweichung zwischen gewünschter und aktiver
  Phasenzahl bei geschlossenem Schütz ist nur Diagnose (**Bekannte Grenze**).
- **Erneutes Schreiben:** Der Provider schreibt den wirksamen Sollwert alle `keepalive_s` Sekunden
  erneut (Provider-Option, Standard `30`, zulässig `5..300`), unabhängig von Änderungen. Dasselbe
  gilt nach einem Schreibfehler: der Fehler bleibt sichtbar, bis ein Schreibvorgang gelingt, auch
  wenn Polls erfolgreich sind. Ein Stopp hat bei jedem Versuch Vorrang vor positiven Schritten.
- **Kommunikationsstörung:** Nach einer vorübergehenden Störung nimmt der Provider den wirksamen
  Sollwert automatisch wieder auf, ohne Quittierung; ein Phasenwechsel-Fehler wird getrennt als
  Gerätefehler gemeldet und ebenfalls ohne Quittierung durch den nächsten Schreibversuch erneut
  versucht.
- Mit dem Wirksamwerden des Lebenszeichens (Neustart, Ausfall des HEMS) wird nach frischem Zyklus
  automatisch der aktuelle Schnappschuss angewendet.

Die Schrittfolge für Strom und Phase ist keine Transaktion. Scheitert ein Schritt, gilt der Befehl
als nicht erfolgreich und wird beim nächsten Schreibversuch vollständig wiederholt.

Die Freigabe über `frc` = 2 ("Ein") lässt den Ladevorgang unabhängig von der Zugangskontrolle des
Geräts zu. V1 setzt deshalb voraus, dass keine RFID-Autorisierung genutzt wird (siehe unten).
Ein späterer optionaler RFID-Betrieb ist **Entwurf für eine Folgeversion**: Der Provider soll dann
die erkannte RFID-Karte als HA-Ereignis veröffentlichen; Änderungen daran sind additiv.

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
| Notabschaltung | schreibt den HEMS-Sollwert auf `0 A` | setzt `0 A` bei Betriebsart `HEMS` sicher um; bei `manuell` nicht (Bekannte Grenze) |
| HEMS-Lebenszeichen | veröffentlicht `sensor.skytech_hems_status` je Zyklus | wertet es aus und stoppt bei Ausbleiben (Entwurf) |
| Ungültige Istleistung des Providers | setzt den Sollwert auf `0 A` (Entwurf, siehe unten) | veröffentlicht `unavailable` |

V1 setzt voraus, dass keine konkurrierende herstellereigene Überschuss-, Zeitplan-, OCPP- oder
Fremdsteuerung die vom Provider gesteuerten Ladefreigaben überschreibt; es steuert ausschließlich
das HEMS. RFID und sonstige Zugangskontrolle werden in V1 nicht genutzt und vom Provider nicht
verändert.

### Ungültige Istleistung (Entwurf)

Wie beim Battery-Provider gilt: Ist `sensor.<provider_prefix>_istleistung` ungültig oder nicht
verfügbar, setzt das HEMS den Sollwert des Gerätes auf `0 A`, soweit es seine Ausgabehelfer
schreiben kann. Das ist eine **Änderung der HEMS-Geräteklasse `controllable` im Ampere-Modus** und
im HEMS noch nicht umgesetzt. Bis dahin rechnet das HEMS bei ungültiger Istleistung intern mit
`0 W` und sperrt das Gerät nicht (**Bekannte Grenze**).

### Weitere bekannte Grenzen

| Fall | Grenze |
|---|---|
| Vollständiger Verbindungsverlust zur Wallbox | Der Provider kann keinen Stopp zustellen. Ein physischer Stopp ist ohne erreichbaren Transport nicht garantiert; eine geräteseitige Ausfallfunktion wird nicht genutzt. |
| Strom und Phase | Keine gemeinsame Transaktion, siehe oben. |
| Umschaltsperre | Das HEMS begrenzt wiederholtes Umschalten über `min_umschaltzeit_s`. Die Sperre gilt nicht gleichermaßen für jeden Ladestart, und der interne Zeitstempel überlebt keinen HEMS-Neustart. Der Provider ergänzt keine eigene Umschaltsperre. |
| Geräteidentität | Die Zuordnung `<hems_prefix>` ↔ Provider und die Eindeutigkeit der Provider-Instanzen pflegt der Anwender. |

## Kompatibilität und Änderungen

Die Version `1.1` ergänzt Betriebsart, Lebenszeichen, Phasenbetrieb und Statuskennzeichnung
gegenüber `1.0`, die nur ein Entwurf ohne Implementierung war; es entsteht dadurch keine
Inkompatibilität. Dokumentversion ist keine zur Laufzeit übertragene Protokollversion.

Der Vertrag wächst additiv: neue optionale Diagnose-Entities oder optionale Provider-Fähigkeiten
brechen V1 nicht. Das Entfernen, Umbenennen oder die Bedeutungsänderung einer verpflichtenden
Entity, ihrer Einheit oder ihrer Sicherheitssemantik ist eine inkompatible Vertragsänderung und
erfordert eine neue Vertragsversion sowie die gemeinsame Anpassung beider Kopien.
