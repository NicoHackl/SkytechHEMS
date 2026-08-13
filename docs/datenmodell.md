# Datenmodell

Das Add-on hat **keine eigene Persistenz**. Zustand lebt an zwei Orten: in den HA-Helfer-Entitäten
(überlebt Neustarts) und im Speicher der Geräteobjekte (Timer, überlebt keinen Neustart). Dieses
Dokument beschreibt beide Verträge — den zu Home Assistant und den zum **Energy Pilot**.

## Identitäten

| Bezeichner | Bedeutung | Vergeben von | Unveränderlich |
|---|---|---|---|
| `name` | Technische Geräte-ID aus den Add-on-Optionen; erscheint als `id` in `/api/status` und als `name` im Steuerschema | User (Konfiguration) | ja — ein Rename ist eine Neuanlage |
| `entity_prefix` | Präfix der HA-Helfer, per Default `name` | User (Konfiguration) | ja |
| `label` | Reiner Anzeigename | User (Konfiguration) | nein — darf sich jederzeit ändern |

Grundsatz: Konsumenten machen die Identität am `name` fest und zeigen nur das `label` an. Ein
umbenanntes Label darf keine Zuordnung brechen.

Erlaubte Zeichen in `name` und `entity_prefix`: Kleinbuchstaben, Ziffern, Unterstrich — sie fließen
unverändert in Entitätsnamen ein.

## HA-Helfer — Namenskonvention

```text
<domain>.ems_<prefix>_<suffix>
```

`<domain>` ist `input_boolean`, `input_select` oder `input_number`. Die Helfer müssen in Home
Assistant existieren; das Add-on legt sie nicht an.

### Global

| Entität | Domain | Werte | Pflicht | Funktion |
|---|---|---|---|---|
| `input_boolean.ems_pv_regelung_aktiv` | `input_boolean` | `on` / `off` | ja | Globaler Schalter der gesamten Regelung |
| `input_select.ems_regelmodus` | `input_select` | `auto`, `manuell`, `nur_heizen`, `nur_laden`, `aus` | ja | Globaler Regelmodus. `auto` = KI-Übernahme, `manuell` = normale Regeln, `aus` = aus |
| `input_number.ems_globaler_puffer_w` | `input_number` | Watt | ja | Zusätzlich reservierte Leistung je regelbarem Gerät |
| `input_number.ems_einschaltreserve_global_w` | `input_number` | Watt | ja | Hysterese-Aufschlag für alle binären Geräte |
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
| `min_umschaltzeit_s` *(optional)* | s | Phasenwechsel-Hysterese; überschreibt `phase_switch_delay_s`. Fehlt beides, gelten 30 s |
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

### Externe, nur gelesene Entitäten

| Entität | Funktion |
|---|---|
| Überschuss-Sensor (`residual_power_entity`) | **Pflicht.** PV-Überschuss in Watt; `unavailable`/`unknown` oder ≤ −50 000 W löst Hard-Lockout aus. Semantik: [konfiguration.md](konfiguration.md) |
| `actual_power_entity` je regelbarem Gerät | Ist-Leistung in Watt |
| `switch_entity` je binärem Gerät | Tatsächlicher Schaltzustand |
| `voltage_l1/l2/l3_entity` | Phasenspannungen in Volt, Fallback je 230 V |

## Statusvertrag `/api/status`

Erzeuger ist `EMSController.run_cycle()`, Verbraucher sind die eigene Oberfläche **und** der
Energy Pilot. Feldnamen sind damit ein öffentlicher Vertrag.

Global:

| Feld | Typ | Bedeutung |
|---|---|---|
| `ems_enabled` | bool | Globale Freigabe |
| `global_mode` | string | Regelmodus |
| `hard_lockout` | bool | Sperre wegen ungültigem Überschuss-Sensor |
| `residual_sensor_valid` | bool | Sensor lieferte einen brauchbaren Wert |
| `residual_w`, `pool_w`, `current_deficit_w`, `binary_total_w` | float | Leistungen in Watt |
| `binary_immediate_off` | bool | Notabschaltung binärer Geräte |
| `timestamp` | string | **Maschinenformat** `JJJJ-MM-TT hh:mm:ss`, nicht zur Anzeige gedacht |
| `devices` | Liste | siehe unten |

Regelbares Gerät: `type`, `id`, `label`, `priority`, `eligible`, `source`, `actual_w`,
`anforderung_current_w`, `alloc_w`, `new_w`, `schutz_w`, `geschuetzte_mindestleistung_w`,
`output_unit`. Im Ampere-Modus zusätzlich `current_phases`, `allowed_phases`, `voltage_l1..l3`,
`new_a`, `schutz_a`, `geschuetzte_mindestleistung_a` und — solange die Sperre läuft —
`phase_lock_remaining_s`.

Binäres Gerät: `type`, `id`, `label`, `priority`, `eligible`, `source`, `power_w`, `actual_on`,
`anforderung_an`, `desired_on`, `candidate_on`, `final_on`, `in_min_runtime`, `switch_age_s`,
`min_runtime_s`, `min_offtime_s`, `off_delay_remaining_s`.

Fallstricke, die schon Fehler verursacht haben:

- **`schutz_w` ist nicht die geschützte Mindestleistung.** `schutz_w` ist der effektive Schutz
  (`Sockel + reserve_w + globaler Puffer`, geklemmt). Der rohe Nutzerwert steht in
  `geschuetzte_mindestleistung_w` bzw. `_a`. Vergleiche gehören gegen den Rohwert.
- **`source`** sagt, woher die wirksamen Werte stammen: `aus`, `user` oder `ep`.
- **`off_delay_remaining_s` ist `null`**, wenn keine Abschaltverzögerung läuft — `0` bedeutet
  „läuft ab", nicht „nicht vorhanden".
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
| `sensor.ep_<prefix>_<feld>_vorschlag` | EP → HEMS | Vorschlag je Gerät und Feld, Attribute `friendly_name` (`"<Gerät> – <Feld> (Vorschlag)"`), `valid_until`, `unit_of_measurement` |

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
