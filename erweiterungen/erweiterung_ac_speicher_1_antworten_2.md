# Antworten zu den offenen Fragen · AC‑Speicher‑Erweiterung, zweite Runde

> Bezug: [`erweiterung_ac_speicher_1.md`](erweiterung_ac_speicher_1.md),
> Abschnitt 18 und die erste Antwortdatei
> [`erweiterung_ac_speicher_1_antworten.md`](erweiterung_ac_speicher_1_antworten.md).
> Eingearbeitet in **Entwurf v5**.
>
> Anlass: Beim Abgleich des Entwurfs mit der tatsächlichen Anlage sind drei
> Grundannahmen aufgefallen, die nicht zutrafen. Der Befund steht unten unter
> „Anlagenbefund", die Antworten darauf hier.

## Antworten

- **F‑2 (Wechselrichter, Register, Reihenfolge):** Das HEMS stellt Lade‑ und
  Entladeleistung ausschließlich als HA‑Entitäten bereit. Die Ansteuerung des
  Speichers — über MQTT oder Modbus — übernimmt eine externe HA‑Automation.
  Damit ist die Registerfrage **kein HEMS‑Thema mehr**.
- **F‑11 (Shelly‑Nulleinspeisung an/aus):** Es gibt keinen Shelly 3EM.
  Die Frage entfällt ersatzlos.
- **F‑12 (Quelle des Überschuss‑Sensors):** Bleibt als Messpunkt offen, ist
  aber kein Gate mehr — sie bestimmt nur die Dimensionierung von
  `hoch_regelzeit_s`.
- **Welcher Speicher:** Ein **neuer, AC‑gekoppelter Speicher**. Der vorhandene
  E3DC ist ausdrücklich **nicht** gemeint.
- **E3DC:** Regelt sich selbst. Seine Ladeleistung ist im Überschuss‑Sensor
  bereits berücksichtigt. Er ist kein HEMS‑Gerät und wird keines.
- **Ausgabe‑Vertrag:** **Ein signierter Leistungswert plus Betriebsart.**
- **Messpunkt (D‑B03):** 0 W Entladung bei 500 W Netzbezug → der Speicher regelt
  auf 500 W hoch → der Überschuss‑Sensor zeigt 0 W. Die Entladung ist also im
  Sensor enthalten.
- **Sicherer Zustand:** `inverter` und `shelly_fallback` streichen, immer
  `standby`.
- **Namensraum:** `ems_ac_speicher_*` für globale Helfer, `acspeicher1` als
  Geräte‑Präfix.

---

## Anlagenbefund

Read‑only aus dem laufenden Home Assistant erhoben, Stand 20.08.2026:

| Fund | Beleg |
|---|---|
| Der vorhandene Speicher ist ein **E3DC**, lesend über **Modbus** angebunden | `sensor.e3dc_*`, `platform: modbus` |
| Die PV‑Erträge laufen **über den E3DC** | `sensor.e3dc_leistung_ertrag_hausdach`, `…_garagendach` — ein DC‑gekoppelter Hybrid |
| Sein Schreibpfad kennt nur **Obergrenzen** | `pyscript.e3dc_set_power_limits(max_charge, max_discharge, discharge_start)` |
| **Kein Shelly 3EM** vorhanden | Nur Shelly‑Steckdosen und ein `shellyplus010v` |
| Der Überschuss‑Sensor ist ein **Template‑Sensor**, nicht der Netzzähler | `sensor.verfugbare_leistung_fur_uberschusverbraucher`, `platform: template` |
| Es läuft bereits eine **eigene E3DC‑Regelung** | `automation.pye3dc_max_ladeleistung_speicher_setzen`, `input_boolean.ems_speicher_regelung_stufe_1_aktiv`, `input_number.ems_speicher_mindesladeleistung_1/2`, `…_soc_mindestwert_1/2` |
| `post_cycle_script` ist **belegt** | `script.heizstab_sollleistung_setzen` |
| `interval_s = 3` ist bestätigt | Add‑on‑Optionen |

---

## Was daraus im Entwurf geworden ist

### F‑2 · Das HEMS schreibt nur Entitäten → **D‑B19**

Die Arbeitsteilung aus Abschnitt 1 („Das HEMS schreibt niemals direkt in
Wechselrichter‑Register") gilt jetzt ohne Einschränkung und ohne Vorbehalt:

| Teil | Wer |
|---|---|
| Sollwert berechnen, begrenzen, rampen | **HEMS** |
| Sollwert in Modbus/MQTT übersetzen, Reihenfolge und Übernahmezeit am Gerät | **HA‑Automation** |

Folgen:

* **`steuerprofil` ist nicht mehr reserviert, sondern entschieden:** `signiert`.
* **Das Reihenfolge‑Gate im Phasenplan entfällt.** Phase 2 und 3 waren durch F‑2
  blockiert — das sind sie nicht mehr. Der gesamte Plan ist baubar.
* Die Schreibreihenfolge aus D‑B11 (Betriebsart vor Leistung, beim Abschalten
  umgekehrt) bleibt als *Konvention* im HEMS erhalten. Sie kostet nichts und
  hilft der Automation, wenn diese die Reihenfolge durchreicht.

### Ausgabe‑Vertrag · Ein signierter Wert → **D‑B20**

Statt der drei Entitäten aus D‑B11 v4 nur noch zwei:

```
input_number.ems_<p>_anforderung_leistung_w      # + laden / - entladen
input_select.ems_<p>_anforderung_betriebsart     # laden | entladen | standby
```

Das Vorzeichen folgt der Konvention aus 4.1 (`netto_w`: + laden / − entladen),
es kommt also keine dritte Bedeutung ins Spiel.

Zwei Punkte, die daraus folgen:

1. **Der HA‑Helfer braucht ein negatives Minimum.** `input_number` klemmt
   serverseitig; steht `min: 0`, kommt nie eine Entladeanforderung an. Gehört
   in die Package‑Vorlage und in die README.
2. **Ein `last_changed` für beide Richtungen.** In v4 hatten Laden und Entladen
   getrennte Entitäten und damit getrennte Rampen‑Alterungen. Jetzt gibt es
   eine — `_lade_age_s` und `_entlade_age_s` fallen zu `_anforderung_age_s`
   zusammen. Das ist eine Vereinfachung, keine Einschränkung: ein
   Richtungswechsel setzt die Alterung ohnehin zurück, und die Umschaltsperre
   (`min_umschaltzeit_s`, Default 300 s) dominiert diesen Fall.

### E3DC · Kein HEMS‑Gerät → **D‑B21**

Der E3DC regelt sich selbst auf Eigenverbrauch. Seine Lade‑ und Entladeleistung
ist im Überschuss‑Sensor bereits verrechnet, bevor das HEMS ihn liest.

Daraus folgt die **Abgrenzungsregel**:

> Aus HEMS‑Sicht ist der E3DC Teil der Erzeugungsseite, nicht ein Gerät.
> Er bekommt **keine** `BatteryDevice`‑Instanz, sein `netz_support_w` wird
> **nicht** herausgerechnet, und die bestehende Regelung
> (`automation.pye3dc_max_ladeleistung_speicher_setzen`, die
> `input_number.ems_speicher_*`‑Helfer) bleibt vollständig unberührt.

Das ist zugleich der Grund für den neuen Namensraum: `ems_speicher_*` gehört
dem E3DC. Der globale Helfer heißt deshalb
`input_number.ems_ac_speicher_entlade_abschlag_w`, das Beispiel‑Präfix in der
Doku ist `acspeicher1`.

Eine Konsequenz, die man kennen muss: `pool_roh_w` und `hausdefizit_w` beziehen
sich auf das, was **nach** dem E3DC übrig bleibt. Lädt der E3DC gerade, sinkt
der Überschuss und der AC‑Speicher bekommt weniger. Das ist gewollt — die
Priorisierung zwischen beiden Speichern findet außerhalb des HEMS statt.

### D‑B03 · `speicher_in_residual_enthalten = true` bestätigt

Die Antwort beschreibt exakt das Prüfrezept aus D‑B03: Entladung von 0 W auf
500 W bei 500 W Netzbezug, Sensor geht auf 0 W. Der AC‑Speicher ist im Sensor
enthalten, also gilt

```
residual_bereinigt_w = residual_w - netz_support_w
```

und **H‑1** (Pool‑Aufschaukelung) sowie **H‑2** (Defizit‑Maskierung) sind reale
Gefahren, keine theoretischen. Die Option bleibt trotzdem konfigurierbar, weil
sie eine Anlageneigenschaft beschreibt und nicht eine Vorliebe.

> Der Sensor ist ein YAML‑Template‑Sensor, dessen Definition dem HEMS nicht
> vorliegt. Für die Formeln reicht die bestätigte Semantik. Für die
> **Dimensionierung** von `hoch_regelzeit_s` fehlt weiterhin der gemessene
> Sensor‑Versatz → F‑12.

### Sicherer Zustand · `inverter` und `shelly_fallback` gestrichen → **D‑B22**

Ohne Shelly gibt es keine autonome Rückfallregelung, die man aktivieren könnte.
Ersatzlos gestrichen:

* Betriebsart `inverter` — Eingang wie Ausgang
* Konfigfeld `shelly_fallback` samt der `_build_devices`‑Validierung
  „höchstens einer"
* `blockiert_grund`‑Wert `inverter`
* **Watchdog‑Ebene 3** (Shelly als Rückfallebene) aus 12.2

```python
def _sicherer_zustand(self) -> str:
    """Zustand bei EMS-Ausfall, Lockout oder fehlender Freigabe.

    Immer standby: es gibt keine autonome Rueckfallregelung, auf die man
    umschalten koennte. Wichtig ist deshalb, dass get_write_ops() diesen
    Zustand AKTIV schreibt - 'nichts tun' liesse den letzten Sollwert stehen.
    """
    return "standby"
```

Einwand 1 aus D‑B05 (n autonome Regler auf einer Messgröße haben kein
Gleichgewicht) bleibt vollständig gültig und trägt die zentrale Koordination
allein. Einwand 2 (der Shelly ist langsamer als der HEMS‑Zyklus) entfällt
mangels Shelly.

**Was das für den Watchdog bedeutet:** Der Ausfall wird teurer. Fällt das HEMS
aus, geht der Speicher auf `standby` und das Haus zieht voll aus dem Netz,
obwohl der Speicher geladen ist. Kein Sicherheitsproblem, aber Geld. Die
verbleibenden Ebenen sind damit Pflicht:

1. **Heartbeat.** `post_cycle_script` ist bereits durch
   `script.heizstab_sollleistung_setzen` belegt und kennt nur einen Slot.
   Statt einer neuen Add‑on‑Option bekommt dieses Skript eine zusätzliche
   Aktion, die `input_datetime.ems_letzter_zyklus` auf `now()` setzt.
2. **HA‑Automation als Totmann.** Zeitstempel älter als 3 × `interval_s`
   (`for: 00:02:00`) → alle `ems_*_anforderung_leistung_w` auf 0,
   `…_anforderung_betriebsart` auf `standby`.
3. ~~Shelly‑Rückfallebene~~ — entfällt.
4. **Wechselrichterseitiger Watchdog**, falls das künftige Gerät einen hat.
   Die einzige Ebene, die auch einen HA‑Ausfall überlebt — beim Kauf darauf
   achten.

### Korrektur an 15.3 · P3 und P4 gehören auf die Zuteilungsebene

Beim Gegenlesen der Property‑Tests ist ein Widerspruch im Entwurf selbst
aufgefallen. P3 fordert

```python
assert sum(b.new_entlade_w for b in batteries) <= hausdefizit_w + 1e-6
```

Das kann die asymmetrische Rampe aus 5.3 nicht halten, und zwar absichtlich:
Bei einer *kleinen* Absenkung des Ziels dämpft sie bewusst und hält den
Sollwert vorübergehend über dem gesunkenen Ziel — genau das ist das Gegenmittel
gegen H‑7. Ein Test in dieser Form würde die gewollte Eigenschaft als Fehler
melden.

Dieselbe Überlegung gilt für P4 gegenüber `runter_regelzeit_s`, und zwar schon
im Bestandscode.

Deshalb werden beide auf der Ebene formuliert, auf der sie exakt gelten — der
Zuteilung, wie es die bestehende `tests/test_allocation_properties.py` bereits
tut:

```python
# P3  Die ZUTEILUNG überschreitet das Hausdefizit nie
assert sum(b.entlade_ziel_w for b in batteries) <= hausdefizit_w + 1e-6

# P4  Die ZUTEILUNG überschreitet den Pool nie
assert sum(b.alloc_w for b in batteries) <= pool_w + 1e-6
```

Auf der Sollwertebene bleibt die Monotonie‑Form aus P6: Der Sollwert steigt nie
über das Ziel *und* den bisherigen Wert hinaus.

---

## Weiterhin offen

| # | Frage | Blockiert | Warum sie den Entwurf ändert |
|---|---|---|---|
| **F‑12** | Aus welcher Quelle kommt `sensor.verfugbare_leistung_fur_uberschusverbraucher`, und wie weit läuft er dem Batterie‑Leistungssensor nach? | Nichts — nur die Dimensionierung | Bestimmt `hoch_regelzeit_s` und `entlade_sofort_schwelle_w` (H‑7). Messbar erst mit installiertem Speicher |
| **F‑13** | Welches Gerät wird der AC‑Speicher? | Inbetriebnahme, nicht den Code | Liefert `soc_entity`, die Ist‑Leistungssensoren (Variante A oder B nach D‑B12), `capacity_kwh` und die technischen Grenzen |
| **F‑14** | Bringt das Gerät eine eigene Nulleinspeisungs‑Regelung mit? | Inbetriebnahme | Ist sie vorhanden und nicht abschaltbar, regeln HEMS und Gerät gegeneinander — Merksatz 2. Beim Kauf mitentscheiden |

Keine dieser Fragen blockiert die Umsetzung. F‑13 und F‑14 sind Beschaffungs‑
und Inbetriebnahmethemen; der Code liest alle drei Werte aus der Konfiguration.
