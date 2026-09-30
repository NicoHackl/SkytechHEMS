# D-058: Totzone um Null am Speicher nur beim Start aus Standby

- **Datum:** 30.09.2026
- **Status:** Aktiv
- **Betrifft:** [`app/ems/devices.py`](../../app/ems/devices.py),
  [device_classes/battery.md](../device_classes/battery.md),
  [datenmodell.md](../datenmodell.md)

## Kontext

`BatteryDevice.calculate_ramp` setzte jedes Nettoziel mit `|netto| < umschalt_totzone_w` auf
`0` und fuhr den Speicher in `standby` — unabhängig davon, ob er gerade stand oder lief. Ein
Speicher, der mit 100 W lud und im nächsten Zyklus nur noch 45 W bekommen sollte, fiel bei einer
Totzone von 75 W hart auf 0 W. Um wieder anzulaufen, musste das Ziel erneut die Totzone
überschreiten.

## Entscheidung

- Die Totzone verhindert nur das **Verlassen von 0 W**. Steht der Speicher (`standby`), führt ein
  Nettoziel unterhalb der Totzone weiter zu `standby`.
- Läuft der Speicher bereits in der Richtung des Ziels (Laden bzw. Entladen, bestimmt aus dem
  aktuellen Sollwert), gilt die Totzone nicht; das Ziel darf darunter sinken.
- Ein Ziel in der **Gegenrichtung** zählt wie ein Start aus 0: liegt es innerhalb der Totzone,
  fährt der Speicher `standby`.
- Mindeständerung (`min_anderung_pro_schritt_w`), Regelzeiten, Schrittbegrenzung und
  `min_lade-/entladeleistung_w` bleiben unverändert und greifen danach wie bisher.
- Regelbare Geräte (Heizstab, Wallbox) haben keine Totzone und sind nicht betroffen.

## Betrachtete Alternativen

- **Totzone auch beim Richtungswechsel aussetzen:** verworfen. Ein kleines Ziel in der
  Gegenrichtung wäre ein Start aus 0 und würde den Speicher um den Netzpunkt pendeln lassen.
- **Neue Totzone für regelbare Geräte:** verworfen. Dort übernimmt die Mindeständerung beim Start
  aus 0 diese Aufgabe bereits.

## Folgen

- Die Totzone wirkt jetzt als Hysterese: Einschalten ab der Totzone, Weiterlaufen bis knapp über
  0 W.
- Kleine Restleistungen bleiben stehen, bis das Ziel auf 0 fällt oder Mindeständerung bzw.
  Mindestleistung sie verhindern.
