# Vertrag: SkytechHEMS ↔ Skytech HEMS Battery Provider

**Version:** 1.1

**Status:** Dokumentierter Implementierungsstand mit bekannten Betriebsgrenzen; das HEMS-Lebenszeichen ist **Entwurf**

**Stand:** 07.10.2026

**Geprüfte Codebasis:** SkytechHEMS `e5c0156`, Skytech-HEMS-Battery-Provider `12ae0f3`.

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
SkytechHEMS ── zwei input_*-Ausgabehelfer ──► HA ──► Battery-Provider ──► Speicher
SkytechHEMS ◄── SoC und Istleistungen ── HA ◄── Battery-Provider ◄── Speicher
```

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

## HEMS-Konfiguration

Der Provider liefert die getrennte Leistungssensor-Variante des HEMS-Speichervertrags.
Beispiel mit angenommenen, vor Ort zu prüfenden Entity-IDs und beispielhaften Gerätegrenzen:

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

Status: **Entwurf** — weder im HEMS noch im Provider implementiert. Bis zur Umsetzung gilt die
bekannte Grenze "HEMS steht, HA und Provider laufen weiter" der Tabelle unten unverändert.
Entität, Attribute und Frisch-Regel sind im Vertrag HEMS ↔ Wallbox-Provider identisch; nur die
Reaktion bei nicht frischem Lebenszeichen ist gerätespezifisch.

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
- **Nicht frisch:** Der Provider wendet **keine** Ladung oder Entladung an und setzt den Speicher
  auf `0 W` (Standby-Verhalten, wie bei `standby` in der Tabelle "Befehlsausführung"). Sobald ein
  frisches Lebenszeichen vorliegt, wird der aktuelle Schnappschuss automatisch angewendet.
- **Nach Start des Providers** (Neustart, Neuladen, Entry-Setup) gilt das Lebenszeichen erst als
  frisch, nachdem der Provider **nach seinem Start** eine Änderung von `zyklus_zaehler` gesehen hat.
  Ein wiederhergestellter oder alter Wert löst keine Ladung oder Entladung aus.
- Bei pausierter Bridge (`hems_steuerung_aktiv` aus) wird das Lebenszeichen nicht ausgewertet;
  die Bridge führt dann keinen Sync aus. Die HEMS-Notabschaltung übersteuert die Pause nicht
  (**Bekannte Grenze**, bewusst so entschieden).

`binary_sensor.<provider_prefix>_hems_lebenszeichen` bildet diesen Zustand ab (an = frisch);
er gehört zum Entwurf.

## Keep-Alive, Pause und Neustart

| Verhalten | Aktueller Stand |
|---|---|
| Marstek-Keep-Alive | Aktueller Helfer-Schnappschuss alle 60 s; Adapter verwendet einen 300-s-Passive-Mode-Zeitraum. |
| E3DC-Keep-Alive | Aktueller Helfer-Schnappschuss alle 5 s, einschließlich Nullanforderung. |
| Messwert-Poll | Standard 5 s, konfigurierbar 1–60 s; getrennt vom Keep-Alive. |
| Poll-Ausfall | Coordinator verwendet vorübergehend 30 s; erfolgreicher Poll stellt den normalen Takt wieder her. |
| Bridge-Schalter aus | Unterbindet neue automatische Syncs einschließlich Keep-Alive; sendet selbst keinen Stopp. |
| Bridge-Schalter ein | Sofortige Synchronisierung einschließlich erneuter Richtungsinitialisierung. |
| Neustart/Neuladen | Bridge wieder aktiv; pausierter Zustand und letzter Befehl werden nicht wiederhergestellt. |
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
| HEMS steht, HA und Provider laufen weiter | Keep-Alive erneuert den alten Helferwert weiter. Ein HEMS-Lebenszeichen-Gate ist als **Entwurf** definiert, aber nicht implementiert. |
| Geräteverbindung ausgefallen | Messsensoren werden nicht verfügbar; Schreibfehler werden separat sichtbar. Physischer Stopp ist ohne erreichbaren Transport nicht garantiert. |
| HEMS-Notabschaltung bei pausierter Bridge | HEMS setzt Helfer auf null/Standby; die Bridge beobachtet den Notabschaltungsstatus nicht gesondert und führt während der Pause keinen neuen Sync aus. |
| Unterschiedliche Herstellerlimits | Bridge führt keine generische Prüfung gegen HEMS-`available_*_w` aus; richtige Konfiguration und Adapter-/Gerätegrenzen bleiben erforderlich. |

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
| Ist-SoC und Istleistungen | liest | veröffentlicht |
| Schreibdiagnose | sieht Erfolg des HA-Helferzugriffs | sieht Ergebnis seiner Adapteraufrufe |
| Geräteautonomie bei Verbindungsverlust | keine physische Bestätigung | adapterabhängig; keine allgemeine Stoppgarantie |
| `sensor.ems_<prefix>_lade_limit_w` | veröffentlicht als Diagnose | wird von der Bridge nicht gelesen |

Ein erfolgreicher HEMS-Helferzugriff bestätigt nicht, dass der Speicher den Befehl ausgeführt
hat. Die beiden Schreibdiagnosen betreffen unterschiedliche Abschnitte des Transportwegs.

## Kompatibilität und Änderungen

Neue optionale Diagnose-Entities oder Adapter können additiv ergänzt werden. Änderungen an
Helfernamen, Einheiten, Vorzeichen, Betriebsarten oder Ausfallsemantik benötigen eine gemeinsame
Prüfung beider Projekte und eine entsprechende Vertragsversion. Dokumentversion `1.0` ist
keine zur Laufzeit übertragene Protokollversion.

Die bekannten Grenzen werden erst nach tatsächlich implementierter und geprüfter Änderung
entfernt. Insbesondere dürfen das als Entwurf beschriebene Lebenszeichen, strikte Paarvalidierung oder serialisierte
Gesamtbefehle nicht allein durch eine neue Formulierung als vorhanden gelten.

Implementierungsreferenzen:

| Repository | Dateien |
|---|---|
| SkytechHEMS | `app/ems/devices.py` (`BatteryDevice`), `app/ems/ops.py`, `app/emergency.py`, `docs/device_classes/battery.md` |
| Skytech-HEMS-Battery-Provider | `custom_components/battery_bridge/hems_bridge.py`, `sensor.py`, `number.py`, `switch.py`, `coordinator.py`, `const.py`, `adapters/marstek_udp.py`, `adapters/e3dc_rscp.py` (unter `custom_components/battery_bridge/`) |
