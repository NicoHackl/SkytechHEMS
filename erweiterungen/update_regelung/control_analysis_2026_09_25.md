# Regelanalyse HEMS – Live-Daten vom 25.09.2026

Auswertung des realen Regelverhaltens über den HA-MCP-Zugriff. Ziel: Optimierungen an der
Regellogik ableiten und Schwächen in der Datenlage benennen. Diese Datei ist **Analyse und
Vorschlag** — es wurde weder Code noch Konfiguration geändert.

## 1. Datengrundlage

| Fenster | Uhrzeit | Charakter |
|---|---|---|
| Vormittag | 09:30–10:30 | Beide Speicher laden, ruhige Einstrahlung |
| Mittag | 12:00–13:00 | Wolken plus pulsierende Hauslast, beide Speicher entladen zeitweise |
| Nachmittag | 15:00–16:00 | Speicher voll (E3DC 99 %, AC 100 %), nur Heizstab und Heizlüfter |

Quellen:

- `sensor.skytech_hems_flow_status` (Attribute je Zyklus, ~2 s): `residual_w`, `pool_w`,
  `hausdefizit_w`, `hems_last_w`, je Gerät `leistung_w`. **Achtung:** bei Heizstab und Heizlüftern
  ist `leistung_w` der Istwert, bei Speichern der **Sollwert** (`netto_w`), nicht die Messung.
- Sollwert-Helfer `input_number/input_select.ems_*_anforderung_*`, Schalter `switch.ems_uv_1/2`,
  `sensor.elwa_istleistung`, `sensor.shelly_em4_ac_speicher_1_leistung`,
  `sensor.ac_speicher_1_ist_*`, `sensor.netz_leistung_ed` (nur 10-s-Raster).
- Add-on-Log des Tages und die aktuelle Add-on-Konfiguration.

Aktive Konfiguration (Auszug): `interval_s: 2`, `protected_minimum_scope: binary_and_controllable`,
`speicher_in_residual_enthalten: true`. Prioritäten: E3DC 1, AC-Speicher 5, Heizstab 10,
Heizlüfter 2 = 30, Heizlüfter 1 = 31, Wallbox 40 (gesperrt). Entladepriorität: AC-Speicher 1,
E3DC 5.

## 2. Kennzahlen je Fenster

| Fenster | Residual ±150 W | Einspeisung | Netzbezug | Sollwert-Schreibvorgänge/h |
|---|---|---|---|---|
| 09:30–10:30 | 89 % der Zyklen | 0,08 kWh | 0,02 kWh | Heizstab 144, AC 417, E3DC 120 |
| 12:00–13:00 | 46 % | 0,33 kWh | 0,22 kWh | Heizstab 213, AC 104, **E3DC 628 + 343 Betriebsartwechsel** |
| 15:00–16:00 | 56 % | 0,30 kWh | 0,03 kWh | **Heizstab 626** (274 Richtungsumkehrungen) |

„Residual" ist hier `residual_w` aus dem Flow-Status; er entspricht in allen Stichproben dem
negativen Netzwert (`sensor.netz_leistung_ed`), positiv = Einspeisung.

## 3. Befunde

### 3.1 Vormittag: Regelung sauber, Verteilung folgt der Sockel-Logik

- 09:45–10:25 liegt der Residual stabil bei 30–100 W — die Regelung ist hier gut.
- Der E3DC (Priorität 1) bleibt konstant bei **1500 W**, obwohl bis 6000 W möglich wären. Grund
  ist kein Fehler, sondern `binary_and_controllable`: zuerst bekommen **alle** Geräte ihre
  geschützte Mindestleistung (E3DC 1500, AC 2500 → um 10:09 von Hand auf 1500, Heizstab 500 → 1700),
  erst danach gibt es Zusatzleistung nach Priorität. Der Pool (3,1–4,3 kW) erreichte nie die
  Summe der Sockel (4,7 kW), also bekam der E3DC nie mehr als seinen Sockel, während der Heizstab
  (Priorität 10) Leistung bekam.
- Das Heizstab-Soll-Flattern um 10:09:34–42 (500 ↔ 797 ↔ 487 W) fällt zeitlich mit dem Verstellen
  der Sockel-Helfer zusammen — kein Reglerfehler.

→ **Rückfrage F-7:** Ist das so gewollt?

### 3.2 Mittag: pulsierende Last schaukelt beide Speicher auf (Hauptbefund)

Von 12:05 bis 12:50 (vereinzelt auch 09:54, 10:19, 10:26 und nachts) tritt eine **Last von
rund 2 kW auf, die alle ~30 s für 2–4 s anspringt**. Der Residual fällt dabei auf −2000 W und
springt danach auf +2000 W.

Reaktionskette (Beispiel 12:11–12:15):

1. Die Last springt an → `hausdefizit_w` steigt → der AC-Speicher bekommt −2500 W, der E3DC bis
   **−6000 W**.
2. Der Marstek braucht laut Shelly-Messung 2–5 s, bis die Entladung ankommt. Dann ist die Last
   schon wieder weg → die Speicherentladung geht **ins Netz** (Residual +2000 W, `pool_w` > 0).
3. Das HEMS nimmt die Entladung zurück → Totzone/Ziel 0 → sofort `standby` → 4 s später wieder
   `entladen` mit vollem Sprung.

Messbar:

- E3DC-Sollwert: 628 Schreibvorgänge und 343 Betriebsartwechsel in einer Stunde, Sprünge von 0 auf
  −6000 W und zurück alle 4 s (z. B. 12:14:04 `standby` 0 W → 12:14:08 `entladen` −6000 W →
  12:14:12 −1539 W → 12:14:17 −6000 W).
- Add-on-Log: **über 70 Warnungen** „Entladung … UND Pool … gleichzeitig" allein zwischen 12:07 und
  12:55, dazu weitere nachts (23:11, 23:41, 01:18, 02:55, 05:15) — dasselbe Muster: Die Entladung
  läuft noch, wenn die Last schon weg ist.
- Nur 46 % der Zyklen im Band ±150 W.

Ursachen im Code (`app/ems/devices.py`, `BatteryDevice.calculate_ramp`):

| # | Ursache | Stelle |
|---|---|---|
| a | Die **Umschaltsperre** greift nur beim direkten Wechsel laden ↔ entladen. Der Weg entladen → standby → entladen ist ungebremst, weil `richtung_alt` bei standby 0 ist | Bedingung `richtung_neu and richtung_alt and …` |
| b | Ziel 0 (Totzone oder kein Defizit) geht **ohne** `runter_regelzeit_s` sofort auf 0 — so gewollt laut D-055, verstärkt hier aber das Pendeln | `else`-Zweig nach `netto`-Auflösung |
| c | Speicher haben **kein Schrittlimit**: der optionale Helfer `input_number.ems_<prefix>_max_anderung_pro_schritt_w` ist für beide Speicher nicht angelegt, also springt der Sollwert nach Ablauf der Regelzeit direkt auf das volle Ziel (0 → −6000 W) | `_begrenze_schritt`, `update_from_ha` |
| d | Entladeziel = **Momentanwert** des Hausdefizits. Ein 2-s-Puls wird voll ausgeregelt, obwohl der Aktor langsamer ist als der Puls | `_allocate_discharge` im Controller |
| e | Zwei Speicher teilen sich schnelle Pulse: um 12:13:19 wechselt die Deckung vom AC-Speicher auf den E3DC, der dann ebenfalls mitpendelt | Entladeplanung |

→ **Rückfragen F-1 und F-3.**

### 3.3 Nachmittag: Heizlüfter takten, Heizstab schreibt zu oft

- **Heizlüfter:** Die Einschaltphasen dauern fast immer **~150 s = Mindestlaufzeit 120 s +
  Abschaltverzögerung 30 s** (UV1: 8×, UV2: 12× am Tag). Nach Ablauf der Mindestdauer gehen sie
  sofort wieder aus. Ursache sind Wolkenkanten: Überschussspitzen von 2–3,4 kW über 30–60 s
  (z. B. 15:13:20–15:14:10, 15:25:48–15:26:09), während der Heizstab schon am Anschlag steht.
  Die Einschaltverzögerung (30 s, durchgehend geprüft — korrekt implementiert) wird gerade noch
  erfüllt, dann bricht der Überschuss ein.
- **Heizstab:** 626 Sollwert-Schreibvorgänge pro Stunde bei einem Totband von 15 W. Das
  Messrauschen des Residuals liegt bei ±50 W. Der ELWA folgt dem Sollwert in 2–3 s — Regelzeit
  3 s passt, das Totband ist zu fein.
- **Heizstab-Maximum:** Das Soll steht auf 3500 W, der ELWA liefert real höchstens 3250–3400 W
  (gemessen). Überschuss darüber bleibt liegen, bis ein Heizlüfter zuschaltet.
- **Heizlüfter-Leistung:** konfiguriert 1500 W, gemessen UV1 ≈ 1320–1410 W, UV2 ≈ 1260–1330 W.

### 3.4 Unvollständige Sensor-Verträge

- Die lokale Vorlage
  `erweiterungen/zusatz_sensor_für_speicher_null_einspeisung/ueberschusssensor_von_ha.yaml` passt
  **nicht** zu den Live-Werten: Live gilt `residual_w` = Hausleistungsbilanz = −Netz (z. B.
  18:14 Uhr: Netz −3 W, beide Sensoren 3 W, E3DC-Batterie −12 W). Nach der lokalen Formel müssten
  Netzhysterese (200 W) und Batterie-Entladung abgezogen sein.
- [docs/bekannte-luecken.md](../../docs/bekannte-luecken.md) und
  [docs/konfiguration.md](../../docs/konfiguration.md) beschreiben den E3DC als **kein HEMS-Gerät**,
  dessen Batterieleistung bewusst in der Hausleistungsbilanz steckt. Inzwischen ist er aber als
  `e3dc_speicher` (Klasse `battery`) im HEMS und wird über
  `switch.technik_e3dc_speicher_hems_steuerung` gesteuert. Steckt seine Batterieleistung noch in
  der Bilanz, würde seine eigene Entladung von `netz_support_w` ein zweites Mal abgezogen
  (Mitkopplung). Die Live-Werte sprechen dafür, dass die Bilanz inzwischen nur noch −Netz ist —
  **bestätigt ist das nicht.**

→ **Rückfrage F-2.** Die Doku wird erst nach der Antwort angepasst.

## 4. Datenlage — was schlecht ist und verbessert werden muss

| # | Problem | Folge | Vorschlag |
|---|---|---|---|
| D-1 | Recorder zeichnet die **Kern-Regelsensoren nicht auf**: `sensor.verfugbare_leistung_fur_uberschusverbraucher`, `sensor.hausleistung_bilanz_fur_ac_speicher`, `sensor.e3dc_leistung_netz_modbus`, `…_ertrag_gesamt_modbus`, `…_batterie_modbus`, `…_haus_modbus`, `…_netz_einspeisung/_bezug`, `…_batterie_laden/_entladen`, `sensor.elwa_istleistung_modbus`. `sensor.mqtt_ac_speicher_1_leistung` zuletzt am 20.09.2026 um 17:48 | Keine direkte Nachanalyse von PV, Netz und E3DC-Batterie möglich; nur der Umweg über `flow_status` | Mindestens Netz, PV, E3DC-Batterie und die beiden HEMS-Eingangssensoren wieder aufzeichnen (bei Platzsorge: `recorder`-Filter nur für diese, oder Aufbewahrung kurz) |
| D-2 | Keine `state_class` an den Leistungssensoren (Modbus und Template) | Keine Langzeitstatistik (5-min/Stunde) — Trends über 10 Tage hinaus fehlen | `state_class: measurement` und `device_class: power` setzen |
| D-3 | `sensor.netz_leistung_ed` nur im 10-s-Raster | Zu grob für die Analyse eines 2-s-Reglers | Für die Analyse `sensor.e3dc_leistung_netz_modbus` aufzeichnen (D-1) |
| D-4 | `flow_status.devices.<speicher>.leistung_w` ist der **Sollwert**, bei den anderen Geräten der Istwert | Leicht falsch zu lesen; Soll/Ist der Speicher lässt sich nicht vergleichen | Im Status getrennt `soll_w` und `ist_w` führen (siehe R-6) |
| D-5 | `sensor.e3dc_leistung_batterie_modbus` steht seit 13:17 unverändert auf −12 W | Bei SoC 99 % plausibel (Ruhe), aber ein eingefrorener Wert wäre nicht zu erkennen | Mit dem E3DC-Portal gegenprüfen; im HEMS einen Veraltungs-Check (`last_reported`) erwägen |
| D-6 | Lokale YAML-Vorlage des Überschuss-Sensors ist veraltet (3.4) | Doku und Analyse arbeiten mit falschem Vertrag | Aktuelle YAML ins Repo legen |
| D-7 | Heizlüfter `power_w` 1500 W vs. gemessen ~1300 W; Heizstab-Maximum 3500 W vs. real ~3400 W | Einschaltschwellen und Sockelrechnung zu konservativ | Werte an die Messung angleichen (P-5, P-6) |

## 5. Optimierungsvorschläge

### 5.1 Sofort umsetzbar — nur Parameter, keine Codeänderung

| # | Parameter | heute | Vorschlag | Wirkung |
|---|---|---|---|---|
| P-1 | `input_number.ems_acspeicher1_umschalt_totzone_w` / `…e3dc_speicher_umschalt_totzone_w` | 15 / 60 W | 150–200 W | Kleine Pulse lösen keinen Richtungswechsel mehr aus |
| P-2 | `direction_switch_delay_s` (Add-on) acspeicher1 / e3dc_speicher | 3 / 5 s | 20–30 s | Weniger Richtungswechsel — wirkt aber wegen 3.2 a **nicht** über Standby hinweg |
| P-3 | `input_number.ems_*speicher*_hoch_regelzeit_s` | 3 s | 6–8 s (≥ Aktor-Totzeit + 1 Zyklus) | Ein 2–4-s-Puls ist vorbei, bevor die Entladung erhöht wird. Nachteil: das Laden reagiert ebenfalls langsamer (gemeinsame Rampe) |
| P-4 | `input_number.ems_heizstab_min_anderung_pro_schritt_w` | 15 W | 50 W | Etwa ein Drittel der Schreibvorgänge, Residual-Rauschen wird ignoriert |
| P-5 | `power_w` / `input_number.ems_heizlufter_1/2_leistung_w` | 1500 W | 1350 / 1300 W | Realistische Einschaltschwelle |
| P-6 | Heizstab `technical_maximum` / `…max_technisch_w` | 3500 W | 3400 W | Reststrom oberhalb des ELWA-Maximums wird sichtbar |
| P-7 | Heizlüfter `einschaltverzogerung_s` | 30 s | 60–90 s | Wolkenkanten unter einer Minute lösen kein Einschalten mehr aus; weniger 150-s-Zyklen |
| P-8 | `input_number.ems_acspeicher1_max_anderung_pro_schritt_w` / `…e3dc_speicher_max_anderung_pro_schritt_w` (neu anlegen, optionaler Helfer — der Code liest ihn bereits) | fehlt | 500 / 1000 W | Keine Sprünge 0 → −6000 W mehr |

P-1 bis P-3 und P-8 dämpfen das Mittagsproblem, lösen es aber nicht — dafür braucht es R-1 und R-3.

### 5.2 Änderungen an der Regellogik (Code)

**R-1 Umschaltsperre auch über Standby (Befund 3.2 a).**
Den Zeitstempel der letzten *aktiven* Richtung und des Wechsels auf standby merken. Ein
Wiedereinstieg in die **Gegenrichtung** wird für `direction_switch_delay_s` gesperrt, ein
Wiedereinstieg in **dieselbe** Richtung wird mindestens um `hoch_regelzeit_s` ab dem Standby
verzögert. Sicherheitsgründe (Sensor ungültig, Freigabe weg, Betriebsart standby) bleiben
sofort wirksam.

**R-2 Add-on-Fallback für die Speicher-Schrittbegrenzung (Befund 3.2 c).**
Heute gilt ohne Helfer „keine Begrenzung". Ein fehlender optionaler Helfer sollte bei einem
Speicher nicht zu ungebremsten Sprüngen über die volle Leistung führen. Vorschlag: optionales
Add-on-Feld `maximum_step_change` auch für `battery`, Default leer = heutiges Verhalten. Solange
das fehlt, reicht P-8.

**R-3 Gefiltertes Entladeziel (Befund 3.2 d) — der wirksamste Hebel.**
Das Hausdefizit für die **Erhöhung** der Entladung nicht als Momentanwert nehmen, sondern als
Minimum (oder unteres Perzentil) über ein Fenster von z. B. 6–10 s. Für die **Rücknahme** der
Entladung weiterhin den Momentanwert, damit keine Speicherenergie ins Netz geht. Wirkung: Ein
2–4-s-Puls wird kurz aus dem Netz gedeckt (≈ 2 kW × 3 s ≈ 1,7 Wh je Puls), statt dass
anschließend 2 kW × 4 s aus dem Speicher eingespeist werden — und der Speicher pendelt nicht.
Das Fenster als Helfer (`…_entlade_filter_s`) mit Default 0 = heutiges Verhalten, damit nichts
Bestehendes bricht.

**R-4 Ziel 0 durch Totzone rampen statt springen (Befund 3.2 b).**
Nur wenn R-1 und R-3 nicht reichen: Fällt das Ziel **wegen Totzone** auf 0, gilt
`runter_regelzeit_s` wie bei jeder anderen Absenkung. Das berührt D-055 („Totzone sofort 0") und
braucht deshalb eine neue Design-Entscheidung.

**R-5 Überschuss-Mittelwert für Binärgeräte (Befund 3.3).**
Alternative zu P-7: Einschaltentscheidung eines Binärgeräts auf das Minimum des Pools über die
Einschaltverzögerung stützen statt auf den Momentanwert am Ende der Verzögerung. Heute prüft die
Verzögerung „ununterbrochen gewünscht" — ein Pool, der 30 s knapp über der Schwelle schwankt,
reicht dafür. Das Minimum macht die Entscheidung robuster, ohne die Verzögerung zu verlängern.

**R-6 Diagnose-Sensor mit Soll und Ist (D-1, D-4).**
Im Flow-Status je Speicher `soll_w` **und** `ist_w` ausgeben, dazu global
`residual_bereinigt_w` und je Speicher `blockiert_grund` (`umschaltsperre`/`totzone`). Der Sensor
wird bereits aufgezeichnet — damit wäre jede künftige Analyse ohne Recorder-Umbau möglich.
Additiv, also ohne Bruch des Vertrags zur Power Flow Card (D-047).

**R-7 Warnung „Entladung UND Pool" drosseln.**
Die Meldung erscheint mittags mehrmals pro Minute und verdeckt andere Warnungen. Vorschlag: nur
loggen, wenn der Zustand länger als z. B. 10 s anhält, und höchstens einmal pro Minute.

### 5.3 Reihenfolge

1. Rückfragen F-1 bis F-3 klären (Lastquelle, Sensorvertrag, E3DC-Steuerweg).
2. P-1, P-3, P-4, P-5, P-7, P-8 setzen und einen Tag beobachten.
3. R-6 umsetzen, damit die Wirkung messbar wird.
4. R-3, dann R-1 — mit Pflicht-Testfällen für einen 2-s-Puls alle 30 s. R-2 nebenbei.
5. R-4 und R-5 nur bei Restbedarf.

## 6. Offene Rückfragen

| # | Frage | Warum wichtig |
|---|---|---|
| F-1 | Was ist die **~2-kW-Last, die mittags alle ~30 s für 2–4 s anspringt** (12:05–12:50, auch 09:54, 10:19, 10:26 und nachts)? Induktionskochfeld, Backofen, Durchlauferhitzer, Pumpe? | Bestimmt die Filterlänge für R-3 und ob die Last überhaupt vom Speicher gedeckt werden soll |
| F-2 | Wie sind `sensor.verfugbare_leistung_fur_uberschusverbraucher` und `sensor.hausleistung_bilanz_fur_ac_speicher` **heute** definiert (aktuelle YAML)? Steckt die E3DC-Batterie noch in der Bilanz? | Seit der E3DC HEMS-Gerät ist, würde sie sonst doppelt gezählt; Doku muss danach korrigiert werden |
| F-3 | Schaltet der E3DC bei `switch.technik_e3dc_speicher_hems_steuerung: on` seine **eigene Nulleinspeisung ab**? Über welchen Weg (Automation/Modbus) und mit welcher Latenz kommt der Sollwert an? | Laufen beide Regler parallel, arbeiten sie gegeneinander. Falls der E3DC selbst schnell ausregelt, wäre „HEMS lädt, E3DC entlädt selbst" (Betriebsart `nur_laden`) die stabilere Aufteilung |
| F-4 | Welche Automation überträgt `input_number.ems_heizstab_anforderung_leistung_w` an den ELWA? `script.hems_postskript` ruft `script.mqtt_test_2` auf, das als YAML-Skript für MCP nicht lesbar ist | Schreibrate auf Modbus (P-4) und Latenz |
| F-5 | Sind die Recorder-Ausschlüsse (D-1) bewusst (Datenbankgröße)? Welche Sensoren dürfen wieder rein? | Grundlage jeder weiteren Analyse |
| F-6 | Welche Version läuft? Installiert ist laut Supervisor **2.0.17**, `config.yaml` im Repo sagt **2.0.6**. War D-055 (Commit vom 24.09.2026) heute aktiv? | Befunde 3.2 a–c beziehen sich auf den Code-Stand im Repo |
| F-7 | Ist gewollt, dass bei `binary_and_controllable` der E3DC (Priorität 1) auf seinem Sockel bleibt, solange niederpriore Geräte ihre Sockel noch nicht voll haben (3.1)? | Sonst müssten Sockel oder Scope angepasst werden |
| F-8 | Was wurde um 11:34 in der Konfiguration geändert (Neustart über die Konfigurationsseite, Supervisor meldete „nicht erreichbar")? | Ordnet Vormittag und Nachmittag der richtigen Konfiguration zu |

## 7. Annahmen

- Residual > 0 = Einspeisung, abgeleitet aus dem Vergleich mit `sensor.netz_leistung_ed`
  (Vorzeichen Netzbezug positiv).
- Die Aktor-Latenz des AC-Speichers (2–5 s) stammt aus dem Vergleich Sollwert-Helfer ↔
  `sensor.shelly_em4_ac_speicher_1_leistung`. Die Latenz des E3DC ist mangels aufgezeichneter
  Batterieleistung **nicht** gemessen.
- Die Energiebilanzen in Abschnitt 2 sind aus dem 2-s-Raster des Flow-Status integriert und
  daher Näherungen.
