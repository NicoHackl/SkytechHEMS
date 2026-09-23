# D-054: Einschaltverzögerung für Binärgeräte über `ems_<prefix>_einschaltverzogerung_s`

- **Datum:** 23.09.2026
- **Status:** Aktiv
- **Betrifft:** [`app/ems/devices.py`](../../app/ems/devices.py),
  [`app/ems/controller.py`](../../app/ems/controller.py),
  [`app/configuration.py`](../../app/configuration.py), [`app/main.py`](../../app/main.py),
  `web/src/`, [device_classes/binary.md](../device_classes/binary.md) und der Statusvertrag in
  [datenmodell.md](../datenmodell.md)

## Kontext

Ein binäres Gerät schaltete ein, sobald der Pool an seiner Prioritätsposition die
Einschaltschwelle erreichte. Gebremst hat nur die Mindestauszeit — die aber misst die Zeit seit
dem letzten Schalten, nicht die Dauer des Überschusses. Eine kurze Wolkenlücke reichte, um einen
Heizlüfter anlaufen zu lassen, der Sekunden später wieder in der Abschaltverzögerung hing.

Gewünscht war das Gegenstück zur Abschaltverzögerung: Der Überschuss muss eine einstellbare Zeit
anliegen, bevor eingeschaltet wird. Ausdrücklich **ohne** die Bedienfreigabe: Wer die Freigabe
einschaltet, während der Überschuss schon länger anliegt, soll nicht noch einmal warten.

## Entscheidung

- Neuer optionaler Helfer `input_number.ems_<prefix>_einschaltverzogerung_s`, Add-on-Fallback
  `on_delay_s` **optional mit Default `0`** — Bestandskonfigurationen bleiben aktiv und verhalten
  sich unverändert.
- Die Zeit misst die **Einschaltbedingung**: kein Zwang, Steuerquelle nicht `aus`, technische
  Freigabe an, Schreibziel gesund, Pool an der Prioritätsposition ≥ Einschaltschwelle. Fällt
  etwas davon weg, beginnt sie von vorn. Die wirksame Bedienfreigabe (Nutzerschalter oder
  EP-Vorschlag) ist bewusst ausgenommen.
- Bei Freigabe `off` wird die Bedingung nur hypothetisch geprüft, ohne Leistung zu reservieren.
  Bei Freigabe `on` reserviert das Gerät während der Wartezeit seine Leistung — wie bisher
  während einer laufenden Mindestauszeit.
- Mindestauszeit und Einschaltverzögerung laufen parallel, nicht nacheinander.
- Hat ein Zwang-Ende (D-053) das Gerät ausgeschaltet, entfällt neben der Mindestauszeit auch die
  Einschaltverzögerung bis zum ersten regulären Einschalten.

## Betrachtete Alternativen

- **Pflichtfeld wie `off_delay_s`:** verworfen — jedes Bestandsgerät wäre nach dem Update beim
  Start inaktiv geworden, bis das Feld gepflegt ist.
- **Mindestauszeit und Verzögerung nacheinander:** verworfen — verlängert die Wartezeit ohne
  Mehrwert; beide Guards beantworten verschiedene Fragen und dürfen gleichzeitig laufen.
- **Keine Reservierung während der Wartezeit:** verworfen — ein niedriger priorisiertes
  Binärgerät könnte den Überschuss übernehmen und das höher priorisierte dauerhaft aushungern.

## Folgen

- Status je Binärgerät um `on_delay_s` und `on_delay_remaining_s` erweitert (`null`, solange
  keine Wartezeit läuft).
- Der Timer lebt nur im Speicher des Add-ons; nach einem Neustart beginnt die Wartezeit neu.
- „Sofort einschalten" bei Freigabe heißt: im selben Zyklus Kandidat AN. One-Change-Limit und
  Prioritätskaskade gelten weiterhin.
