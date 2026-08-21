# Datenmodell

Das Add-on hat **keine eigene Persistenz**. Zustand lebt an zwei Orten: in den HA-Helfer-Entitäten
(überlebt Neustarts) und im Speicher der Geräteobjekte (Timer, überlebt keinen Neustart). Dieses
Dokument beschreibt Identität und Statusverträge. Die vollständigen Pflichtfelder, Leserichtungen,
Schreibrichtungen und Fallbacks der HA-Entitäten stehen in [device_classes/](device_classes/global.md).

## Identitäten

| Bezeichner | Bedeutung | Vergeben von | Unveränderlich |
|---|---|---|---|
| `name` | Technische Geräte-ID aus den Add-on-Optionen; erscheint als `id` in `/api/status` und als `name` im Steuerschema | User (Konfiguration) | ja — ein Rename ist eine Neuanlage |
| `entity_prefix` | Präfix der HA-Helfer, per Default `name` | User (Konfiguration) | ja |
| `label` | Reiner Anzeigename | User (Konfiguration) | nein — darf sich jederzeit ändern |

Grundsatz: Konsumenten machen die Identität am `name` fest und zeigen nur das `label` an. Ein
umbenanntes Label darf keine Zuordnung brechen.

Erlaubte Zeichen in `name` und `entity_prefix`: Kleinbuchstaben, Ziffern, Unterstrich — sie fließen
unverändert in Entitätsnamen ein. Beide müssen je Anlage **eindeutig** sein; zwei Geräte mit
demselben effektiven Präfix schrieben sonst auf dieselben Helfer.

## HA-Helfer — Namenskonvention

```text
<domain>.ems_<prefix>_<suffix>
```

`<domain>` ist `input_boolean`, `input_select` oder `input_number`. Das Add-on legt die Helfer
nicht an.

Für die **Eingangswerte** von `controllable` und `binary` gibt es je ein verpflichtendes Feld in
der Add-on-Konfiguration, das bei fehlender, nicht verfügbarer oder unbrauchbarer Entität greift —
siehe [Add-on-Fallbacks](device_classes/global.md#add-on-fallbacks-für-ha-entitäten). Die
**Ausgabe**-Helfer (`anforderung_*`, `anzahl_phase`) haben keinen Fallback: ein Sollwert lässt sich
nicht erfinden.

Die Tabellen in diesem Abschnitt sind eine Übersicht. Kanonische Detailreferenz sind die Seiten
für [globale Werte](device_classes/global.md), [regelbare Geräte](device_classes/controllable.md),
[binäre Geräte](device_classes/binary.md) und [AC-Speicher](device_classes/battery.md).

### Global

| Entität | Domain | Werte | Pflicht | Funktion |
|---|---|---|---|---|
| `input_boolean.ems_pv_regelung_aktiv` | `input_boolean` | `on` / `off` | ja | Globaler Schalter der gesamten Regelung |
| `input_select.ems_regelmodus` | `input_select` | `auto`, `manuell`, `nur_heizen`, `nur_laden`, `aus` | ja | Globaler Regelmodus. `auto` = KI-Übernahme, `manuell` = normale Regeln, `aus` = aus |
| `input_number.ems_globaler_puffer_w` | `input_number` | Watt | ja | Zusätzlich reservierte Leistung je regelbarem Gerät |
| `input_number.ems_einschaltreserve_global_w` | `input_number` | Watt | ja | Hysterese-Aufschlag für alle binären Geräte |
| `input_number.ems_ac_speicher_entlade_abschlag_w` | `input_number` | Watt | nur mit Speicher | Bewusster Unterschuss der Speicherentladung, **einmal systemweit** angewandt (nicht je Speicher). Empfehlung bei `interval_s = 3`: 20 W |
| `input_boolean.ems_pyems_debug_output` | `input_boolean` | `on` / `off` | nein | Ausführliches Zyklus-Logging zur Laufzeit |

### Je Gerät, beide Klassen

| Entität | Domain | Funktion |
|---|---|---|
| `input_boolean.ems_<prefix>_freigabe` | `input_boolean` | Bedien-Freigabe |
| `input_boolean.ems_<prefix>_technische_freigabe` | `input_boolean` | Technische Freigabe. Nur wenn **beide** Freigaben `on` sind, wirkt das Gerät mit — hartes Gate in jedem Modus |
| `input_select.ems_<prefix>_modus` | `input_select` | `auto` = EP-Vorschlag für dieses Gerät, `manuell` = normale Regeln, `aus` = Kill-Switch |
| `input_number.ems_<prefix>_prioritat` | `input_number` | Kleinere Zahl = höhere Priorität |

### Regelbare Geräte

`output_unit=watt` → Suffix `_w` und Werte in Watt, `output_unit=ampere` → Suffix `_a` und Werte in
Ampere. `reserve_w` ist **immer** in Watt.

| Suffix | Einheit | Funktion |
|---|---|---|
| `min_technisch_w` / `_a` | W / A | Untere technische Grenze; Sollwerte dazwischen rasten auf `0` oder das Minimum |
| `max_technisch_w` / `_a` | W / A | Obere technische Grenze |
| `geschutzte_mindestleistung_w` / `_a` | W / A | Garantiert reservierter Sockel dieses Geräts |
| `reserve_w` | W | Zusätzlicher Puffer des Geräts |
| `hoch_regelzeit_s`, `runter_regelzeit_s` | s | Mindestabstand zwischen Regelschritten; bei Defizit wird sofort heruntergeregelt |
| `max_anderung_pro_schritt_w` / `_a` | W / A | Maximale Änderung je Zyklus |
| `min_anderung_pro_schritt_w` / `_a` | W / A | Totband — kleinere Änderungen werden nicht geschrieben |
| `min_umschaltzeit_s` | s | Phasenwechsel-Hysterese; Fallback `phase_switch_delay_s`, dann 30 s. Ein gültiger Wert `0` gilt als „keine Sperrzeit" und wird nicht ersetzt |
| `anforderung_leistung_w` / `_a` **(Ausgabe)** | W / A | Vom EMS geschriebener Sollwert, im Ampere-Modus ganzzahlig abgerundet |
| `anzahl_phase` **(Ausgabe)** | 1 oder 3 | Gewählte Phasenzahl, nur bei `phases="1,3"` |

Dazu je Gerät ein externer Ist-Leistungs-Sensor (`actual_power_entity`) und optional die
Spannungssensoren L1/L2/L3.

### Binäre Geräte

| Suffix | Einheit | Funktion |
|---|---|---|
| `leistung_w` | W | Angenommene Leistung im EIN-Zustand |
| `einschaltreserve_w` | W | Hysterese dieses Geräts, zusätzlich zur globalen |
| `mindestlaufzeit_s` | s | Schutz gegen zu frühes Abschalten — gilt **auch** bei Notabschaltung |
| `mindestauszeit_s` | s | Schutz gegen zu frühes Wiedereinschalten |
| `abschaltverzogerung_s` | s | Verzögert den Aus-Befehl; gilt **immer**, auch bei Notabschaltung |
| `anforderung_an` **(Ausgabe, `input_boolean`)** | `on`/`off` | Anforderung des EMS. Eine HA-Automation übersetzt sie in echtes Schalten |

Der reale Schalter (`switch_entity`) wird nur gelesen — daraus stammen `actual_on` und die
Schaltdauer.

### AC-Speicher (`class: battery`)

Ein Speicher ist das einzige Gerät, das Leistung auch **abgeben** kann. Er nutzt die gemeinsamen
Helfer (Freigabe, technische Freigabe, Modus, Priorität) und die geerbten Regelparameter der
regelbaren Geräte (`hoch_regelzeit_s`, `runter_regelzeit_s`, `max_anderung_pro_schritt_w`,
`min_anderung_pro_schritt_w`, `geschutzte_mindestleistung_w`, `reserve_w`) — dazu diese eigenen:

| Suffix | Einheit | Default | Funktion |
|---|---|---|---|
| `entlade_prioritat` | – | 50 | **Reihenfolge beim Entladen, unabhängig von `prioritat`.** Kleiner = zuerst; bei Gleichstand entscheidet die Reihenfolge in der Add-on-Konfiguration |
| `max_ladeleistung_w`, `min_ladeleistung_w` | W | – / 0 | Grenzen des Ladepfads. Unterhalb der Mindestleistung wird auf 0 gerastet, nicht überschossen |
| `max_entladeleistung_w`, `min_entladeleistung_w` | W | – / 0 | Grenzen des Entladepfads |
| `soc_min_prozent` | % | 10 | Entladeschluss (Tiefentladeschutz) |
| `soc_max_prozent` | % | 100 | Ladeschluss |
| `soc_reserve_prozent` | % | 0 | Notstromreserve; darunter entlädt das HEMS nicht mehr |
| `soc_taper_band_prozent` | % | 5 | Drosselband vor der Grenze; bildet die CV-Phase des Geräts nach |
| `soc_max_hysterese_prozent` | % | 2 | Wiedereinstiegsschwelle unter `soc_max`. Ohne sie flippt der Speicher bei 100 % im Takt |
| `entlade_sofort_schwelle_w` | W | 300 | Ab dieser Absenkung wird ungerampt zurückgenommen — echter Lastabwurf. Kleinere Absenkungen werden gedämpft, sonst wird aus Sensor-Versatz ein Grenzzyklus |
| `umschalt_totzone_w` | W | 100 | Totzone um 0; ein Netto-Wunsch darunter führt zu `standby` und verhindert Mikrozyklen |
| `min_umschaltzeit_s` | s | 300 | Sperrzeit nach einem Richtungswechsel. In der Sperrzeit wird `standby` gefahren, **nicht** die alte Richtung fortgesetzt |
| `netzlade_leistung_w` | W | 0 | Reservierte, noch nicht sicher freigegebene Netzlade-Schnittstelle; muss wegen [B-4](bekannte-luecken.md#offene-bugs) auf `0` bleiben |
| `netzlade_soc_ziel_prozent` | % | 0 | Nur im Entwurf vorhanden; wird vom aktuellen Code nicht gelesen |
| `anforderung_leistung_w` **(Ausgabe)** | W | – | **Ein signierter Sollwert: + laden / − entladen.** Der Helfer braucht ein **negatives Minimum** |
| `anforderung_betriebsart` **(Ausgabe, `input_select`)** | – | – | `laden` / `entladen` / `standby` |

Dazu drei Schalter und eine Auswahlliste:

| Entität | Werte | Funktion |
|---|---|---|
| `input_boolean.ems_<prefix>_laden_erlaubt` | `on`/`off` | Ladepfad freigeben |
| `input_boolean.ems_<prefix>_entladen_erlaubt` | `on`/`off` | Entladepfad freigeben |
| `input_boolean.ems_<prefix>_netzladen_aktiv` | `on`/`off` | Reserviert; entgegen der früheren Annahme nicht hart gesperrt und daher bis zur Behebung von [B-4](bekannte-luecken.md#offene-bugs) zwingend `off` |
| `input_select.ems_<prefix>_betriebsart` | `auto`, `nur_laden`, `nur_entladen`, `standby` | Was das HEMS überhaupt darf |

Externe Sensoren je Speicher: `soc_entity` (Pflicht) und entweder `charge_power_entity` **und**
`discharge_power_entity` (beide ≥ 0) oder ein signierter `power_entity` mit `power_sign`.
Optional `available_charge_power_entity` / `available_discharge_power_entity` für das momentane
Geräte-Limit — sie haben Vorrang vor `max_ladeleistung_w` bzw. `max_entladeleistung_w`.

Fehlt einer der Messwerte (`unavailable`), fällt genau dieser Speicher aus der Regelung und geht
auf `standby`; die übrigen laufen weiter. Ohne Ist-Leistung wäre die Pool-Bereinigung blind.

> **Namensraum:** In dieser Anlage ist `ems_speicher_*` bereits von einer eigenen
> HA-Automation für den vorhandenen E3DC belegt. Der HEMS-Speicher benutzt deshalb `acspeicher1`
> als Präfix. Der E3DC selbst ist **kein** HEMS-Gerät (D-040).

### Externe, nur gelesene Entitäten

| Entität | Funktion |
|---|---|
| Überschuss-Sensor (`residual_power_entity`) | **Pflicht.** PV-Überschuss in Watt; `unavailable`/`unknown` oder ≤ −50 000 W löst Hard-Lockout aus. Semantik: [konfiguration.md](konfiguration.md) |
| `actual_power_entity` je regelbarem Gerät | Ist-Leistung in Watt |
| `switch_entity` je binärem Gerät | Tatsächlicher Schaltzustand |
| `voltage_l1/l2/l3_entity` | Phasenspannungen in Volt, Fallback je 230 V |
| `soc_entity` je Speicher | Ladezustand in Prozent |
| `charge_power_entity` / `discharge_power_entity` je Speicher | Ist-Leistung in Watt, beide ≥ 0 |
| `power_entity` + `power_sign` je Speicher | Alternative: eine signierte Entität für beide Richtungen |
| `available_charge_power_entity` / `available_discharge_power_entity` | Momentanes Geräte-Limit, optional |

## Statusvertrag `/api/status`

Erzeuger ist `EMSController.run_cycle()`, Verbraucher sind die eigene Oberfläche **und** der
Energy Pilot. Feldnamen sind damit ein öffentlicher Vertrag.

Global:

| Feld | Typ | Bedeutung |
|---|---|---|
| `ems_enabled` | bool | Globale Freigabe |
| `global_mode` | string | Regelmodus |
| `hard_lockout` | bool | Sperre wegen ungültigem Überschuss-Sensor |
| `global_mode_configured` | bool | `false`, wenn `global_mode` ein normaler, aber global nicht aktivierter Modus ist — der Zyklus bleibt dann sicher inaktiv |
| `available_modes` | Liste | Die aktivierten normalen Regelmodi |
| `residual_sensor_valid` | bool | Sensor lieferte einen brauchbaren Wert |
| `residual_w`, `pool_w`, `current_deficit_w`, `binary_total_w` | float | Leistungen in Watt |
| `residual_bereinigt_w` | float | `residual_w` abzüglich der gemessenen Speicherentladung. **Alle Regelentscheidungen laufen darüber**, nicht über `residual_w` |
| `netz_support_w` | float | Σ gemessene Entladeleistung aller Speicher |
| `hems_last_w` | float | Σ `current_w` — nur vom HEMS angeforderte Last, Force-Modus gefiltert |
| `hems_last_gemessen_w` | float | Σ `gemessene_last_w` — roher Messwert, Force-Modus enthalten |
| `pool_roh_w` | float | Ungeklemmter Pool. Positiv = Überschuss, negativ = Entladebedarf |
| `entlade_basis_w` | float | Basis der Entladeplanung; weicht bei Fremdsteuerung von `pool_roh_w` ab |
| `hausdefizit_w` | float | Hausverbrauchs-Fehlbetrag, den die Speicher decken sollen. **Enthält keine HEMS-Gerätelast**, auch keine fremdgesteuerte |
| `binary_immediate_off` | bool | Notabschaltung binärer Geräte |
| `timestamp` | string | **Maschinenformat** `JJJJ-MM-TT hh:mm:ss`, nicht zur Anzeige gedacht |
| `devices` | Liste | siehe unten |
| `inactive_devices` | Liste | Beim Start übersprungene Geräteeinträge: `index`, `name`, `device_class`, `label`, `errors` (Feldname → deutsche Meldung). Ausdrücklich **ohne** erfundene Ist-, SoC- oder Schaltwerte |

Jedes Gerät trägt zusätzlich `entity_diagnostics`: `{entity_id: {role, state, source}}` mit
`state` aus `valid`/`missing`/`unavailable`/`invalid` und `source` aus `ha`/`addon`/`internal`.
Damit ist beantwortbar, welcher Wert gerade wirkt und warum nicht der aus Home Assistant — siehe
[Doppelte Auflösung](device_classes/global.md#doppelte-auflösung-von-ha-entitäten).

Regelbares Gerät: `type`, `id`, `label`, `priority`, `eligible`, `source`, `actual_w`,
`anforderung_current_w`, `alloc_w`, `new_w`, `schutz_w`, `geschuetzte_mindestleistung_w`,
`output_unit`. Im Ampere-Modus zusätzlich `current_phases`, `allowed_phases`, `voltage_l1..l3`,
`new_a`, `schutz_a`, `geschuetzte_mindestleistung_a` und — solange die Sperre läuft —
`phase_lock_remaining_s`.

Binäres Gerät: `type`, `id`, `label`, `priority`, `eligible`, `source`, `power_w`, `actual_on`,
`anforderung_an`, `desired_on`, `candidate_on`, `final_on`, `in_min_runtime`, `switch_age_s`,
`min_runtime_s`, `min_offtime_s`, `off_delay_remaining_s`.

Speicher (`type: "battery"`): `id`, `label`, `priority` (Laden), `entlade_prioritat`, `eligible`,
`source`, `ep_proposal_status`, `sensoren_gueltig`, `soc_prozent`, `capacity_kwh`, `betriebsart`,
`betriebsart_effektiv`, `lade_ist_w`, `entlade_ist_w`, `lade_anforderung_w`,
`entlade_anforderung_w`, `new_lade_w`, `new_entlade_w`, `netto_w`, `max_ladeleistung_w`,
`max_entladeleistung_w`, `lade_limit_w`, `entlade_limit_w`, `hausdefizit_anteil_w`, `schutz_w`,
`geschuetzte_mindestleistung_w`, `laden_erlaubt`, `entladen_erlaubt`, `netzladen_aktiv`,
`soc_min_prozent`, `soc_max_prozent`, `soc_reserve_prozent`, `umschaltsperre_rest_s`,
`lade_blockiert_grund`, `entlade_blockiert_grund`, `blockiert_grund`. Dazu `energie_kwh`, sofern
`capacity_kwh > 0` konfiguriert ist.

Fallstricke, die schon Fehler verursacht haben:

- **`schutz_w` ist nicht die geschützte Mindestleistung.** `schutz_w` ist der effektive Schutz
  (`Sockel + reserve_w + globaler Puffer`, geklemmt). Der rohe Nutzerwert steht in
  `geschuetzte_mindestleistung_w` bzw. `_a`. Vergleiche gehören gegen den Rohwert.
- **`source`** sagt, woher die wirksamen Werte stammen: `aus`, `user` oder `ep`.
- **`max_ladeleistung_w` ist nicht `lade_limit_w`.** Dieselbe Falle wie bei `schutz_w`: das eine
  ist der Nutzerwert, das andere die Grenze nach SoC-Taper und Geräte-Derating. Vergleiche
  gehören gegen den Rohwert, Anzeigen von Grenzen gegen den effektiven.
- **`netto_w` ist signiert:** positiv = laden, negativ = entladen. Genauso der geschriebene
  Sollwert `anforderung_leistung_w`.
- **Drei Sperrgrund-Felder statt einem.** `lade_blockiert_grund` und `entlade_blockiert_grund`
  beantworten je Pfad „warum passiert gerade nichts", `blockiert_grund` trägt nur die Gründe der
  Richtungsauflösung (`umschaltsperre`, `totzone`). Ein Speicher in `nur_entladen` hat einen
  gesperrten Ladepfad und trotzdem keinen Fehler.
- **`off_delay_remaining_s` ist `null`**, wenn keine Abschaltverzögerung läuft — `0` bedeutet
  „läuft ab", nicht „nicht vorhanden".
- **`eligible: false` ist keine ungültige Konfiguration.** Es ist die aktuelle Freigabeentscheidung
  dieses Zyklus. Ein Gerät, das wegen fehlender Pflichtfelder gar nicht erst registriert wurde,
  steht in `inactive_devices` und taucht in `devices` überhaupt nicht auf.
- Restzeiten sind zum Zyklus-Zeitpunkt gültig. Die Oberfläche zählt zwischen den Zyklen selbst
  herunter, statt eingefrorene Werte zu zeigen.

Zeitangaben für Menschen liefert das Add-on zusätzlich als `last_cycle_at` im Format
`TT.MM.JJJJ hh:mm:ss` (Berliner Zeit, eiserne Regel 9). Das unverändert gebliebene
Maschinenformat steht in `last_cycle_at_iso` und `status.timestamp`.

## Vertrag zum Energy Pilot

Der Energy Pilot ist ein eigenes Add-on. Es gibt **keinen** direkten Aufruf zwischen beiden — der
Austausch läuft ausschließlich über HA-Entitäten:

| Entität | Richtung | Inhalt |
|---|---|---|
| `sensor.ep_plan_status` | EP → HEMS | Gesamtstatus des Plans, Attribute `label`, `valid_until`, `in_window`, `abweichungen` |
| `sensor.ep_hems_verbindung` | EP → HEMS | `online`/`offline`, Attribute `last_cycle_at`, `cycle_count`, `global_mode`, `error` |
| `sensor.ep_<prefix>_<feld>_vorschlag` | EP → HEMS | Vorschlag je Gerät und Feld, Attribute `plan_id`, `valid_from`, `valid_until`, `friendly_name` (`"<Gerät> – <Feld> (Vorschlag)"`) und optional `unit_of_measurement` |
| `sensor.ep_plan_commit` | EP → HEMS | Atomarer Commit-Marker; State = `plan_id`, Attribute `valid_from` und `valid_until`. Nur exakt passende Vorschläge werden übernommen |

Übernommen werden **Priorität**, **Freigabe** und die **geschützte Mindestleistung** (nur
Watt-Geräte), abhängig vom Regelmodus: `auto` → alle Geräte folgen dem Vorschlag; `manuell`,
`nur_heizen`, `nur_laden` → normale Regeln, je Gerät über `input_select.ems_<prefix>_modus`
verfeinerbar. Die technische Freigabe bleibt in jedem Modus hartes Gate, harte Grenzen (min/max,
Lockout) gelten weiter. Fehlt oder stört ein Vorschlag, greift der Nutzerwert — ein KI-Ausfall
blockiert die Anlage nie.

**Verwaiste Vorschläge.** HEMS spiegelt nur und löscht keine HA-Entitäten. Tauscht man im EP einen
Quellsensor, entsteht eine neue `entity_id`, während die alte mit eingefrorenem Wert stehen bleibt.
Die Oberfläche filtert deshalb zweifach: abgelaufene Vorschläge (`valid_until` in der
Vergangenheit) werden ausgeblendet, und bei doppeltem Feld je Gerät bleibt nur der frischere
(späteres `valid_until`).

## Migrationen

Es gibt kein Schema, das migriert werden müsste. Ändert sich der Statusvertrag, müssen im
**selben** Arbeitspaket geändert werden:

1. `to_status_dict()` bzw. der Statusaufbau in `controller.py`
2. die Typen in `web/src/types.ts` und die auswertenden Seiten
3. diese Datei und [api-referenz.md](api-referenz.md)
4. die betroffenen Tests

Feldnamen werden **erweitert, nicht umbenannt** (D-034): Ein Rename bräche jede bestehende Anlage
und den Energy Pilot.
