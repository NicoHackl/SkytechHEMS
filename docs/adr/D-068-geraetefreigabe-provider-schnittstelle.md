# D-068: Speicher über den Schnittstellen-Sensor des Battery-Providers, mit Gerätefreigaben

- **Datum:** 18.10.2026
- **Status:** Aktiv
- **Betrifft:** [`app/ems/devices.py`](../../app/ems/devices.py) (`BatteryDevice`),
  [`app/ems/state.py`](../../app/ems/state.py), [`app/configuration.py`](../../app/configuration.py),
  [`app/ems/controller.py`](../../app/ems/controller.py), [`config.yaml`](../../config.yaml), `web/src/`,
  [Vertrag HEMS ↔ Battery-Provider 1.2](../../contract/contract_hems_battery_provider/contract_hems_battery_provider.md)

## Kontext

Am 18.10.2026 von 09:01 bis 09:16 forderte das HEMS beim Marstek `acspeicher1` eine Entladung von
bis zu 2320 W an. Der Battery-Provider sendete sie, der Speicher bestätigte sie und entlud nicht
(Shelly: rund 8 W Leerlauf). Das trat in den drei Tagen davor nur bei 12–15 % SoC auf, nachdem der
Speicher vom Boden aus wieder geladen hatte. Weil der Marstek Entladepriorität 1 hat und 2500 W
abgeben darf, bekam er das ganze Hausdefizit; der E3DC (Priorität 10) bekam 0 W, das Netz deckte
den Bedarf. Das HEMS hatte keine Möglichkeit, eine Sperre des Geräts zu erkennen.

Der Battery-Provider liest seit seiner D-017 die Lade-/Entladefreigabe direkt am Gerät und
veröffentlicht sie zusammen mit SoC, Ist-Leistung und dem Spiegel der HEMS-Anforderung in einem
Schnittstellen-Sensor.

## Betrachtete Optionen

- **Ein Feld `provider_entity`, das die Einzel-Eingänge ersetzt.** Gewählt (Entscheidung des Users).
  Eine Stelle für alles, was zwischen HEMS und Provider fließt; Messwert und Freigabe kommen aus
  demselben Poll.
- **Zwei zusätzliche Felder für je einen Freigabe-`binary_sensor`.** Verworfen: mehr Konfiguration
  je Speicher, und die Zusammengehörigkeit von Messwert und Freigabe ginge verloren.
- **Automatisch über eine Namenskonvention suchen.** Verworfen: Die Entity-IDs vergibt Home
  Assistant; an der Anlage heißt der Provider-Präfix `ac_speicher_1`, der HEMS-Präfix `acspeicher1`.
- **Sperre aus „Soll angefordert, Ist bleibt 0“ ableiten.** Verworfen: erkennt die Folge, nicht die
  Ursache, und braucht eine geratene Wartezeit.

## Entscheidung

1. Neues optionales Feld `provider_entity` je `class: battery`. Gesetzt liest `BatteryDevice`
   SoC und Ist-Leistung nur aus den Attributen des Sensors (`StateProxy.resolve_attribute_number`,
   ohne Ersatzwert). `soc_entity` und Variante A/B sind dann keine Pflicht und wirken nicht auf die
   Regelung; gesetzt dürfen sie bleiben (Flow-Card, Data Insight).
2. Gültig ist der Sensor nur mit einem bekannten Zustand (`bereit`, `laden_gesperrt`,
   `entladen_gesperrt`, `gesperrt`) und `schnittstelle_version` 1. Alles andere, auch `getrennt`,
   macht die Messwerte ungültig: Sperrgrund `sensor_ungueltig`, `0 W` und `standby`.
3. `laden_freigegeben: false` → Sperrgrund `geraet_laden_gesperrt`, `entladen_freigegeben: false`
   → `geraet_entladen_gesperrt`, jeweils direkt nach der Hausleistungsbilanz geprüft. Die
   Entladekapazität wird `0`, `_allocate_discharge` gibt das Defizit an den nächsten Speicher.
   Der Controller bleibt unverändert.
4. Eine Freigabe ohne Angabe (`null`, fehlend, kein Bool) gilt als erlaubt (Entscheidung des Users).
5. Ohne `provider_entity` ist das Verhalten bit-identisch zu vorher.

## Folgen

- **Positiv:** Sperrt ein Speicher eine Richtung, übernimmt der nächste. Die Statuskarte zeigt die
  Sperre mit Ursache („Speicher sperrt Entladen (Notstromreserve erreicht)“).
- **Negativ:** Ob der Marstek die Verweigerung vom 18.10.2026 tatsächlich als
  `entladen_freigegeben: false` meldet, ist noch nicht an Hardware bestätigt. Bis dahin soll
  `provider_entity` an der Anlage erst nach einem Blick in die History gesetzt werden. Der Energy
  Pilot kennt das Feld nicht (`device_controls_schema` unverändert); `soc_entity` sollte für ihn
  gesetzt bleiben.
- **Aufwand:** Zwei Resolver in `state.py`, ein Lesepfad und zwei Sperrgründe in `BatteryDevice`,
  ein Formularfeld und eine Statuszeile.

**Nachtrag 19.10.2026:** Der Test des Users bestätigt, dass der Marstek seine Entladesperre
nicht über `dischrg_flag` meldet. Der Soll/Ist-Vergleich läuft auf Wunsch des Users im Provider
(Provider D-018, Vertrag 1.3): Er meldet eine nicht umgesetzte Richtung als
`entladen_freigegeben: false` mit Sperrgrund `keine_reaktion_entladen`. Im HEMS ändert sich an
der Regelung nichts, nur die Statuskarte kennt die neuen Sperrgründe.

## Rücknahmebedingung

Meldet das Gerät eine Sperre nicht zuverlässig (Freigabe `true`, Ist bleibt bei angeforderter
Entladung 0), trägt die Freigabe allein nicht. Dann ist ein Abgleich Soll gegen Ist zu entscheiden.
