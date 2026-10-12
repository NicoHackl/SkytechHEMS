# D-063: Der E3DC ist ein HEMS-Speicher und nicht mehr Teil der Hausleistungsbilanz

- **Datum:** 12.10.2026 (dokumentiert; in Betrieb seit Ende September 2026)
- **Status:** Aktiv
- **Betrifft:** Anlagenkonfiguration (`devices[]`, `battery_residual_power_entity`,
  `residual_power_entity`), Doku zu `class: battery`, [D-040](D-040-ac-speicher.md) Punkt 6,
  [D-044](D-044-hausleistungsbilanz-ac-speicher.md) (E3DC-Anteil der Bilanz)

> Diese Entscheidung ändert keinen Code. Sie hält eine Änderung der Anlage fest und löst die
> Anlagenannahme „der E3DC ist kein HEMS-Gerät" aus D-040 und D-044 ab. Die Mechanik der
> separaten Hausleistungsbilanz (D-044) bleibt unverändert gültig.

## Kontext

D-040 und D-044 gingen davon aus, dass der vorhandene, DC-gekoppelte E3DC sich selbst regelt und
das HEMS nur einen AC-Speicher (`acspeicher1`, Marstek Venus E 3.0) ansteuert. Die
Hausleistungsbilanz enthielt deshalb neben der Netzleistung bewusst die E3DC-Batterieleistung.

Inzwischen unterstützt der
[Skytech-HEMS-Battery-Provider](https://github.com/NicoHackl/Skytech-HEMS-Battery-Provider) den
E3DC über RSCP (dort D-015). In dieser Anlage gilt seitdem:

- Battery-Provider-Eintrag „E3DC Speicher“ (angelegt am 24.09.2026);
- HEMS-Gerät `e3dc_speicher`, `class: battery`, 12 kWh, je 6000 W Lade- und Entladegrenze,
  SoC aus `sensor.e3dc_batterie_soc_modbus`, Istleistung aus
  `sensor.e3dc_leistung_batterie_modbus` (`positiv_laden`);
- Notabschaltungs-Zielzeile `switch.technik_e3dc_speicher_hems_steuerung` → `off`, damit der E3DC
  bei einer Notabschaltung in seine Eigenregelung zurückfällt.

Bleibt der E3DC-Akku in der Hausleistungsbilanz, zählt seine Entladung doppelt: einmal in der
Bilanz und noch einmal als `netz_support_w` des Geräts `e3dc_speicher`. Beispiel: Hauslast
`700 W`, E3DC entlädt `700 W` → Bilanz `−700 W`, bereinigt `−700 − 700 = −1400 W`, Entladeziel
`1400 W` statt `700 W`.

## Betrachtete Optionen

### Option A — E3DC als HEMS-Speicher, Bilanz ohne E3DC-Akku (gewählt)

- Dafür: Ein Regler für beide Speicher; Lade- und Entladepriorität zwischen E3DC und AC-Speicher
  liegen im HEMS statt in zwei konkurrierenden Regelungen. Kein Grenzzyklus mehr zwischen
  E3DC-Eigenregelung und AC-Entladung (Rücknahmebedingung 1 aus D-044 entfällt). Voraussetzung
  für das geplante Netzladen mit dynamischem Strompreis, das beide Speicher planen soll.
- Dagegen: Der E3DC hängt nun an Battery-Provider und HEMS-Lebenszeichen; fällt beides aus,
  übernimmt der E3DC nach rund 10 s selbst (Battery-Provider D-015, D-016).

### Option B — E3DC bleibt selbstregelnd (Stand D-040/D-044)

- Dafür: Keine Abhängigkeit des Hauptspeichers vom HEMS.
- Dagegen: Keine gemeinsame Planung beider Speicher; der Battery-Provider-Adapter bliebe
  ungenutzt.

## Entscheidung

Option A, vom User so eingerichtet. Für die Sensoren dieser Anlage folgt daraus:

```text
hausleistungsbilanz_w = −netzleistung_w        (positiv = Einspeisung)
```

Die E3DC-Batterieleistung gehört nicht mehr hinein. Geprüft am 12.10.2026 um 21:17: Netz
`−28 W` (Einspeisung), E3DC-Akku entlädt `12 W`, `sensor.hausleistung_bilanz_fur_ac_speicher`
und `sensor.verfugbare_leistung_fur_uberschusverbraucher` zeigen beide `28 W`, also genau
`−Netz`. Mit der alten Formel wären es `16 W` gewesen.

Allgemein gilt für `battery_residual_power_entity` weiterhin D-044, präzisiert: Die Bilanz
enthält die Netzleistung plus die Leistung von Speichern, die das HEMS **nicht** regelt. Vom HEMS
geregelte Speicher (`class: battery`) gehören nicht hinein, ihre Leistung rechnet das HEMS über
`netz_support_w` selbst heraus.

`class: battery` steht damit nicht mehr nur für AC-gekoppelte Speicher. Für das HEMS zählt allein,
dass Lade- und Entladeleistung des Speichers am Netzübergabepunkt wirken. Beim DC-gekoppelten
E3DC ist das ebenso der Fall.

## Folgen

- **Positiv:** Beide Speicher werden nach `prioritat` und `entlade_prioritat` gemeinsam
  verteilt; der Netzlade-Plan (dynamischer Strompreis) kann beide Speicher berücksichtigen.
- **Negativ:** Die Doku-Formeln mit E3DC-Akku in der Bilanz (D-044, `konfiguration.md`, die
  HA-Vorlage unter `erweiterungen/`) beschreiben nicht mehr diese Anlage. Sie bleiben als Beispiel
  für Anlagen mit einem selbstregelnden Speicher stehen und sind entsprechend gekennzeichnet.
- **Offen:** Die Inbetriebnahme-Punkte des E3DC-Adapters (Vorzeichen, Halten des Sollwerts bei
  5-s-Takt, Parallelbetrieb mit der pyscript-Automation „E3DC Manuelle Leistung“) stehen im
  Battery-Provider unter `docs/bekannte-luecken.md` und sind dort noch nicht als bestätigt
  vermerkt.
- **Aufwand:** Nur Doku; kein Code.

## Rücknahmebedingung

Fällt der E3DC trotz Keep-Alive regelmäßig in seine Eigenregelung zurück (Istleistung springt
zwischen HEMS-Sollwert und Eigenverbrauchsregelung), ist er als HEMS-Gerät nicht verlässlich. Dann
wird er wieder selbstregelnd betrieben, und seine Batterieleistung gehört nach D-044 zurück in die
Hausleistungsbilanz.
