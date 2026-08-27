# HA-Helfer für den ersten AC-Speicher

Minimalkonfiguration der HA-Helfer-Entitäten für den ersten AC-gekoppelten Speicher dieser
Anlage. Anzeigename **„Speicher 1"**, technischer Präfix **`acspeicher1`**, max. 2500 W
Lade-/Entladeleistung, 5 kWh Kapazität.

## Warum `acspeicher1` statt `speicher_1`

Der Namensraum `ems_speicher_*` gehört in dieser Anlage bereits der bestehenden
E3DC-Regelung (`ems_speicher_mindesladeleistung_1/2`, `ems_speicher_soc_mindestwert_1/2`,
`ems_speicher_regelung_stufe_1_aktiv` — live über HA-MCP bestätigt). Das ist auch in
[`docs/device_classes/battery.md`](../../docs/device_classes/battery.md) und
[`docs/datenmodell.md`](../../docs/datenmodell.md) so festgehalten. Ein Präfix `speicher_1`
wäre mit diesen Entitäten leicht zu verwechseln.

Der Anzeigename **„Speicher 1"** bleibt davon unberührt — er steht in jedem `name:`-Feld der
Helfer unten und ist damit überall sichtbar, wo Menschen die Entität sehen (Ingress-Panel,
Lovelace, HA-Oberfläche). Nur die Entity-IDs verwenden `acspeicher1`.

## Enthalten

- `input_boolean.yaml` — Freigabe, technische Freigabe, Lade-/Entlade-Freigabe
- `input_select.yaml` — Modus, Betriebsart, Anforderung-Betriebsart (Ausgabe)
- `input_number.yaml` — Priorität, Entladepriorität, SOC-Grenzen, Anforderung-Leistung
  (Ausgabe), plus der globale Entlade-Abschlag (einmalig für die ganze Anlage, weil dies der
  erste `battery`-Speicher ist)

Umfang: die zwei Ausgabe-Helfer und die vier gemeinsamen Helfer sind zwingend (kein Fallback
bzw. Pflicht laut Doku); zusätzlich die Bedienhelfer (Betriebsart, Freigaben, SOC-Grenzen,
Entladepriorität), damit der Speicher ohne weitere Handarbeit tatsächlich regelbar ist.

**Bewusst weggelassen:** Feinschliff-Parameter wie Rampenzeiten, Reserve, Totzone,
`min_ladeleistung_w`/`min_entladeleistung_w`, `geschutzte_mindestleistung_w`. Sie laufen auf
den internen Ersatzwerten aus `docs/device_classes/battery.md` und können bei Bedarf später
als weitere Helfer ergänzt werden.

## Nicht enthalten: 2500 W / 5 kWh

Unter dem aktuell implementierten Vertrag (ADR D-043) sind die physischen Leistungsgrenzen und
die Kapazität **keine HA-Helfer**, sondern statische Felder im Add-on-Geräteeintrag
(`config.yaml` → `devices[]`). Sie müssen dort ergänzt werden, zum Beispiel:

```yaml
devices:
  - name: acspeicher1
    label: "Speicher 1"
    class: battery
    entity_prefix: acspeicher1
    soc_entity: sensor.acspeicher1_soc                     # anpassen
    charge_power_entity: sensor.acspeicher1_ladeleistung    # anpassen
    discharge_power_entity: sensor.acspeicher1_entladeleistung  # anpassen
    available_charge_power_w: 2500
    available_discharge_power_w: 2500
    capacity_kwh: 5
```

Dazu kommt die Anlage-weite Option `battery_residual_power_entity` (Hausleistungsbilanz für
AC-Speicher), siehe [`docs/konfiguration.md`](../../docs/konfiguration.md). Die passende
Vorlage dafür liegt bereits unter
[`erweiterungen/zusatz_sensor_für_speicher_null_einspeisung/ueberschusssensor_von_ha.yaml`](../zusatz_sensor_für_speicher_null_einspeisung/ueberschusssensor_von_ha.yaml).

## Annahmen

- **Priorität 50** für Laden und Entladen: nächster freier Slot nach den bestehenden Geräten
  (Heizstab 10, Heizlüfter 1/2 20/30, Wallbox 40). Bei Bedarf im Ingress-Panel anpassen.
- **Entlade-Abschlag 30 W**: Empfehlung aus dem Entwurfsdokument bei kurzem Regelzyklus,
  keine gemessene Anlagengröße. Jederzeit änderbar.
- **Icons**: `mdi:home-battery` durchgehend für Speicher-1-Helfer, `mdi:numeric` für die
  beiden Prioritäts-Helfer — gespiegelt vom Icon-Muster der bestehenden `ems_*`-Helfer
  (ein Icon pro Gerät, Ausnahme `prioritat`).

## Einspielen

Diese drei Dateien enthalten Standard-Home-Assistant-YAML (`input_boolean:`/`input_select:`/
`input_number:` als Top-Level-Key). Sie müssen in die tatsächliche HA-Konfiguration
eingebunden werden (z. B. als `packages`-Dateien oder per `!include`) — das Add-on legt diese
Helfer nicht selbst an.
