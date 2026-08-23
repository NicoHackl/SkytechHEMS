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

| Suffix | Einheit | Ersatzwert | Funktion |
|---|---|---|---|
| `entlade_prioritat` | – | 50 | **Reihenfolge beim Entladen, unabhängig von `prioritat`.** Kleiner = zuerst; bei Gleichstand entscheidet die Reihenfolge in der Add-on-Konfiguration |
| `min_ladeleistung_w`, `min_entladeleistung_w` | W | 0 | Untere Grenzen. Darunter wird auf 0 gerastet, nicht überschossen |
| `soc_min_prozent` | % | 10 | Entladeschluss und **einziger** Entladeboden |
| `soc_max_prozent` | % | 100 | Ladeschluss |
| `umschalt_totzone_w` | W | 100 | Totzone um 0; ein Netto-Wunsch darunter führt zu `standby` |
| `netzlade_leistung_w` | W | 0 | Reservierte, noch nicht sicher freigegebene Netzlade-Schnittstelle; muss wegen [B-4](bekannte-luecken.md#offene-bugs) auf `0` bleiben |
| `anforderung_leistung_w` **(Ausgabe)** | W | – | **Ein signierter Sollwert: + laden / − entladen.** Der Helfer braucht ein **negatives Minimum** |
| `anforderung_betriebsart` **(Ausgabe, `input_select`)** | – | – | `laden` / `entladen` / `standby`; genau diese drei Optionen sind erforderlich |

Beim Speicher weichen drei Ersatzwerte von der sonstigen Regel ab:

- `reserve_w` fällt auf **50 W**, nicht auf 0. Eine vorhandene Entität mit gültiger `0` setzt den
  Puffer bewusst ab.
- `max_anderung_pro_schritt_w` hat **keinen** Ersatzwert: ohne gültigen Wert gibt es keine
  Schrittbegrenzung, das Ziel wird unmittelbar erreicht. Im Status erscheint dafür kein
  magischer Großwert und kein `Infinity`.
- `laden_erlaubt` und `entladen_erlaubt` trennen fehlend von ausgefallen: eine **nicht angelegte**
  Entität heißt „erlaubt", eine vorhandene mit `unknown`/`unavailable`/ungültigem State heißt
  „gesperrt".

Dazu drei Schalter und eine Auswahlliste:

| Entität | Werte | Funktion |
|---|---|---|
| `input_boolean.ems_<prefix>_laden_erlaubt` | `on`/`off` | Ladepfad freigeben |
| `input_boolean.ems_<prefix>_entladen_erlaubt` | `on`/`off` | Entladepfad freigeben |
| `input_boolean.ems_<prefix>_netzladen_aktiv` | `on`/`off` | Reserviert; bis zur Behebung von [B-4](bekannte-luecken.md#offene-bugs) zwingend `off` |
| `input_select.ems_<prefix>_betriebsart` | `auto`, `nur_laden`, `nur_entladen`, `standby` | Was das HEMS überhaupt darf |

Externe Sensoren je Speicher: `soc_entity` (Pflicht) und genau eine Ist-Leistungsvariante —
entweder `charge_power_entity` **und**
`discharge_power_entity` (beide ≥ 0) oder ein signierter `power_entity` mit `power_sign`. Beide
Varianten gleichzeitig sind ungültig.

`available_charge_power_w` und `available_discharge_power_w` sind verpflichtende, direkt in den
Add-on-Optionen gepflegte Wattwerte und die **alleinigen physischen Maximalgrenzen**. Ein Wert `0`
sperrt nur die jeweilige Richtung bewusst. Dafür werden keine HA-Entitäten gelesen.

**Entfallen** sind `max_ladeleistung_w`, `max_entladeleistung_w`, `soc_reserve_prozent`,
`soc_taper_band_prozent`, `soc_max_hysterese_prozent`, `entlade_sofort_schwelle_w` und
`min_umschaltzeit_s`. Hysterese und Umschaltsperre stehen jetzt als
`soc_max_hysteresis_percent` (Default 2) und `direction_switch_delay_s` (Default 5) in der
Add-on-Konfiguration; Notstromreserve, Drosselband und Sofort-Schwelle entfallen ersatzlos.

Fehlt einer der Messwerte (`unavailable`), fällt genau dieser Speicher aus der Regelung und geht
auf `standby`; die übrigen laufen weiter. Ohne Ist-Leistung wäre die Pool-Bereinigung blind.

> **Namensraum:** In dieser Anlage ist `ems_speicher_*` bereits von einer eigenen
> HA-Automation für den vorhandenen E3DC belegt. Der HEMS-Speicher benutzt deshalb `acspeicher1`
> als Präfix. Der E3DC selbst ist **kein** HEMS-Gerät (D-040).

### Externe, nur gelesene Entitäten

| Entität | Funktion |
|---|---|
| Überschuss-Sensor (`residual_power_entity`) | **Pflicht.** PV-Überschuss in Watt; `unavailable`/`unknown` oder ≤ −50 000 W löst Hard-Lockout aus. Semantik: [konfiguration.md](konfiguration.md) |
| Hausleistungsbilanz (`battery_residual_power_entity`) | **Pflicht bei `class: battery`.** Signiert: negativ = Unterdeckung, positiv = Einspeisung. Steuert ausschließlich die AC-Speicher-Entladung; ein ungültiger Wert schickt diese Speicher auf `standby`, ohne den übrigen Zyklus zu sperren. |
| Formel-Zeilen (`residual_formula_variables`/`battery_residual_formula_variables`) | **Optional (D-045).** Beliebig viele benannte HA-Entitäten, die der zugehörige Formel-Code kombiniert. Liefert der Code einen gültigen Wert, ersetzt er die beiden Entitäten oben vollständig — siehe [konfiguration.md](konfiguration.md#formel-statt-einzel-entität) |
| `actual_power_entity` je regelbarem Gerät | Ist-Leistung in Watt |
| `switch_entity` je binärem Gerät | Tatsächlicher Schaltzustand |
| `power_actual_entity` je binärem Gerät (optional) | Ist-Leistung in Watt, reine Datenquelle ohne Regelwirkung |
| `voltage_l1/l2/l3_entity` | Phasenspannungen in Volt, Fallback je 230 V |
| `soc_entity` je Speicher | Ladezustand in Prozent |
| `charge_power_entity` / `discharge_power_entity` je Speicher | Ist-Leistung in Watt, beide ≥ 0 |
| `power_entity` + `power_sign` je Speicher | Alternative: eine signierte Entität für beide Richtungen |

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
| `residual_source` | string | `"ha"` oder `"formula"` (D-045) — welche Quelle `residual_w` gerade liefert |
| `residual_w`, `pool_w`, `current_deficit_w`, `binary_total_w` | float | Leistungen in Watt |
| `residual_bereinigt_w` | float | `residual_w` abzüglich der gemessenen Speicherentladung. Grundlage für Pool und Verbraucher-Defizit, nicht für die AC-Entladeplanung |
| `battery_residual_sensor_valid` | bool | Separate Hausleistungsbilanz lieferte einen brauchbaren Wert; ohne `battery` nur Diagnose und nicht regelrelevant |
| `battery_residual_source` | string | `"ha"`, `"addon"`, `"internal"` oder `"formula"` (D-045) — welche Quelle `battery_residual_w` gerade liefert |
| `battery_residual_w` | float | Rohe Hausleistungsbilanz: negativ = Unterdeckung, positiv = Einspeisung |
| `battery_residual_bereinigt_w` | float | `battery_residual_w` abzüglich der gemessenen AC-Entladung (`netz_support_w`) |
| `netz_support_w` | float | Σ gemessene Entladeleistung aller Speicher |
| `hems_last_w` | float | Σ `current_w` — nur vom HEMS angeforderte Last, Force-Modus gefiltert |
| `hems_last_gemessen_w` | float | Σ `gemessene_last_w` — roher Messwert, Force-Modus enthalten |
| `pool_roh_w` | float | Ungeklemmter Pool aus dem Überschuss-Sensor. Positiv = verteilter Überschuss, negativ = kein verteilter Überschuss |
| `entlade_basis_w` | float | Basis der Entladeplanung aus der separaten Hausleistungsbilanz; enthält die gemessenen HEMS-Lasten zurückgerechnet |
| `hausdefizit_w` | float | Hausverbrauchs-Fehlbetrag, den die Speicher decken sollen. **Enthält keine HEMS-Gerätelast**, auch keine fremdgesteuerte; bei ungültiger Hausleistungsbilanz `0` |
| `binary_immediate_off` | bool | Notabschaltung binärer Geräte |
| `timestamp` | string | **Maschinenformat** `JJJJ-MM-TT hh:mm:ss`, nicht zur Anzeige gedacht |
| `devices` | Liste | siehe unten |
| `devices_inactive_runtime` | Liste | Geräte-IDs, die diesen Zyklus technisch nicht regelbar waren (Schreibziel fehlt oder Schreiben schlug fehl) |
| `inactive_devices` | Liste | Beim Start übersprungene Geräteeinträge: `index`, `name`, `device_class`, `label`, `errors` (Feldname → deutsche Meldung). Ausdrücklich **ohne** erfundene Ist-, SoC- oder Schaltwerte |

Jedes Gerät trägt zusätzlich:

| Feld | Typ | Bedeutung |
|---|---|---|
| `entity_diagnostics` | Objekt | `{entity_id: {role, state, source}}` |
| `runtime_active` | bool | `false`, wenn ein Schreibziel fehlt, unbrauchbar ist oder der letzte Schreibversuch fehlschlug |
| `inactive_reasons` | Liste | `schreibziel_fehlt`, `schreibziel_nicht_verfuegbar`, `schreibziel_ungueltig`, `schreiben_fehlgeschlagen` |
| `write_error` | string oder `null` | Bereinigte Fehlermeldung des letzten Schreibversuchs |

`state` ist `valid`, `missing`, `unavailable` oder `invalid`; bei Schreibzielen zusätzlich
`write_failed`. `source` ist `ha`, `addon` oder `internal`.
Damit ist beantwortbar, welcher Wert gerade wirkt und warum nicht der aus Home Assistant — siehe
[Doppelte Auflösung](device_classes/global.md#doppelte-auflösung-von-ha-entitäten).

Regelbares Gerät: `type`, `id`, `label`, `priority`, `eligible`, `source`, `actual_w`,
`anforderung_current_w`, `alloc_w`, `new_w`, `schutz_w`, `geschuetzte_mindestleistung_w`,
`output_unit`. Im Ampere-Modus zusätzlich `current_phases`, `allowed_phases`, `voltage_l1..l3`,
`new_a`, `schutz_a`, `geschuetzte_mindestleistung_a` und — solange die Sperre läuft —
`phase_lock_remaining_s`.

Binäres Gerät: `type`, `id`, `label`, `priority`, `eligible`, `source`, `power_w`, `actual_on`,
`anforderung_an`, `desired_on`, `candidate_on`, `final_on`, `in_min_runtime`, `switch_age_s`,
`min_runtime_s`, `min_offtime_s`, `off_delay_remaining_s`. Dazu `power_actual_w`, sofern
`power_actual_entity` konfiguriert ist und der Sensor einen gültigen Wert liefert.

Speicher (`type: "battery"`): `id`, `label`, `priority` (Laden), `entlade_prioritat`, `eligible`,
`source`, `ep_proposal_status`, `sensoren_gueltig`, `battery_residual_sensor_valid`, `soc_prozent`, `capacity_kwh`, `betriebsart`,
`betriebsart_effektiv`, `lade_ist_w`, `entlade_ist_w`, `lade_anforderung_w`,
`entlade_anforderung_w`, `new_lade_w`, `new_entlade_w`, `netto_w`, `max_ladeleistung_w`,
`max_entladeleistung_w`, `lade_limit_w`, `entlade_limit_w`, `hausdefizit_anteil_w`, `schutz_w`,
`geschuetzte_mindestleistung_w`, `laden_erlaubt`, `entladen_erlaubt`, `netzladen_aktiv`,
`soc_min_prozent`, `soc_max_prozent`, `soc_max_hysteresis_percent`, `direction_switch_delay_s`,
`lade_limit_gueltig`, `entlade_limit_gueltig`, `umschaltsperre_rest_s`, `lade_blockiert_grund`,
`entlade_blockiert_grund`, `blockiert_grund`. Dazu `energie_kwh`, sofern `capacity_kwh > 0`
konfiguriert ist. `soc_reserve_prozent` ist **entfallen**.

Fallstricke, die schon Fehler verursacht haben:

- **`schutz_w` ist nicht die geschützte Mindestleistung.** `schutz_w` ist der effektive Schutz
  (`Sockel + reserve_w + globaler Puffer`, geklemmt). Der rohe Nutzerwert steht in
  `geschuetzte_mindestleistung_w` bzw. `_a`. Vergleiche gehören gegen den Rohwert.
- **`source`** sagt, woher die wirksamen Werte stammen: `aus`, `user` oder `ep`.
- **`max_ladeleistung_w` ist nicht `lade_limit_w`.** Beide Schlüssel bleiben aus
  Kompatibilitätsgründen erhalten: `max_ladeleistung_w` und `max_entladeleistung_w` spiegeln die
  beiden statischen `available_*_w`-Werte, `lade_limit_w` und `entlade_limit_w` denselben Wert
  **nach** Freigaben und SoC-Grenzen. `lade_limit_gueltig` und `entlade_limit_gueltig` bleiben
  kompatibel erhalten und sind für eine validierte Konfiguration immer `true`.
- **`netto_w` ist signiert:** positiv = laden, negativ = entladen. Genauso der geschriebene
  Sollwert `anforderung_leistung_w`.
- **Die Hausleistungsbilanz ersetzt den Überschuss-Sensor nicht.** `battery_residual_w` ist nur
  die Entladegröße der AC-Speicher. `pool_w` und `current_deficit_w` bleiben am
  `residual_power_entity`; eine ungültige Bilanz sperrt daher nur die Speicher.
- **Drei Sperrgrund-Felder statt einem.** `lade_blockiert_grund` und `entlade_blockiert_grund`
  beantworten je Pfad „warum passiert gerade nichts", `blockiert_grund` trägt nur die Gründe der
  Richtungsauflösung (`umschaltsperre`, `totzone`). Ein Speicher in `nur_entladen` hat einen
  gesperrten Ladepfad und trotzdem keinen Fehler.
- **`off_delay_remaining_s` ist `null`**, wenn keine Abschaltverzögerung läuft — `0` bedeutet
  „läuft ab", nicht „nicht vorhanden".
- **Drei verschiedene „inaktiv".** `eligible: false` ist die Freigabeentscheidung dieses Zyklus
  (Schalter, Modus, Lockout). `runtime_active: false` heißt „technisch nicht regelbar" — ein
  Schreibziel fehlt oder das Schreiben schlug fehl; das Gerät steht weiterhin in `devices`. Ein
  Eintrag, der wegen fehlender Pflichtfelder gar nicht erst registriert wurde, steht in
  `inactive_devices` und taucht in `devices` überhaupt nicht auf.
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

## Veröffentlichte Kartendaten

Für die **Skytech Power Flow Card** schreibt das Add-on zwei eigene Anzeige-Entitäten über
`POST /api/states` (D-046). Sie sind ein Datenvertrag zu einem zweiten Repository; autoritativ
für jedes Feld ist
[`vertrag_powerflow_card_hems/kontrakt.md`](../vertrag_powerflow_card_hems/kontrakt.md).

| Entität | State | Inhalt | Schreibtakt |
|---|---|---|---|
| `sensor.skytech_hems_flow_config` | Revisions-Kurzhash, 12 Hex-Zeichen | Layout, Anlagenwerte, Geräteliste — ausschließlich **Verweise** auf HA-Entitäten, keine Messwerte | nur bei geänderter Revision oder fehlender Entität |
| `sensor.skytech_hems_flow_status` | `pool_w`, gerundet | Kennzahlen des letzten Zyklus, Rückfallwert je Gerät | jeder Zyklus |

Drei Zusagen dieses Vertrags:

1. **Verweise, keine Messwerte.** Die Karte löst die Entity-IDs selbst gegen `hass.states` auf.
   Dadurch aktualisiert sie im Takt von Home Assistant statt im Regelintervall und bleibt lesbar,
   wenn das Add-on gerade steht.
2. **Entity-IDs stehen ausgeschrieben.** Die Karte setzt keinen Namen aus einem Präfix zusammen.
   Quelle ist dieselbe wie beim Steuerung-Tab: `_build_device_controls_schema()`.
3. **`schema_version` ist additiv.** Neue optionale Felder erhöhen sie nicht; erhöht wird nur,
   wenn ein Feld entfällt, umbenannt wird oder seine Bedeutung ändert (D-047).

Zwei Abbildungen weichen bewusst von den internen Namen ab, weil der Vertrag eine andere Frage
beantwortet als der Status:

| Vertragsfeld | Quelle im Status | Warum |
|---|---|---|
| `devices[id].runtime_active` | `eligible and runtime_active` | Der Vertrag fragt „regelt gerade mit". Intern meldet `runtime_active` nur die Schreibziel-Gesundheit, die Freigabeentscheidung steht in `eligible` |
| `devices[id].inactive_reasons` | Tokens aus `mark_inactive()`, sonst aus `entity_diagnostics` und `source` | Der Vertrag verlangt deutschen Klartext; intern sind es bewusst stabile Tokens. Ein unbekannter Token wird unverändert durchgereicht statt verschluckt |

Beide Entitäten gehören in die `recorder`-Ausschlussliste, solange keine Historie gewünscht ist —
die Statusentität ändert sich jeden Zyklus. Per `POST /api/states` erzeugte Entitäten überleben
keinen HA-Neustart; der Publisher erkennt das am fehlenden Eintrag im Zustandsabbild und schreibt
die Konfiguration spätestens nach einem Regelintervall neu.

## Migrationen

Es gibt kein Schema, das migriert werden müsste. Ändert sich der Statusvertrag, müssen im
**selben** Arbeitspaket geändert werden:

1. `to_status_dict()` bzw. der Statusaufbau in `controller.py`
2. die Typen in `web/src/types.ts` und die auswertenden Seiten
3. diese Datei und [api-referenz.md](api-referenz.md)
4. die betroffenen Tests

Feldnamen werden **erweitert, nicht umbenannt** (D-034): Ein Rename bräche jede bestehende Anlage
und den Energy Pilot.
