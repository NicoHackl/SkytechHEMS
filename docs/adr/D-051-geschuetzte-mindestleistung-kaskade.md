# D-051: Geschützte Mindestleistung wahlweise in die regelbare Kaskade einbeziehen

- **Datum:** 03.09.2026
- **Status:** Aktiv
- **Betrifft:** [`app/ems/controller.py`](../../app/ems/controller.py),
  [`app/ems/devices.py`](../../app/ems/devices.py), [`app/configuration.py`](../../app/configuration.py),
  [`config.yaml`](../../config.yaml) und `web/src/`

## Kontext

Die geschützte Mindestleistung eines regelbaren Geräts reservierte bislang nur Leistung vor
nachfolgenden Binärverbrauchern. Bei mehreren regelbaren Verbrauchern erhielt danach jedoch immer
das höher priorisierte Gerät die gesamte Zusatzleistung bis zur technischen Obergrenze; ein
niedriger priorisierter Schutzsockel hatte dort keine Wirkung.

Für unterschiedliche Anlagen sind beide Strategien sinnvoll. Eine Bestandsanlage darf sich durch
ein Update nicht stillschweigend anders verhalten. Zugleich muss eine Anlage mit mehreren
regelbaren Verbrauchern die geschützten Sockel nacheinander absichern können. Binärgeräte behalten
in jedem Fall Hysterese, Mindestlaufzeit, Mindestauszeit und Abschaltverzögerung.

## Betrachtete Optionen

### Option A — Schutz immer nur gegen Binärgeräte beibehalten

- Dafür: vollständig bit-identisches Bestandsverhalten.
- Dagegen: ein Schutzsockel eines niedrig priorisierten regelbaren Verbrauchers kann von der
  Zusatzleistung eines höher priorisierten Verbrauchers vollständig verdrängt werden.

### Option B — Schutz immer auch zwischen regelbaren Verbrauchern anwenden

- Dafür: einfache, einheitliche Lesart des Begriffs „geschützt".
- Dagegen: jede Bestandsanlage ändert ihr Betriebsverhalten ohne aktive Entscheidung des Nutzers.

### Option C — Geltungsbereich als globale Add-on-Option wählen (gewählt)

- Dafür: `binary_only` bewahrt den bisherigen Pfad, `binary_and_controllable` stellt die neue
  Prioritätskaskade bewusst und sichtbar bereit. Die Option ist statisch und wird erst nach dem
  Add-on-Neustart wirksam; der Wechsel kann deshalb laufende Sollwerte nicht mitten im Zyklus
  umdeuten.
- Dagegen: zwei fachliche Verteilmodi müssen dauerhaft getestet und dokumentiert werden.

## Entscheidung

Es gibt die globale Add-on-Option `protected_minimum_scope`:

- `binary_only` ist der Default und erhält das bisherige Verhalten vollständig.
- `binary_and_controllable` ergänzt nach der bestehenden Binärentscheidung einen Schutzdurchlauf
  für regelbare Geräte. Jedes Gerät erhält in Prioritätsreihenfolge zunächst seinen effektiven
  Schutzsockel `schutz_w`; danach fließt verbleibende Leistung erneut nach Priorität bis zur
  technischen Obergrenze.

Der effektive Sockel bleibt geschützte Mindestleistung plus Geräte- und globalem Puffer, an der
technischen Obergrenze geklemmt. Er ist keine zweite technische Einschaltgrenze: Trägt der Pool das
technische Minimum, aber nicht den ganzen Sockel, erhält das Gerät den verfügbaren Teil.

Bei sinkendem Pool berechnet derselbe Ablauf zuerst kleinere Anteile oberhalb der Sockel. Reicht
das nicht, fällt der niedrigste regelbare Teilnehmer unter seinen Sockel. Binärgeräte werden
weiterhin ausschließlich durch ihre prioritäts- und zeitgeschützte Wunschentscheidung geschaltet.
Bei `battery` betrifft der Modus nur die Ladeallokation; die Entladepriorität bleibt getrennt.

## Folgen

- **Positiv:** Mehrere regelbare Verbraucher können ihren Mindestanteil in klarer Prioritätsfolge
  halten. Die drei konkreten Verteilungs- und Abregelfälle sind als Zyklus-Regressionstests
  abgebildet.
- **Negativ:** Die Konfiguration muss die passende Regelstrategie explizit auswählen; der
  erweiterte Modus ist anspruchsvoller zu erklären als eine einzige starre Regel.
- **Aufwand:** Add-on-Schema, Ingress-Auswahl, Validierung, Controller, Gerätevertrag,
  Property-Tests und Dokumentation werden gemeinsam gepflegt.

## Rücknahmebedingung

Die Entscheidung wird überprüft, wenn der erweiterte Modus in einer realen Anlage trotz korrekter
Prioritäten zu wiederholtem Hin- und Herschalten führt oder wenn Nutzer den Unterschied der beiden
Modi regelmäßig nicht nachvollziehen können. Dann muss die Kaskade anhand realer Messreihen
vereinfacht oder die Auswahl um eine eindeutigere fachliche Strategie ergänzt werden.
