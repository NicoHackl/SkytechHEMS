# Globale Entitäten und gemeinsame Gerätefelder

Diese Seite ist die verbindliche Referenz für globale Add-on-Optionen, globale
Home-Assistant-Entitäten und die gemeinsame Basis aller Geräteklassen. Die klassenspezifischen
Verträge stehen in:

- [Regelbares Gerät (`controllable`)](controllable.md)
- [Binäres Gerät (`binary`)](binary.md)
- [AC-Speicher (`battery`)](battery.md)

## Zwei Konfigurationsebenen

Das HEMS bezieht seine Konfiguration aus zwei voneinander getrennten Ebenen:

1. **Add-on-Konfiguration:** statische Struktur, Gerätezuordnung und Namen externer Sensoren. Eine
   Änderung wird erst nach einem Add-on-Neustart wirksam.
2. **HA-Helfer:** zur Laufzeit änderbare Freigaben, Grenzen und Regelparameter. Das Add-on legt
   diese Entitäten nicht an.

Ein Default im Python-Code ersetzt keinen dauerhaft angelegten HA-Helfer. Er beschreibt nur das
Verhalten bei einem fehlenden oder ungültigen State. Alle als Pflicht markierten Helfer müssen in
Home Assistant existieren.

## Namenskonvention

Gerätebezogene Helfer folgen immer diesem Schema:

```text
<domain>.ems_<prefix>_<suffix>
```

`<prefix>` kommt aus `devices[].entity_prefix`; fehlt das Feld, wird `devices[].name` verwendet.
Erlaubt sind Kleinbuchstaben, Ziffern und Unterstriche. `label` hat keinen Einfluss auf die
Entitätsnamen.

## Gemeinsame Felder in `devices[]`

| Feld | Für Geräteklasse | Pflicht | Default | Funktion |
|---|---|---:|---|---|
| `name` | alle | ja | – | Stabile technische Geräte-ID; wird ohne `entity_prefix` zugleich zum Präfix |
| `class` | alle | ja | – | `controllable`, `binary` oder `battery` |
| `label` | alle | nein | Wert von `name` | Anzeigename; darf Leerzeichen und Umlaute enthalten |
| `entity_prefix` | alle | nein | Wert von `name` | Überschreibt ausschließlich das Präfix der HEMS-Helfer |
| `allowed_modes` | alle | nein | `manuell` | Kommagetrennte globale Regelmodi, in denen normale Nutzerregeln wirken; zulässig sind `manuell`, `nur_heizen` und `nur_laden`. Der Alt-Wert `auto` wird auf `manuell` abgebildet |

Ein fehlendes `name` oder eine unbekannte `class` führt dazu, dass nur dieser Geräteeintrag mit
einer Fehlermeldung übersprungen wird.

## Gemeinsame HA-Helfer

Diese vier Helfer werden von jeder Geräteklasse gelesen:

| Entität | Werte | Pflicht | Verhalten bei fehlendem State | Funktion |
|---|---|---:|---|---|
| `input_boolean.ems_<prefix>_freigabe` | `on`, `off` | ja | `off` | Bedienfreigabe; im EP-Modus zugleich Fallback für den EP-Freigabevorschlag |
| `input_boolean.ems_<prefix>_technische_freigabe` | `on`, `off` | ja | `off` | Hartes technisches Gate, das auch im EP-Modus gilt |
| `input_select.ems_<prefix>_modus` | `auto`, `manuell`, `aus` | ja | außerhalb des globalen EP-Modus wie `manuell` | `auto` übernimmt gültige EP-Vorschläge, `manuell` nutzt HA-Helferwerte, `aus` ist der gerätespezifische Kill-Switch |
| `input_number.ems_<prefix>_prioritat` | ganze Zahl | ja | `99` | Lade- beziehungsweise Verbraucherpriorität; kleinere Zahl wird zuerst bedient |

Die Bedienfreigabe und die technische Freigabe müssen beide wirksam sein. Zusätzlich müssen die
globale Freigabe, der globale Modus und `allowed_modes` das Gerät zulassen.

## Globale HA-Helfer

Der Regelzyklus liest diese Entitäten. Er schreibt keine globale HA-Entität selbst; Änderungen in
der Oberfläche laufen als explizite Nutzeraktion über `/api/set`.

| Entität | Werte/Einheit | Pflicht | Verhalten bei fehlendem State | Funktion |
|---|---|---:|---|---|
| `input_boolean.ems_pv_regelung_aktiv` | `on`, `off` | ja | `off` | Hauptschalter der gesamten Regelung |
| `input_select.ems_regelmodus` | `auto`, `manuell`, `nur_heizen`, `nur_laden`, `aus` | ja | `aus` | Globale Steuerquelle und Betriebsart; `auto` aktiviert den Energy Pilot |
| `input_number.ems_globaler_puffer_w` | W | ja | `0` | Zusätzliche Reservierung für jedes regelbare Gerät einschließlich AC-Speicher beim Laden |
| `input_number.ems_einschaltreserve_global_w` | W | ja | `0` | Globaler Hysterese-Aufschlag für binäre Geräte |
| `input_number.ems_ac_speicher_entlade_abschlag_w` | W | nur mit `battery` | `0` | Systemweiter Restbezug; wird einmal vom gesamten Entladeziel abgezogen, nicht je Speicher |
| `input_boolean.ems_pyems_debug_output` | `on`, `off` | nein | `off` | Schaltet ausführliches Zyklus-Logging ohne Neustart |

### Externe globale HA-Entitäten

| Add-on-Feld | Richtung | Pflicht | Funktion |
|---|---|---:|---|
| `residual_power_entity` | lesen | ja, Feld hat einen Default | Überschuss-Sensor und zentrale Messgröße des Regelzyklus |
| `post_cycle_script` | `script.turn_on` aufrufen | nein | Nach jedem erfolgreichen Zyklus ausgeführtes HA-Skript; ein Fehler wird geloggt und macht den Regelzyklus nicht nachträglich ungültig |

#### Überschuss-Sensor

Der über `residual_power_entity` konfigurierte Sensor wird global gelesen:

- positiver Wert: Einspeisung beziehungsweise verfügbarer PV-Überschuss;
- negativer Wert: Netzbezug;
- `unknown`, `unavailable`, fehlender State oder ein Wert ≤ −50.000 W: Hard-Lockout.

Der Sensor muss die bereits laufenden HEMS-Lasten enthalten. Die genaue Messpunktsemantik steht
in [konfiguration.md](../konfiguration.md#semantik-des-überschuss-sensors).

## Globale Add-on-Optionen

| Feld | Pflicht im Schema | Laufzeit-Default | Für welches Gerät | Funktion beziehungsweise Bezug zu HA |
|---|---:|---|---|---|
| `interval_s` | ja | `30` | alle | Abstand der Regelzyklen in Sekunden, zulässig `1` bis `300`; kein HA-Helfer-Fallback |
| `log_level` | ja | `info` | alle | Prozess-Log-Level; unabhängig von `input_boolean.ems_pyems_debug_output` |
| `post_cycle_script` | nein | leer | alle | Optionales `script.<name>`, das nach einem erfolgreichen Regelzyklus gestartet wird |
| `residual_power_entity` | nein | `sensor.verfugbare_leistung_fur_uberschussverbraucher` | alle | Vollständige Entity-ID des Überschuss-Sensors; dies ist eine Entity-Zuordnung, kein Ersatzwert für einen HA-State |
| `speicher_in_residual_enthalten` | nein | `true` | `battery` | Legt fest, ob gemessene Speicherentladung vor der Pool-Berechnung vom Überschuss-Sensor abgezogen wird |
| `devices` | ja | Manifest enthält Beispielgeräte; Laufzeit ohne Feld: leere Liste | alle | Liste der Geräteinstanzen und ihrer klassenspezifischen Felder |

### Tatsächliche Add-on-Fallbacks für HA-Entitäten

Nur ein klassenspezifisches Add-on-Feld ersetzt unmittelbar einen fehlenden HA-Helferwert:
`phase_switch_delay_s` bei einem mehrphasigen `controllable`-Gerät. Details stehen in
[controllable.md](controllable.md#fallbacks-und-interne-defaults).

`entity_prefix` fällt auf `name` zurück, erzeugt damit aber lediglich Entitätsnamen. Es liefert
keinen State und legt keine HA-Entität an. Alle anderen fehlenden HA-Werte verwenden interne
Sicherheitsdefaults, die in den Klassenseiten dokumentiert sind.

## Energy-Pilot-Vertrag

Im globalen Regelmodus `auto` oder im Gerätemodus `auto` liest das HEMS zusätzlich
`sensor.ep_<prefix>_<feld>_vorschlag`. Ein Vorschlag wird nur verwendet, wenn State und Attribute
zu diesem Commit-Marker passen:

```text
sensor.ep_plan_commit
```

Der Commit-State enthält `plan_id`; seine Attribute enthalten `valid_from` und `valid_until`.
Fehlt ein gültiger Vorschlag, verwendet das HEMS den entsprechenden HA-Helferwert. Das ist ein
**EP-zu-HA-Fallback**, kein Add-on-Konfigurationsfallback. Die klassenspezifischen Vorschlagsfelder
stehen auf den jeweiligen Klassenseiten.

Diese beiden globalen EP-Sensoren werden ausschließlich für die Anzeige über `/api/ep` gespiegelt
und beeinflussen die Regelung nicht:

```text
sensor.ep_plan_status
sensor.ep_hems_verbindung
```
