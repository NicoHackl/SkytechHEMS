# D-041: Die physische Grenze eines AC-Speichers kommt allein aus den beiden `available_*`-Sensoren

- **Datum:** 21.08.2026
- **Status:** In Teilen ersetzt durch D-043
- **Betrifft:** `app/ems/devices.py` (`BatteryDevice`), `app/main.py` (Steuerschema), `config.yaml`,
  `/api/status`, [device_classes/battery.md](../device_classes/battery.md), Ersetzt Teile von D-040

> **Nachfolgeentscheidung:** D-043 ersetzt die beiden `available_*_entity`-Felder durch direkte
> Wattwerte in der Add-on-Konfiguration. Die übrigen Vereinfachungen dieser Entscheidung bleiben
> aktiv. Siehe [D-043](D-043-speichergrenzen-als-wattwerte.md).

## Kontext

Sieben Mechanismen begrenzten beim Speicher dieselbe Größe:

1. `input_number.ems_<prefix>_max_ladeleistung_w` / `_max_entladeleistung_w` — vom Nutzer gepflegt;
2. `soc_taper_band_prozent` — ein lineares Drosselband vor der SoC-Grenze;
3. `soc_reserve_prozent` — eine Notstromreserve über dem Tiefentladeschutz;
4. `available_charge_power_entity` / `available_discharge_power_entity` — optionales momentanes
   Gerätelimit;
5. die EP-Vorschläge `lade_max_w` / `entlade_max_w`;
6. `entlade_sofort_schwelle_w` — ab welcher Absenkung ungerampt zurückgenommen wird;
7. `max_anderung_pro_schritt_w` — die eigentliche Rampe.

Welcher davon gerade griff, war ohne Debug-Log nicht zu beantworten. Fachlich schlimmer: mehrere
regelten gegen das Gerät. Ein Wechselrichter fährt seine CV-Phase, sein Temperatur- und
Zell-Derating selbst — und meldet das Ergebnis als momentan verfügbare Leistung. Ein zweites
Drosselband im HEMS bildete dieselbe Kurve ein zweites Mal nach, mit anderen Parametern.

Die Notstromreserve war zusätzlich eine Zusage, die das HEMS gar nicht halten kann: es steuert
keinen Netzumschalter und kann eine Reserve gegen andere Verbraucher nicht durchsetzen.

## Betrachtete Optionen

### Option A — alles behalten, Vorrang genauer dokumentieren

- Dafür: keine brechende Änderung; jede bestehende Anlage läuft weiter.
- Dagegen: Die Doppelregelung gegen den Wechselrichter bleibt. Die Zahl der Sperrgründe bleibt bei
  sieben, und „lädt gerade nicht" bleibt ohne Log unerklärbar. Der Energy Pilot könnte weiterhin
  ein physisches Limit überschreiben.

### Option B — physische Grenze nur noch aus den beiden `available_*`-Sensoren

- Dafür: Eine Quelle für die Frage „wie viel darf gerade fließen". Das Gerät ist die einzige
  Instanz, die es wirklich weiß. Fünf Helfer und zwei EP-Felder entfallen ersatzlos.
- Dagegen: Brechende Konfigurationsänderung — die beiden Sensoren werden Pflicht. Wer sie nicht
  liefern kann, bekommt seinen Speicher nicht mehr registriert.

## Entscheidung

Option B. Die beiden `available_*`-Sensoren sind Pflicht und die **alleinigen** physischen
Maximalgrenzen. Entfernt werden `max_ladeleistung_w`, `max_entladeleistung_w`,
`soc_reserve_prozent`, `soc_taper_band_prozent`, `soc_max_hysterese_prozent`,
`entlade_sofort_schwelle_w`, `min_umschaltzeit_s` (nur beim Speicher) sowie die EP-Vorschläge
`lade_max_w` und `entlade_max_w`. Hysterese und Umschaltsperre werden statische Add-on-Felder
`soc_max_hysteresis_percent` (Default `2`) und `direction_switch_delay_s` (Default `5`).

Vier Eigenschaften sind dabei nicht verhandelbar:

- **Getrennte Auswertung.** Der Ausfall des Ladelimit-Sensors sperrt nur den Ladepfad. Ein
  gemeinsames „Sensoren ungültig" hätte einen halb defekten Speicher ganz stillgelegt, obwohl er
  die andere Richtung noch sicher fahren kann.
- **Ein gültiger Wert `0` ist eine Sperre, kein Fehler.** Genau so meldet ein Wechselrichter „geht
  gerade nicht". Ein Fallback darüber wäre ein Überschreiben der Hardware.
- **Ein gesunkenes Limit gilt sofort.** Die Rampe darf ein Ziel bremsen, aber nach der
  Rampenrechnung liegt der Sollwert nie über der momentanen Grenze.
- **Der Energy Pilot darf sie nicht überschreiben.** Deshalb verschwinden die beiden
  Maximalvorschläge aus dem Gerätevertrag, statt nur ignoriert zu werden.

Die Entlade-Sofort-Schwelle entfällt, weil die Fälle, die wirklich unverzüglich auf `0 W` müssen —
sicherer Standby, ungültiger Sensor, Richtungswechsel, Netzdefizit — ohnehin **vor** der Rampe
greifen. Die Schwelle war eine zweite, ungenauere Antwort auf dieselbe Frage.

## Folgen

- **Positiv:** Eine Quelle je physischer Grenze. Fünf Sperrgründe weniger, und die verbleibenden
  unterscheiden „Sensor unbrauchbar" (`limit_sensor`) von „Gerät meldet 0" (`wr_derating`). Kein
  magischer Großwert und kein `Infinity` mehr im Status.
- **Negativ:** Brechende Konfigurationsänderung. Ein Speicher ohne die beiden Sensoren wird nicht
  registriert und erscheint als inaktives Gerät. Wer bisher eine Notstromreserve über
  `soc_reserve_prozent` gesetzt hatte, muss sie über `soc_min_prozent` ausdrücken.
- **Aufwand:** MAJOR-Anhebung vor dem nächsten Release; die entfallenen HA-Helfer dürfen gelöscht
  werden.

## Rücknahmebedingung

Ein realer Wechselrichter, der **kein** brauchbares momentanes Limit liefert — etwa weil sein
Register nur den Typenschildwert meldet und nicht auf Temperatur oder SoC reagiert. Dann fehlt der
Regelung die Grenze, die diese Entscheidung voraussetzt, und ein konfigurierter Maximalwert muss
als ausdrücklicher Ersatz zurückkehren. Erkennbar daran, dass `max_ladeleistung_w` im Status über
Stunden konstant bleibt, während der Speicher am SoC-Deckel oder im Derating fährt.
