# D-056: SoC-abhängige Maximal-Ladestufen für AC-Speicher

- **Datum:** 29.09.2026
- **Status:** Aktiv
- **Betrifft:** [`app/ems/devices.py`](../../app/ems/devices.py),
  [`web/src/pages/Status.tsx`](../../web/src/pages/Status.tsx),
  [device_classes/battery.md](../device_classes/battery.md),
  [datenmodell.md](../datenmodell.md)

## Kontext

Die bestehende E3DC-Regelung dieser Anlage steuert den Hausspeicher über einen HA-Template-Sensor
mit zwei fest verdrahteten SoC-Stufen (`ems_speicher_soc_mindestwert_1/2`,
`ems_speicher_mindesladeleistung_1/2`, Schalter nur für Stufe 1). Ab einer SoC-Schwelle bekommt
der Speicher nur noch einen Teil des Überschusses, der Rest geht an die Verbraucher.

Für HEMS-Speicher (`class: battery`) gab es nichts Vergleichbares: ein Speicher mit hoher
Ladepriorität nimmt bis `available_charge_power_w` alles, auch wenn er fast voll ist und über den
Tag ohnehin voll würde.

## Entscheidung

- Optional je Speicher beliebig viele Ladestufen aus je drei HA-Helfern:
  `input_boolean.ems_<prefix>_ladestufe_<n>_aktiv`,
  `input_number.ems_<prefix>_ladestufe_<n>_soc_prozent`,
  `input_number.ems_<prefix>_ladestufe_<n>_max_ladeleistung_w`.
- Eingelesen wird ab `n = 1` bis zur ersten Lücke, höchstens 20 Stufen. Eine Stufe mit fehlendem,
  ausgefallenem oder ungültigem Helfer gilt als Lücke; die Liste endet dort. Ein Schalter `off`
  ist keine Lücke.
- Es greifen alle eingeschalteten Stufen mit SoC ≥ Schwelle; das **kleinste** Maximum gewinnt.
  Es begrenzt die maximale Ladeleistung zusätzlich zu `available_charge_power_w`.
- Keine SoC-Hysterese. Sinkt das Limit, gilt es sofort; steigt es, laufen Regelzeit und Rampe.
- Ein Stufenmaximum von `0 W` sperrt das Laden mit dem neuen Sperrgrund `ladestufe`.
- Die Helfer stehen nicht im Steuerschema; der Energy Pilot liefert noch keine Vorschläge.

## Betrachtete Alternativen

- **Mindestladeleistung wie beim E3DC:** verworfen. Das HEMS verteilt nach Priorität; eine
  Obergrenze am Speicher ergibt dieselbe Wirkung (Überschuss geht weiter), ohne den
  Verteilalgorithmus zu ändern.
- **Höchste erreichte Schwelle gewinnt:** verworfen. Das Ergebnis hinge von der Reihenfolge der
  Stufen ab; das kleinste Maximum ist eindeutig und die strengere Grenze.
- **Alle HA-States nach dem Muster scannen (Lücken erlaubt):** verworfen zugunsten des einfachen,
  deterministischen Hochzählens.
- **Ausgefallener Schalter gilt als aktiv:** verworfen. Eine unvollständige Stufe ist ein
  Konfigurationsfehler und wird sichtbar gemacht statt still ergänzt.

## Folgen

- Fällt ein Helfer einer frühen Stufe aus, wirken auch alle späteren Stufen nicht; das Limit kann
  dadurch **steigen**. Die Statuskarte zeigt den Abbruch mit Stufe und Entität.
- Die Anzahl der Stufen ist dynamisch; die Stufen-Helfer erscheinen nur in `entity_diagnostics`
  und im Speicherstatus, nicht in der Helferliste des Steuerschemas.

## Ausblick

Später soll der Energy Pilot die Ladestufen und `min_ladeleistung_w` aller Speicher anhand der
Prognose setzen und so Leistung für Überschussverbraucher freigeben, sobald feststeht, dass die
Speicher über den Tag voll werden. Das ist nicht Teil dieser Entscheidung.
