# Vertrag: SkytechHEMS ↔ Skytech HEMS Battery Provider

**Version:** 2.0

**Status:** Dokumentierter Implementierungsstand mit bekannten Betriebsgrenzen; je Einheit eine Schnittstellen-Entität (`sensor.hems_schnittstelle`, `sensor.battery_provider_schnittstelle`) in beiden Projekten **implementiert**; Marstek-Freigaben aus dem Soll/Ist-Vergleich des Providers mit HEMS-Istwerten **implementiert**; E3DC-Statusbits an Hardware **noch nicht negativ getestet** (bekannte Grenze)

**Stand:** 20.10.2026

**Geprüfte Codebasis:** SkytechHEMS `e5c0156`, Skytech-HEMS-Battery-Provider `12ae0f3`; Lebenszeichen: SkytechHEMS `f2037f4` (D-062), Battery-Provider D-016; Schnittstellen-Entitäten: SkytechHEMS D-069, Battery-Provider D-019 (lösen D-068/D-017 ab); Soll/Ist-Vergleich Marstek: Battery-Provider D-018/D-019.

Dieser Vertrag beschreibt den vorhandenen Austausch über Home Assistant. Er führt keine neue
Steuerungslogik ein. Bekannte Einschränkungen sind ausdrücklich dokumentiert und dürfen nicht
als bereits erfüllte Sicherheits- oder Kompatibilitätszusagen gelesen werden.

Die Datei liegt wortgleich in beiden Repositories unter
`contract/contract_hems_battery_provider/contract_hems_battery_provider.md`. Änderungen am
Austausch müssen in beiden Kopien im selben Arbeitspaket dokumentiert werden. Projektregeln
bleiben übergeordnet; für die Schnittstellenbeschreibung ist dieser Vertrag maßgeblich.

## Zweck und Architekturgrenze

SkytechHEMS regelt Speicher als `class: battery`. Es entscheidet über Lade-/Entladeleistung,
Prioritäten, SoC-Grenzen, Freigaben, Rampen und Richtungswechsel. Der Provider ist die
Home-Assistant-Custom-Integration `battery_bridge` und übersetzt die HEMS-Ausgabehelfer in
Adapteraufrufe. Aktuell existieren Marstek-UDP- und E3DC-RSCP-Adapter.

```text
SkytechHEMS ── zwei input_*-Ausgabehelfer (Sollwerte) ──────────► HA ──► Battery-Provider ──► Speicher
SkytechHEMS ── sensor.hems_schnittstelle (Lebenszeichen, Istwerte) ► HA ──► Battery-Provider
SkytechHEMS ◄── sensor.battery_provider_schnittstelle (Freigaben) ── HA ◄── Battery-Provider ◄── Speicher
SkytechHEMS ◄── SoC und Istleistungen (eigene konfigurierte Sensoren) ── HA
```

**Grundsatz (seit 2.0):** Jede Einheit veröffentlicht genau eine Entität
`sensor.<einheit>_schnittstelle`, die alle Informationen für alle anderen Teilnehmer enthält.
Sollwerte laufen weiter über die Ausgabehelfer, Messwerte liest das HEMS aus seinen eigenen
konfigurierten Sensoren.

Es gibt keinen direkten REST-Aufruf zwischen HEMS und Provider. Die Integration berechnet
keinen PV-Überschuss, ändert keine HEMS-Prioritäten und schreibt keine HEMS-Helfer zurück.
Herstellerbefehle und Zugangsdaten gehören ausschließlich zur Provider-Konfiguration.

## Bezeichner und Konfiguration

| Bezeichner | Bedeutung |
|---|---|
| `<hems_prefix>` | HEMS `devices[].entity_prefix`, standardmäßig `devices[].name`. |
| `hems_entity_prefix` | Optionale Provider-Konfiguration; muss exakt zum HEMS-Präfix passen. |
| `<provider_prefix>` | Beispielpräfix für Provider-Entities; unabhängig vom HEMS-Präfix. |
| `W`, `%` | Leistung in Watt, SoC in Prozent. |

Bei leerem `hems_entity_prefix` gibt es keine automatische HEMS-Bridge. Messsensoren und
manuelle Number-Entities bleiben vorhanden. Mit Präfix entstehen zusätzlich HEMS-Sollsensoren
und der Schalter für die automatische Steuerung.

Die tatsächlichen Entity-IDs werden von HA verwaltet. Übersetzte Anzeigenamen, bereits
vergebene Namen und Umbenennungen können von den Beispielen abweichende IDs ergeben. Für die
HEMS-Konfiguration sind die vorhandenen IDs zu übernehmen; die stabilen internen Entity-Keys
sind in der folgenden Tabelle angegeben.

## Provider → HEMS: Messwerte und Diagnose

| Interner Entity-Key / Plattform | Einheit | Bedeutung | HEMS-Zuordnung |
|---|---|---|---|
| `soc` / `sensor` | % | Gemessener Ladezustand. | `soc_entity` |
| `ist_ladeleistung` / `sensor` | W | Tatsächliche Ladeleistung, nicht negativ. | `charge_power_entity` |
| `ist_entladeleistung` / `sensor` | W | Tatsächliche Entladeleistung, nicht negativ. | `discharge_power_entity` |
| `hems_soll_ladeleistung` / `sensor` | W | Zuletzt von der Bridge erfolgreich an den Adapter übergebene Ladeanforderung. | Diagnose; kein Istwert. |
| `hems_soll_entladeleistung` / `sensor` | W | Zuletzt von der Bridge erfolgreich an den Adapter übergebene Entladeanforderung. | Diagnose; kein Istwert. |
| `soll_ladeleistung` / `number` | W | Manueller Schreibzugang für Laden. | Kein regulärer HEMS-Ausgabeweg. |
| `soll_entladeleistung` / `number` | W | Manueller Schreibzugang für Entladen. | Kein regulärer HEMS-Ausgabeweg. |
| `hems_steuerung_aktiv` / `switch` | – | Pausiert beziehungsweise aktiviert die Bridge. | Nicht vom HEMS automatisch ausgewertet. |

Die drei Messsensoren bilden `StorageState` ab. `None` bedeutet fehlender Messwert, `0` einen
echten Nullwert. Scheitert der Poll oder ist `StorageState.available` falsch, sind Messsensoren
nicht verfügbar. HEMS fährt einen Speicher bei ungültigem SoC oder ungültiger Istleistung auf
`0 W` und `standby`, soweit es seine Ausgabehelfer schreiben kann.

Die HEMS-Sollsensoren hängen dagegen an `HemsCommandState` und `write_ok`, unabhängig vom
Poll-Erfolg. Vor dem ersten erfolgreichen Sync und nach einem behandelten Schreibfehler sind
sie nicht verfügbar. Ein später erfolgreicher Sync stellt ihre Verfügbarkeit wieder her.
Sie tragen `assumed_state`: Erfolg bedeutet keinen unabhängigen Messnachweis der Ausführung.

Die manuellen `number.*`-Werte spiegeln die HEMS-Bridge nicht. Sie zeigen ihren Initialwert
beziehungsweise den zuletzt manuell gesetzten Wert. Auch während einer Pause kann der letzte
erfolgreiche HEMS-Sollsensorwert weiterhin sichtbar sein; er ist kein Lebenszeichen.

## Provider → HEMS: `sensor.battery_provider_schnittstelle`

Status: **Implementiert** — Provider D-019 (`interface.py`), HEMS D-069 (`BatteryDevice`).

Eine Entität für **alle** Speicher des Providers (keine je Speicher). Der Provider schreibt sie
per `hass.states.async_set`; sie ist keine Registry-Entität und steht nach einem HA-Neustart
wieder, sobald der erste Eintrag geladen ist. Ohne Eintrag mit HEMS-Anbindung gibt es sie nicht.

| Feld | Typ | Bedeutung |
|---|---|---|
| `state` | Text | `hems_entity_prefix` aller Provider-Einträge mit HEMS-Anbindung, durch Komma getrennt, z. B. `acspeicher1,e3dc_speicher`. |
| `attributes.schnittstelle_version` | Ganzzahl | `2`. |
| `attributes.<prefix>_ladefreigabe` | Bool | Darf das HEMS diesen Speicher laden? |
| `attributes.<prefix>_entladefreigabe` | Bool | Darf das HEMS diesen Speicher entladen? |
| `attributes.<prefix>_ladesperrgrund` | Text oder `null` | Grund einer Ladesperre, mehrere mit Komma; `null` ohne Sperre. |
| `attributes.<prefix>_entladesperrgrund` | Text oder `null` | Grund einer Entladesperre, mehrere mit Komma; `null` ohne Sperre. |
| `attributes.<prefix>_sperre_bis_soc_prozent` | Zahl | Nur bei einer Sperre aus dem Soll/Ist-Vergleich: Ladezustand, ab dem die Richtung wieder frei ist. Nur Anzeige. |

Sperrgründe: `nicht_erreichbar`, `geraet_laden_gesperrt`, `geraet_entladen_gesperrt`,
`ladesperrzeit`, `entladesperrzeit`, `notstromreserve`, `keine_reaktion_laden`,
`keine_reaktion_entladen`.

Herkunft der Freigaben:

| Fall | Ladefreigabe | Entladefreigabe |
|---|---|---|
| Poll gescheitert, Speicher nicht erreichbar | `false` (`nicht_erreichbar`) | `false` (`nicht_erreichbar`) |
| Marstek UDP | `Bat.GetStatus.charg_flag` (fehlt = frei) und keine Soll/Ist-Sperre | `Bat.GetStatus.dischrg_flag` (fehlt = frei) und keine Soll/Ist-Sperre |
| E3DC RSCP | `EMS_STATUS` Bit 0 (Laden gesperrt) und Bit 5 (Ladesperrzeit) nicht gesetzt | `EMS_STATUS` Bit 1 (Entladen gesperrt) und Bit 6 (Entladesperrzeit) nicht gesetzt, Notstromreserve nicht erreicht |

Die Gerätestatus-Abfragen laufen höchstens alle 15 s. Scheitert nur die Statusabfrage, gilt die
Richtung als frei; der Messwert-Poll bleibt gültig.

**Auswertung im HEMS:** Jeder `class: battery` liest `<entity_prefix>_ladefreigabe` /
`_entladefreigabe`. `false` sperrt die Richtung (Sperrgründe `geraet_laden_gesperrt` /
`geraet_entladen_gesperrt`); eine gesperrte Entladung gibt das Hausdefizit an den nächsten
Speicher nach `entlade_prioritat` weiter. Fehlt die Entität, das Attribut, oder ist der Wert kein
Bool, gilt die Richtung als **frei** (keine Information ist keine Sperre). Die Sperrgründe zeigt
das HEMS in der Statuskarte.

## HEMS → Provider: `sensor.hems_schnittstelle`

Status: **Implementiert** — HEMS D-069 (`app/status_publisher.py`), Provider D-019
(`heartbeat.py`, `hems_bridge.py`, `response_check.py`).

Die Schnittstellen-Entität des HEMS trägt das [Lebenszeichen](#hems-lebenszeichen) und je
Speicher die Istwerte aus den HEMS-Sensoren. Der Provider braucht diese für seinen
Soll/Ist-Vergleich, weil die HEMS-Sensoren schneller sind als die Gerätewerte; mit den langsamen
Gerätewerten würde der Vergleich springen.

| Feld | Typ | Bedeutung |
|---|---|---|
| `state` | Text | `entity_prefix` aller HEMS-Geräte `class: battery`, durch Komma getrennt; leer ohne Speicher. Kein Lebenszeichen. |
| `attributes.zyklus_zaehler`, `zyklus_intervall_s`, `erzeugt_am`, `vertrag_version` | – | Lebenszeichen, siehe dort. `vertrag_version` = `2`. |
| `attributes.<prefix>_ladeleistung` | Zahl ≥ 0 | Gemessene Ladeleistung in W aus den HEMS-Sensoren dieses Zyklus. |
| `attributes.<prefix>_entladeleistung` | Zahl ≥ 0 | Gemessene Entladeleistung in W aus den HEMS-Sensoren dieses Zyklus. |

Hat das HEMS in einem Zyklus keine gültigen Messwerte für einen Speicher (oder misst nicht, z. B.
während der Notabschaltung), fehlen dessen beiden Leistungsattribute.

**Soll/Ist-Vergleich im Provider** (nur Marstek, Provider D-018/D-019): Der Marstek meldet seine
Entladesperre nicht über `dischrg_flag` (Befund 19.10.2026: Flag `true`, Entladung bei 12 % SoC
verweigert). Bei jeder Änderung von `sensor.hems_schnittstelle` vergleicht der Provider den
zuletzt bestätigt gesendeten Sollwert mit den HEMS-Istwerten. Liegt ein Sollwert ab
`response_check_min_request_w` an und bleibt die Ist-Leistung derselben Richtung unter
`response_check_max_actual_w`, summiert er die Zeit über mehrere Anforderungen auf; ab
`response_check_time_seconds` meldet er die Richtung als gesperrt (`keine_reaktion_*`).
Provider-Optionen je Speicher, Defaults 100 W, 20 W, 30 s; Erkennungszeit 0 = aus. Die
Entladesperre fällt bei SoC ≥ Sperr-SoC + 1 %, die Ladesperre bei SoC ≤ Sperr-SoC − 1 %; die
nächste Anforderung wird neu geprüft. **Fehlen die Istwerte, pausiert der Vergleich** — es zählt
keine Fehlzeit, eine bestehende Sperre bleibt.

**Bekannte Grenze:** Ob die RSCP-Bitbelegung von `EMS_STATUS` der E3DC-Modbus-Doku entspricht und
ob der E3DC eine Verweigerung darüber meldet, ist noch nicht negativ getestet; für den E3DC gibt es
keinen Soll/Ist-Vergleich.

## HEMS-Konfiguration

Das HEMS liest SoC und Istleistung aus seinen eigenen konfigurierten Sensoren (`soc_entity` und
genau eine Leistungsvariante). Das können die Messsensoren des Providers sein oder schnellere
Sensoren anderer Herkunft. Die Freigaben findet es ohne Konfiguration über sein `entity_prefix`
in `sensor.battery_provider_schnittstelle`. Das Feld `provider_entity` aus Version 1.2/1.3 entfällt
(eine gespeicherte Bestandsoption wird ignoriert). Beispiel mit angenommenen, vor Ort zu prüfenden
Entity-IDs und beispielhaften Gerätegrenzen:

```yaml
battery_residual_power_entity: sensor.hausleistungsbilanz_fur_ac_speicher
speicher_in_residual_enthalten: true

devices:
  - name: acspeicher1
    label: AC-Speicher
    class: battery
    entity_prefix: acspeicher1
    allowed_modes: "manuell,nur_heizen,nur_laden"
    soc_entity: sensor.marstek_venus1_ladezustand
    charge_power_entity: sensor.marstek_venus1_ist_ladeleistung
    discharge_power_entity: sensor.marstek_venus1_ist_entladeleistung
    available_charge_power_w: 1500
    available_discharge_power_w: 1500
    capacity_kwh: 12.8
    soc_max_hysteresis_percent: 2
    direction_switch_delay_s: 5
```

Im Provider wird dazu `hems_entity_prefix: acspeicher1` hinterlegt. Die Zahlenwerte sind kein
allgemeines Geräteprofil. Beide `available_*_w`-Werte sind endliche, nicht negative statische
HEMS-Konfigurationswerte; sie werden nicht aus Provider-Number-Entities abgeleitet. `0` sperrt
die betreffende Richtung. Die Bilanzkonfiguration muss zur konkreten Messanlage passen.

HEMS benötigt zusätzlich die gemeinsamen Freigaben und seine Ausgabehelfer. Die separate
Hausleistungsbilanz ist für Entladeplanung erforderlich; bei ungültiger Bilanz geht der Speicher
auf `0 W` und `standby`. Der Provider liest diese Bilanz nicht.

HEMS-interne Ersatzwerte ersetzen keine Ausgabehelfer in HA. Die Bridge kann ausschließlich
vorhandene HA-States beobachten.

## HEMS → Provider: Ausgabehelfer

| Entity | Typ / gültige Betriebswerte | Bedeutung |
|---|---|---|
| `input_number.ems_<hems_prefix>_anforderung_leistung_w` | Endlicher signierter Zahlenwert in W; HEMS schreibt auf ganze Watt gerundet. | Positiv laden, negativ entladen, `0` keine angeforderte Leistung. |
| `input_select.ems_<hems_prefix>_anforderung_betriebsart` | `laden`, `entladen`, `standby` | Explizite angeforderte Richtung. |

Beide Helfer müssen vorhanden und verwendbar sein. Der Zahlenhelfer benötigt einen ausreichend
negativen Mindestwert und ausreichend großen Maximalwert; der Auswahlhelfer muss alle drei
Optionen unterstützen. Weder HEMS noch Provider legen diese Helfer automatisch an.

Konsistente Paare sind `laden` mit positivem Wert, `entladen` mit negativem Wert und `standby`
mit `0`. Ein Leistungswert `0` führt auch bei `laden`/`entladen` zu einer Nullanforderung.
Die aktuelle Bridge validiert die Konsistenz des Vorzeichens nicht: Sie verwendet den Betrag
der Leistung und entscheidet die Richtung ausschließlich anhand der Betriebsart.

### Schreibreihenfolge des HEMS

- Bei Start, Richtungswechsel und aktiver Änderung: geänderte Betriebsart zuerst, geänderte
  Leistung danach.
- Bei Standby/Abschaltung: Leistung zuerst, Betriebsart danach.
- Unveränderte Werte werden normalerweise nicht erneut geschrieben. Ein zur Laufzeit
  inaktiver Speicher schreibt seinen sicheren Zustand bedingungslos.
- Die HEMS-Notabschaltung schreibt unabhängig von Rampe und Totband `0 W`, danach `standby`.

Das sind getrennte HA-Service-Aufrufe, keine atomare Transaktion. Die Bridge reagiert auf jede
Änderung unmittelbar; sie besitzt keinen gemeinsamen Commit-Marker und kein Debounce für
dieses Paar.

## Befehlsausführung im Provider

Bei Setup registriert die Bridge beide Helfer-Listener und den Keep-Alive-Timer und synchronisiert
einmal sofort. Sie merkt die zuletzt erfolgreich angewendete Betriebsart im Arbeitsspeicher.

| Gelesene Betriebsart | Adapteraufrufe |
|---|---|
| `laden` | Bei Moduswechsel zuerst `write_discharge_power(0)`, dann `write_charge_power(abs(Leistung))`. |
| `entladen` | Bei Moduswechsel zuerst `write_charge_power(0)`, dann `write_discharge_power(abs(Leistung))`. |
| `standby` oder anderer vorhandener State | `write_charge_power(0)`, danach `write_discharge_power(0)`. |

Beim Initialsync und nach Fortsetzen gilt der Modus als neu: der Nullschritt der inaktiven
Richtung wird erneut ausgeführt. Bei gleicher aktiver Richtung entfällt er, damit eine reine
Leistungsanpassung nicht jedes Mal kurz den gemeinsamen Geräte-Sollwert auf null setzt.

Erst nach allen erfolgreichen Adapteraufrufen des Syncs werden `last_command`,
`_last_applied_mode` und `write_ok` aktualisiert und ein Messwertrefresh angefordert.
Ein `StorageAdapterError` setzt `write_ok` auf falsch und aktualisiert die Diagnose-Entities.
Ein späterer Helferwechsel oder Keep-Alive versucht erneut zu synchronisieren.

Die Adapter serialisieren einzelne Transportaufrufe. Die gesamte aus mehreren Aufrufen
bestehende Bridge-Synchronisierung ist nicht durch eine eigene gemeinsame Sperre geschützt.
Es besteht keine zugesagte Transaktionsisolation gegenüber einem weiteren Sync oder manuellen
Schreibaufruf.

## HEMS-Lebenszeichen

Status: **Implementiert** — HEMS-Seite SkytechHEMS D-062/D-069, Auswertung im Provider
D-016/D-019 (`custom_components/battery_bridge/heartbeat.py`, `hems_bridge.py`).
Entität, Attribute und Frisch-Regel sind im Vertrag HEMS ↔ Wallbox-Provider identisch; nur die
Reaktion bei nicht frischem Lebenszeichen ist gerätespezifisch.

Ein unverändert bleibender Sollwert ist normaler Betrieb. Ein HEMS-Ausfall ist deshalb nicht am
Alter eines Sollwerthelfers erkennbar. Das Lebenszeichen steht deshalb in der
Schnittstellen-Entität des HEMS, die es in jedem Zyklus veröffentlicht. Bis Version 1.3 war es
`sensor.skytech_hems_status`; diese Entität entfällt.

```
POST {HA_URL}/api/states/sensor.hems_schnittstelle
```

| Feld | Typ | Bedeutung |
|---|---|---|
| `state` | Text | Präfixliste der Speicher (siehe oben); **kein** Lebenszeichen. Leer ist gültig. |
| `attributes.zyklus_zaehler` | Ganzzahl | Zyklus-Zähler; wird in jedem Zyklus verändert (Überlauf erlaubt). |
| `attributes.zyklus_intervall_s` | Zahl > 0 | Aktuell konfigurierte Zykluslänge des HEMS in Sekunden. |
| `attributes.erzeugt_am` | Text | `TT.MM.JJJJ hh:mm:ss`, Berliner Zeit; nur Anzeige, nicht zur Auswertung. |
| `attributes.vertrag_version` | Ganzzahl | `2`. Unbekannte zusätzliche Attribute ignoriert der Provider. |

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
- Ist die Entität nicht vorhanden, `unknown` oder `unavailable`, oder fehlt `zyklus_zaehler`, ist
  das Lebenszeichen nicht frisch.
- **Nicht frisch:** Der Provider wendet **keine** Ladung oder Entladung an und setzt den Speicher
  auf `0 W` (Standby-Verhalten, wie bei `standby` in der Tabelle "Befehlsausführung"). Sobald ein
  frisches Lebenszeichen vorliegt, wird der aktuelle Schnappschuss automatisch angewendet.
- **Nach Start des Providers** (Neustart, Neuladen, Entry-Setup) gilt das Lebenszeichen erst als
  frisch, nachdem der Provider **nach seinem Start** eine Änderung von `zyklus_zaehler` gesehen hat.
  Ein wiederhergestellter oder alter Wert löst keine Ladung oder Entladung aus.
- Bei pausierter Bridge (`hems_steuerung_aktiv` aus) wird das Lebenszeichen nicht ausgewertet;
  die Bridge führt dann keinen Sync aus. Die HEMS-Notabschaltung übersteuert die Pause nicht
  (**Bekannte Grenze**, bewusst so entschieden).

`binary_sensor.<provider_prefix>_hems_lebenszeichen` bildet diesen Zustand ab (an = frisch).
Der Provider prüft die Frist alle 5 s, unabhängig vom Keep-Alive-Takt; die HEMS-Sollsensoren
zeigen im Stoppzustand `0`, weil genau das gesendet wurde.

## Keep-Alive, Pause und Neustart

| Verhalten | Aktueller Stand |
|---|---|
| Marstek-Keep-Alive | Aktueller Helfer-Schnappschuss alle 60 s; Adapter verwendet einen 300-s-Passive-Mode-Zeitraum. |
| E3DC-Keep-Alive | Aktueller Helfer-Schnappschuss alle 5 s, einschließlich Nullanforderung. |
| Messwert-Poll | Standard 5 s, konfigurierbar 1–60 s; getrennt vom Keep-Alive. |
| Poll-Ausfall | Coordinator verwendet vorübergehend 30 s; erfolgreicher Poll stellt den normalen Takt wieder her. |
| Bridge-Schalter aus | Unterbindet neue automatische Syncs einschließlich Keep-Alive; sendet selbst keinen Stopp. |
| Bridge-Schalter ein | Sofortige Synchronisierung einschließlich erneuter Richtungsinitialisierung. |
| Neustart/Neuladen | Bridge wieder aktiv; pausierter Zustand und letzter Befehl werden nicht wiederhergestellt. Bis zum ersten frisch gesehenen HEMS-Zyklus beide Richtungen 0 W. |
| Unload | Entfernt Helfer-Listener und Keep-Alive; kein ausdrücklicher Abschaltbefehl der Bridge. |

Eine Pause bricht einen bereits laufenden Sync nicht ausdrücklich ab. Manuelle Number-Befehle
haben keinen eigenen Keep-Alive. Das Verhalten bei ausbleibenden Herstellerbefehlen bleibt
adapter-/geräteabhängig; insbesondere ist der Rückfall in Geräteautomatik nicht gleichbedeutend
mit garantiertem physischem Stillstand.

## Ausfälle und bekannte Grenzen

| Fall | Tatsächliches Verhalten / Grenze |
|---|---|
| Einer der Helfer fehlt vollständig | Bridge protokolliert einmal und kehrt ohne Schreibauftrag zurück. Der letzte Gerätebefehl wird dadurch nicht aktiv aufgehoben. |
| Leistungsstate ist nicht als Zahl parsebar | `_parse_leistung()` liefert `0`; bei vorhandenem Betriebsart-State folgt eine Nullanforderung. |
| Betriebsart-State ist `unknown`, `unavailable` oder anderweitig unerwartet | Beide Richtungen werden wie bei Standby auf null gesetzt. |
| `NaN` oder Unendlich als Leistungsstate | Keine ausdrückliche Endlichkeitsprüfung in der Bridge; Verhalten fällt in Adapterpfade. Ein einheitlicher sicherer Fehlerpfad ist dafür nicht zugesagt. |
| Vorzeichen widerspricht Betriebsart | Betrag wird in die durch Betriebsart gewählte Richtung geschrieben; keine Fehlererkennung für das Paar. |
| HEMS steht, HA und Provider laufen weiter | Nach Ablauf der Lebenszeichen-Frist gehen beide Richtungen auf 0 W, auch im Keep-Alive; mit dem nächsten HEMS-Zyklus übernimmt die Bridge wieder. Steht das HEMS-Add-on, aber nicht HA, bleibt der Speicher dauerhaft auf 0 W. |
| Geräteverbindung ausgefallen | Messsensoren werden nicht verfügbar; Schreibfehler werden separat sichtbar. Physischer Stopp ist ohne erreichbaren Transport nicht garantiert. |
| HEMS-Notabschaltung bei pausierter Bridge | HEMS setzt Helfer auf null/Standby; die Bridge beobachtet den Notabschaltungsstatus nicht gesondert und führt während der Pause keinen neuen Sync aus. |
| Unterschiedliche Herstellerlimits | Bridge führt keine generische Prüfung gegen HEMS-`available_*_w` aus; richtige Konfiguration und Adapter-/Gerätegrenzen bleiben erforderlich. |
| Gerät verweigert ohne gesetzte Sperre | Marstek: der Provider erkennt das nach der Erkennungszeit (Default 30 s) und meldet die Richtung als gesperrt; bis dahin fließt Leistung aus dem Netz. Ohne HEMS-Istwerte pausiert die Erkennung. E3DC: kein Abgleich Soll gegen Ist. |
| Teil-Update | HEMS ab 3.0.0 und Provider ab Vertrag 2.0 müssen zusammen aktualisiert werden. Sieht der Provider kein passendes Lebenszeichen, bleibt der Speicher auf 0 W (sicherer Zustand). |
| Statusabfrage verzögert | Eine neue Gerätesperre wird bis zu 15 s plus ein Poll-Intervall später sichtbar. |

Besonders bei Richtungswechseln kann die neue Betriebsart kurzfristig mit dem alten
Leistungsbetrag zusammen gelesen werden. Beispiel: `laden`/`+1000` wird zu `entladen`/`-500`;
zwischen beiden HEMS-Schreibvorgängen kann der Provider zunächst `entladen`/`+1000` lesen und
1.000 W Entladung beauftragen. Der Vertrag beschreibt diese bestehende Grenze und behauptet
keine atomare Umschaltung.

Der Provider ersetzt keinen unabhängigen HEMS-Ausfallwächter. Ein Wächter darf aus einem lange
unveränderten Leistungshelfer allein keinen Ausfall ableiten, weil HEMS unveränderte Sollwerte
bewusst nicht regelmäßig neu schreibt.

Die tatsächliche Bedeutung der Messwerte ist adapterabhängig: Der vorhandene Marstek-Adapter
verwendet bei fehlendem `bat_power` ersatzweise negiertes `ongrid_power`. Dieser Ersatz deckt
keinen zusätzlichen Backup-/Offgrid-Anteil ab. Für E3DC sind Vorzeichen und Rückfallzeiten in
der Provider-Dokumentation weiterhin als an Hardware zu bestätigende Punkte markiert.
Die Vertragsdokumentation ersetzt diese Hardwareprüfung nicht.

## Zuständigkeiten und Nicht-Ziele

| Thema | SkytechHEMS | Battery-Provider |
|---|---|---|
| Überschuss, Hausbilanz, Prioritäten | entscheidet | konsumiert nicht |
| SoC-Ziele, Ladestufen, Grenzen und Rampen | entscheidet | übernimmt resultierende Anforderung |
| Ausgabehelfer | schreibt | liest |
| Geräteprotokoll und Verbindungsaufbau | kein direkter Zugriff | verantwortlich |
| Ist-SoC und Istleistungen | liest aus eigenen konfigurierten Sensoren; veröffentlicht Istwerte in `sensor.hems_schnittstelle` | veröffentlicht Messsensoren; nutzt HEMS-Istwerte für den Soll/Ist-Vergleich |
| Gerätefreigaben | sperrt die betroffene Richtung, gibt das Defizit an den nächsten Speicher weiter | liest am Gerät bzw. ermittelt sie per Soll/Ist-Vergleich (Marstek), veröffentlicht in `sensor.battery_provider_schnittstelle` |
| Schreibdiagnose | sieht Erfolg des HA-Helferzugriffs | sieht Ergebnis seiner Adapteraufrufe |
| Geräteautonomie bei Verbindungsverlust | keine physische Bestätigung | adapterabhängig; keine allgemeine Stoppgarantie |
| `sensor.ems_<prefix>_lade_limit_w` | veröffentlicht als Diagnose | wird von der Bridge nicht gelesen |

Ein erfolgreicher HEMS-Helferzugriff bestätigt nicht, dass der Speicher den Befehl ausgeführt
hat. Die beiden Schreibdiagnosen betreffen unterschiedliche Abschnitte des Transportwegs.

## Kompatibilität und Änderungen

Version `2.0` (20.10.2026) ist inkompatibel zu `1.x`: `sensor.skytech_hems_status` und der
Schnittstellen-Sensor je Speicher (`sensor.<provider_prefix>_hems_schnittstelle`) entfallen,
ebenso das HEMS-Feld `provider_entity`. Ersatz sind `sensor.hems_schnittstelle` und
`sensor.battery_provider_schnittstelle`. Beide Projekte müssen zusammen aktualisiert werden.

Neue optionale Diagnose-Entities oder Adapter können additiv ergänzt werden. Änderungen an
Helfernamen, Einheiten, Vorzeichen, Betriebsarten oder Ausfallsemantik benötigen eine gemeinsame
Prüfung beider Projekte und eine entsprechende Vertragsversion. Dokumentversion `1.0` ist
keine zur Laufzeit übertragene Protokollversion.

Die bekannten Grenzen werden erst nach tatsächlich implementierter und geprüfter Änderung
entfernt. Insbesondere dürfen strikte Paarvalidierung oder serialisierte
Gesamtbefehle nicht allein durch eine neue Formulierung als vorhanden gelten.

Implementierungsreferenzen:

| Repository | Dateien |
|---|---|
| SkytechHEMS | `app/status_publisher.py`, `app/main.py`, `app/ems/controller.py`, `app/ems/devices.py` (`BatteryDevice`), `app/ems/state.py`, `app/ems/ops.py`, `app/emergency.py`, `docs/device_classes/battery.md` |
| Skytech-HEMS-Battery-Provider | `custom_components/battery_bridge/interface.py`, `response_check.py`, `hems_bridge.py`, `heartbeat.py`, `binary_sensor.py`, `sensor.py`, `number.py`, `switch.py`, `coordinator.py`, `const.py`, `adapters/marstek_udp.py`, `adapters/e3dc_rscp.py` (unter `custom_components/battery_bridge/`) |

## Additive Ladeziel-Metadaten im HEMS — 21.10.2026

Für vorbereitete Wallbox-Wege ergänzt HEMS `ladevertrag_version` und `ladeziele`
in derselben Schnittstellen-Entität. Der Battery-Provider ignoriert diese Attribute.
Speicherpräfixliste, `vertrag_version: 2`, Lebenszeichen und Speicher-Istwerte bleiben
unverändert. Der Battery-Provider bleibt ausschließlich für stationäre Speicher
zuständig; EVMS–Wallbox-Verträge übertragen ihm keine Fahrzeugsteuerung.
