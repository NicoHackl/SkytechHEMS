# Erweiterung: AC‑gekoppelte Speicher (1…n) im Skytech HEMS

> **Status:** Entwurf v4 – Diskussionsgrundlage, noch keine Implementierung.
>
> **Änderung ggü. v3 – eingearbeitete Antworten aus
> [`erweiterung_ac_speicher_1_antworten.md`](erweiterung_ac_speicher_1_antworten.md):**
>
> | # | Antwort | Folge im Entwurf |
> |---|---|---|
> | **F‑2** | WR‑Anbindung noch offen | `steuerprofil` bleibt reserviert; **Phase 0 ist Vorbedingung für Phase 2/3**, Phase 1 bleibt davon unabhängig |
> | **F‑3** | getrennte **Lade‑ und Entladepriorität** | neu **D‑B17**, neuer Helfer `entlade_prioritat`, `_discharge_order` sortiert danach |
> | **F‑5** | Speicher deckt **keine** fremdgesteuerten HEMS‑Lasten | **D‑B14 entschieden**, Option entfällt; neue Property `gemessene_last_w`, eigene Entladebasis (4.2) |
> | **F‑6** | kein SoC‑Ausgleich, **strikt nach Priorität**; Kapazität in der Add‑on‑Config | neu **D‑B18**; `speicher_entlade_strategie` entfällt ersatzlos, 10.2 stark gekürzt |
> | **F‑8** | kein Summensensor in HA | `netz_support_w` = Σ Einzelsensoren, fix (10.3) |
> | **F‑9** | Einspeisevergütung vorhanden, Batterieexport zulässig | 5.4‑Rechnung gilt unverändert, kein harter Export‑Stopp, `entlade_abschlag_w` klein |
> | **F‑10** | **ein** Sensor an der Netzübergabe, gilt für alle Speicher | D‑B03 bestätigt (`speicher_in_residual_enthalten: true`) |
>
> **Weiterhin offen:** F‑2, F‑11, F‑12 – alle drei sind Phase‑0‑Themen und
> blockieren keine Planung, wohl aber die Inbetriebnahme des Schreibpfads.
>
> **Änderung v2 → v3 (zwei Korrekturen):**
> 1. **Die Empfehlung „Wechselrichter regelt selbst" (`wr_huelle`) ist zurückgezogen.**
>    Sie skaliert nicht: mehrere autonome Nulleinspeisungs‑Regler am selben
>    Netzpunkt regeln gegeneinander (D‑B05). Und die Shelly‑Regelung ist mit
>    >5 s langsamer als der HEMS‑Zyklus. **HEMS regelt zentral, für alle n.**
> 2. **Die Faustregel „Takt ≥ 3× Totzeit, sonst schwingt es" war falsch**
>    angewandt. Sie gilt für integrierende Regler; die hier gewählte Struktur
>    ist absolut und enthält die eigene Stellgröße nicht. Totzeit erzeugt
>    **Verzögerung, keine Instabilität** (H‑4). Das eigentliche
>    Oszillationsrisiko ist Sensor‑Versatz (H‑7).
>
> **Betriebspunkt dieser Anlage:** `interval_s = 3` (läuft mit dem Heizstab
> stabil). Alle Dimensionierungen in diesem Dokument gehen von 3 s aus, nicht
> vom Config‑Default 30 s.
>
> **Scope:** 1…n AC‑gekoppelte Speicher, Lade‑ und Entladeleistung vollständig
> vom HEMS gesteuert.
> **Laden:** aus PV‑Überschuss. Netzladen mit dynamischen Tarifen ist v2‑Ziel,
> die Schnittstellen werden hier bereits festgelegt.
> **Entladen:** **nur zur Deckung des normalen Hausverbrauchs**, ausdrücklich
> **nicht** für die Überschussverbraucher (Heizstab, Wallbox, Heizlüfter).
> **Prinzip:** rein additiv. Ohne konfigurierten Speicher verhält sich das HEMS
> bit‑identisch wie heute.

---

## Inhalt

1. [Ziel und Abgrenzung](#1-ziel-und-abgrenzung)
2. [Ausgangslage im Bestand](#2-ausgangslage-im-bestand)
3. [Die sieben Gefahren](#3-die-sieben-gefahren)
4. [Grundmodell: `pool_roh_w` und `hausdefizit_w`](#4-grundmodell-pool_roh_w-und-hausdefizit_w)
5. [Regelgüte bei 3 s Takt](#5-regelgüte-bei-3-s-takt)
6. [Architekturentscheidungen (D‑B01…D‑B18)](#6-architekturentscheidungen)
7. [Neue Klasse `BatteryDevice`](#7-neue-klasse-batterydevice)
8. [Entitäten und Konfiguration](#8-entitäten-und-konfiguration)
9. [Änderungen am Regelzyklus](#9-änderungen-am-regelzyklus)
10. [Mehrspeicher‑Koordination (1…n)](#10-mehrspeicher-koordination-1n)
11. [Netzladen mit dynamischen Tarifen (Vorbereitung)](#11-netzladen-mit-dynamischen-tarifen-vorbereitung)
12. [Sicherheit, Fehlerfälle, Watchdog](#12-sicherheit-fehlerfälle-watchdog)
13. [Energy‑Pilot‑Anbindung](#13-energy-pilot-anbindung)
14. [Web‑UI](#14-web-ui)
15. [Tests](#15-tests)
16. [Umsetzungsphasen](#16-umsetzungsphasen)
17. [Nicht in Scope v1](#17-nicht-in-scope-v1)
18. [Offene Fragen an dich](#18-offene-fragen-an-dich)

---

## 1. Ziel und Abgrenzung

### Was gebaut wird

| | Verhalten | Wer regelt |
|---|---|---|
| **Laden** | aus PV‑Überschuss, priorisiert gegen Heizstab/Wallbox/Heizlüfter | HEMS (Sollwert) |
| **Entladen** | deckt den **normalen Hausverbrauch**, wenn PV ihn nicht deckt | HEMS (Sollwert oder Hülle, siehe D‑B05) |
| **Nicht entladen für** | Heizstab, Wallbox, Heizlüfter – also alles, was das HEMS selbst zuschaltet | – |
| **Netzladen** | v2, Schnittstellen hier bereits fixiert | HEMS führt aus, Preislogik extern/EP |

### Warum das HEMS regelt und nicht der Speicher

Der Speicher *könnte* über einen Shelly 3EM autonom auf Netzpunkt ±0 regeln.
Diese Fähigkeit wird bewusst **nicht** als Primärregelung genutzt – aus zwei
unabhängigen Gründen (ausführlich in [D‑B05](#d-b05--warum-hems-zentral-regelt-und-nicht-jeder-speicher-für-sich)):

1. **Sie skaliert nicht auf n > 1.** Zwei autonome Regler am selben Netzpunkt
   lösen `D₁ + D₂ = L` – eine Gleichung, zwei Unbekannte. Es gibt kein
   eindeutiges Gleichgewicht; das Ergebnis ist ein Grenzzyklus.
2. **Sie ist langsamer.** Shelly‑Regelung >5 s gegen HEMS‑Zyklus 3 s.

Daraus folgt für den gesamten Entwurf:

* Das HEMS trägt die volle Verantwortung für die Regelgüte am Netzpunkt –
  eine neue Aufgabenklasse für dieses Projekt, siehe
  [Abschnitt 5](#5-regelgüte-bei-3-s-takt).
* Die Shelly‑Nulleinspeisung bleibt als **Rückfallebene** erhalten und wird
  dort zum wertvollsten Teil des Watchdogs
  ([Abschnitt 12.2](#122-watchdog--pflicht-nicht-empfehlung)).
* Solange das HEMS regelt, **muss die Shelly‑Regelung deaktiviert sein** –
  sonst regeln HEMS und Shelly gegeneinander, mit exakt demselben
  Grenzzyklus wie in Punkt 1. Das ist ein Phase‑0‑Punkt.
* Ein **Watchdog ist Pflicht**, nicht Empfehlung. Der zuletzt geschriebene
  Sollwert bleibt in HA stehen, wenn das Add‑on stirbt.

### AC‑gekoppelt heißt

Der Speicher hängt mit eigenem Wechselrichter am Hausnetz. Seine Lade‑ und
Entladeleistung erscheint am Netzübergabepunkt und damit im
`residual_power_entity`‑Sensor. Genau daraus entsteht die Hauptgefahr
([H‑1](#h-1--pool-aufschaukelung-kritisch)).

### Was nicht gebaut wird

Das HEMS schreibt **niemals direkt in Wechselrichter‑Register**. Es schreibt –
wie `BinaryDevice` heute schon – in HA‑Helfer; eine HA‑Automation übersetzt sie
in Modbus/API‑Aufrufe. Das bleibt so und ist auch für den Watchdog wichtig.

---

## 2. Ausgangslage im Bestand

| Ort | Was | Bedeutung für den Speicher |
|---|---|---|
| [devices.py:27](app/ems/devices.py#L27) | `Device` (ABC) | **zwei** neue Default‑Properties (`netz_support_w`, `gemessene_last_w`) |
| [devices.py:159](app/ems/devices.py#L159) | `ControllableDevice` – Rampen, Deadband, Min/Max, 2‑Pass‑Allokation | Ladepfad ist genau das → **erben** |
| [devices.py:295-313](app/ems/devices.py#L295-L313) | `_hems_power_w()` – „nur vom HEMS angeforderte Leistung zählt" | gilt fürs Laden; für die **Entladebasis** ausdrücklich **nicht** – dort zählt `_actual_w` vollständig (D‑B14/F‑5) |
| [devices.py:378](app/ems/devices.py#L378) / [devices.py:683](app/ems/devices.py#L683) | `_actual_w` bzw. `power_w if _actual_on` – Messwert **ohne** Force‑Modus‑Filter | Quelle der neuen Property `gemessene_last_w` |
| [devices.py:509-538](app/ems/devices.py#L509-L538) | `calculate_ramp` – bei Defizit sofort abregeln | Vorbild für die asymmetrische Entladedynamik (D‑B08) |
| [devices.py:391](app/ems/devices.py#L391) | `select_phases` – Hysterese über `_last_phase_change_ts` | Vorbild für die Umschaltsperre laden↔entladen |
| [devices.py:615](app/ems/devices.py#L615) | `BinaryDevice` – `anforderung_an` → HA‑Automation | Muster „HEMS schreibt Helfer, Automation schaltet real" |
| [controller.py:41](app/ems/controller.py#L41) | `_build_devices()` | neuer Zweig `class == "battery"` |
| [controller.py:135](app/ems/controller.py#L135) | `run_cycle()` – 12 Schritte | 2 neue Schritte, 2 geänderte Formeln |
| [controller.py:262-267](app/ems/controller.py#L262-L267) | `_calc_pool()` = `max(residual + Σ current_w, 0)` | **die `max()`‑Klemme wirft die Information weg, die wir brauchen** |
| [controller.py:182-184](app/ems/controller.py#L182-L184) | Defizit + `binary_immediate_off` | geändert |
| [main.py:140-144](app/main.py#L140-L144) | `_scheduler()`, `interval_s: 30` | ggf. zweiter, schneller Task (D‑B06) |
| [ha_client.py:41](app/ha_client.py#L41) | `fetch_all_states()` – holt **alle** States | für einen schnellen Subzyklus zu teuer → neue Methode nötig |
| [main.py:56](app/main.py#L56) / [main.py:77](app/main.py#L77) | `_ctrl_items_*` | neu: `_ctrl_items_battery` |
| [app.js:86-89](app/static/app.js#L86-L89) | Filter nach `d.type` | neuer Filter `'battery'` |
| [config.yaml:76](config.yaml#L76) | `class: list(controllable\|binary)` | → `…\|battery)` |

---

## 3. Die sieben Gefahren

Alle stammen aus zwei Wurzeln: **der Speicher ist bidirektional** (H‑1…H‑3)
und **das HEMS ist jetzt der Netzpunkt‑Regler** (H‑4…H‑7).

Nach Schwere für diese Anlage (3 s Takt, n Speicher geplant):

| | Gefahr | Schwere | Gegenmittel |
|---|---|---|---|
| **H‑1** | Pool‑Aufschaukelung | **kritisch** | `residual_bereinigt_w` (4.2) |
| **H‑2** | Defizit‑Maskierung | **kritisch** | `hausdefizit_w` (4.2) |
| **H‑3** | Doppelte Entladung bei n Speichern | **hoch** | zentrale Koordination (D‑B05/D‑B15) |
| **H‑7** | Sensor‑Versatz | **hoch** | Rampe auf Versatz dimensionieren |
| **H‑5** | Batterie‑Export bei Lastabwurf | mittel | 3 s Takt + Asymmetrie |
| **H‑6** | Träger Überschusssensor | mittel | Phase‑0‑Messung |
| **H‑4** | Totzeit | **gering** (Verzögerung, keine Instabilität) | – |

### H‑1 · Pool‑Aufschaukelung (kritisch)

Heute: `pool = max(residual_w + Σ current_w, 0)`.

Entlädt der Speicher mit 3 kW, steigt `residual_w` um 3 kW. Das HEMS liest das
als PV‑Überschuss, schaltet den Heizlüfter zu, der Netzbezug steigt, der
Speicher entlädt mehr, das HEMS sieht mehr „Überschuss" …
→ **Positive Rückkopplung, Speicher in einem Zyklus leer.**

### H‑2 · Defizit‑Maskierung

Heute: `current_deficit_w = max(-residual_w, 0)`.

Deckt der Speicher die Hauslast, ist `residual_w ≈ 0` → kein Defizit erkannt →
Verbraucher werden nicht abgeregelt → Heizstab läuft faktisch aus der Batterie.
Genau das, was du ausgeschlossen haben willst.

### H‑3 · Doppelte Entladung bei n Speichern

Berechnet jeder Speicher unabhängig „ich decke das Defizit", entladen bei 3
Speichern und 2 kW Defizit alle drei mit 2 kW → 4 kW gehen ins Netz. Die
Entladeseite **braucht eine Koordinationsstufe im Controller**.

### H‑4 · Totzeit – Verzögerung, **nicht** Instabilität

> **Korrektur ggü. v2 dieses Dokuments.** Dort stand „Takt ≥ ~3× Totzeit, sonst
> schwingt der Kreis". Diese Regel gilt für **integrierende** Regler, die auf
> ihre eigene Stellgröße zurückkoppeln. Die hier gewählte Struktur ist keiner.

Die Schleife hat Totzeit:

```
Zählerlatenz + HEMS-Zyklus + HA-Automation + Modbus-Write + WR-Rampe
   1…5 s     +     3 s     +     0…2 s     +   0,1…1 s   +  0,5…3 s
```

Entscheidend ist aber die **Form des Regelgesetzes**:

```
hausdefizit_w = max(-(residual_bereinigt_w + hems_last_w), 0)
                        └── enthält bereits −netz_support_w ──┘
entlade_soll_w = hausdefizit_w          # absolut, nicht inkrementell
```

`residual_bereinigt_w` zieht die **eigene Entladung** bereits ab. Der Sollwert
ist damit ein direktes Maß der *Hauslast* und hängt **nicht** von der eigenen
Stellgröße ab. Rechnerisch im eingeschwungenen Zustand (PV = 0, Hauslast `L`,
Entladung `D`):

```
residual_w           =  D − L
netz_support_w       =  D
residual_bereinigt_w = −L        ← D kürzt sich vollständig heraus
hausdefizit_w        =  L        ← unabhängig von D
```

**Es gibt in dieser Formulierung keine Rückkopplung, auf der ein Schwingen
aufbauen könnte.** Kommandiert das HEMS 2 kW und der Zähler zeigt die Wirkung
noch nicht, bleibt das Kommando im nächsten Zyklus bei 2 kW – es addiert sich
nichts auf. Totzeit erzeugt **Reaktionsverzögerung auf Laständerungen**, keine
Oszillation.

Deshalb läuft dein Heizstab bei 3 s stabil, und deshalb ist 3 s auch für den
Speicher unkritisch – solange die beiden Messwerte zueinander passen (→ H‑7).

### H‑5 · Batterie‑Export bei Lastabwurf (bei 3 s deutlich entschärft)

Backofen (3 kW) schaltet ab, der Speicher entlädt bis zur nächsten Korrektur
weiter → **Batteriestrom ins Netz**.

Die Kosten sind asymmetrisch:

| Fehler | Kosten |
|---|---|
| 100 W zu wenig entladen (Restbezug) | ~0,30 €/kWh Netzbezug |
| 100 W zu viel entladen (Export) | Differenz Bezugspreis − Einspeisevergütung ~0,22 €/kWh, **plus** ein Speicherzyklus für nichts |

**Größenordnung bei 3 s Takt:** 3 kW × ~8 s (Totzeit + Zyklus) ≈ 0,007 kWh je
Ereignis. Bei 20 Ereignissen/Tag ≈ 0,13 kWh/Tag ≈ **12 €/Jahr**. Bei 30 s Takt
wäre es das Vier‑ bis Fünffache. Der schnelle Takt erledigt hier den Großteil
der Arbeit.

Die Asymmetrie (D‑B08) bleibt trotzdem sinnvoll – sie kostet nichts und
halbiert den Rest. Der `entlade_abschlag_w` kann bei 3 s dagegen klein
ausfallen (Vorschlag 20–30 W statt 50–100 W), weil er im eingeschwungenen
Zustand **dauerhaft** Netzbezug erzeugt, während der Export nur transient ist.

> **Zusätzlich prüfen:** Je nach Anlagenkonstellation und Förderung kann das
> Einspeisen von Batteriestrom regulatorisch problematisch sein. Kein
> Rechtsrat – vor Inbetriebnahme mit Netzbetreiber bzw. Anlagendokumentation
> abgleichen. Falls harte Einspeisefreiheit gefordert ist, muss
> `entlade_abschlag_w` deutlich größer und ein zusätzlicher Export‑Stopp rein.

### H‑6 · Trägheit des Überschusssensors

Der Überschusssensor ist die Regelgrößen‑Quelle – seine Aktualisierungsrate ist
die harte Obergrenze für die Regelgüte. Ein 3‑s‑Takt auf einem Sensor, der nur
alle 10 s aktualisiert, ist Überabtastung: zwei von drei Zyklen rechnen mit
Daten, die schon verarbeitet wurden.

Das ist **nicht instabil** (siehe H‑4), aber es macht die Rampenzeiten
(`hoch_regelzeit_s`) unwirksam, weil `last_changed` schneller altert als der
Messwert. → Phase 0: Update‑Intervall des Sensors messen.

Kommt `residual_power_entity` von einem Shelly 3EM, ist die Rate typischerweise
~1 s (lokal, Push) – dann passt 3 s gut. Über Cloud/Polling kann sie deutlich
schlechter sein.

### H‑7 · Sensor‑Versatz zwischen Zähler und Batteriemesswert (das echte Oszillationsrisiko)

`residual_bereinigt_w = residual_w − netz_support_w` subtrahiert zwei Messwerte
aus **verschiedenen Quellen mit verschiedener Latenz**:

* `residual_w` – Netzzähler (Shelly 3EM)
* `netz_support_w` – Batterie‑Leistungssensor (Wechselrichter, Modbus)

Sind die nicht synchron, entsteht ein Fehler, der **direkt in den Sollwert
durchschlägt**:

| Situation | Folge |
|---|---|
| Zähler zeigt neue Entladung, Batteriesensor noch den alten (kleineren) Wert | `residual_bereinigt_w` zu hoch → `hausdefizit_w` zu klein → Entladung wird gekappt |
| Nächster Zyklus: Batteriesensor holt auf | `hausdefizit_w` springt zurück → Entladung wieder hoch |

→ **Grenzzyklus mit der Periode des Versatzes.** Das ist der einzige Mechanismus
in diesem Entwurf, der wirklich schwingen kann – und er hat nichts mit der
Totzeit zu tun.

**Gegenmittel, in dieser Reihenfolge:**

1. Beide Messwerte möglichst aus derselben Quelle/Abtastung beziehen.
2. `hoch_regelzeit_s` ≥ gemessener Versatz – die Rampe überbrückt das Fenster.
   **Das ist die eigentliche Dimensionierungsregel für die Rampe**, nicht die
   Totzeit.
3. `umschalt_totzone_w` großzügig genug, damit der Versatzfehler unterhalb der
   Totzone bleibt.

→ Phase 0: Versatz messen (Sprungversuch, beide Sensoren in der HA‑History
übereinanderlegen).

---

## 4. Grundmodell: `pool_roh_w` und `hausdefizit_w`

### 4.1 Vorzeichenkonvention (verbindlich)

| Größe | Zeichen | Bedeutung |
|---|---|---|
| `residual_w` | `+` Einspeisung / `−` Netzbezug | wie heute, unverändert |
| `lade_ist_w`, `lade_soll_w` | immer `≥ 0` | Speicher nimmt auf (Last) |
| `entlade_ist_w`, `entlade_soll_w` | immer `≥ 0` | Speicher gibt ab (Quelle) |
| `netto_w` | `+` laden / `−` entladen | nur Anzeige: `lade_w − entlade_w` |

### 4.2 Die zentrale Einsicht

Der heutige Pool ist definiert als *„welcher Überschuss bestünde, wenn alle
HEMS‑Geräte aus wären"*. Die `max(…, 0)`‑Klemme in
[`_calc_pool`](app/ems/controller.py#L267) wirft dabei die negative Hälfte weg.

**Genau diese negative Hälfte ist der Entladebedarf, den du beschreibst.**

```
netz_support_w       = Σ entlade_ist_w          (gemessen, über alle Speicher)
residual_bereinigt_w = residual_w − netz_support_w
hems_last_w          = Σ d.current_w            (nur HEMS-angeforderte Last)
hems_last_gemessen_w = Σ d.gemessene_last_w     (Messwert, inkl. fremdgesteuert)

pool_roh_w      = residual_bereinigt_w + hems_last_w            ← NEU, ungeklemmt
entlade_basis_w = residual_bereinigt_w + hems_last_gemessen_w   ← NEU (F-5)

pool_w        = max( pool_roh_w,      0)  ← unverändert: Überschuss zum Verteilen
hausdefizit_w = max(−entlade_basis_w, 0)  ← NEU: was der Speicher decken soll
```

`pool_roh_w` ist „PV minus Hausgrundlast", ohne HEMS‑Lasten und ohne
Batteriestützung:

* **positiv** → PV‑Überschuss → verteilen an Verbraucher und Speicher‑Laden
* **negativ** → die Hausgrundlast übersteigt die PV → **Entladebedarf**

Die Überschussverbraucher sind **per Konstruktion draußen**, weil ihre
Leistung zurückaddiert wurde. Es braucht keine Heuristik über `max_relief_w`,
keine Sonderbehandlung – die Abgrenzung „nur Hausverbrauch, nicht
Überschussverbraucher" fällt direkt aus der bestehenden Pool‑Definition.

#### Warum zwei Summen und nicht eine (F‑5 / D‑B14)

`current_w` filtert Force‑Modus heraus ([devices.py:295-305](app/ems/devices.py#L295-L305)):
ein von Hand eingeschalteter Heizstab liefert `current_w = 0`. Für den **Pool**
ist das richtig – diese Leistung kann das HEMS nicht freigeben. Für die
**Entladeseite** wäre es falsch: der fremdgesteuerte Heizstab landete im
Hausverbrauch und der Speicher würde ihn decken. Genau das ist mit F‑5
verneint.

Deshalb wird für die Entladebasis der **volle Messwert** zurückaddiert:

```python
# Device (ABC), Default für reine Verbraucher = _actual_w bzw. power_w
@property
def gemessene_last_w(self) -> float: ...
```

Es gilt je Gerät `gemessene_last_w ≥ current_w` (der Force‑Anteil ist die
Differenz) und damit `entlade_basis_w ≥ pool_roh_w`:

| Fall | `current_w` | `gemessene_last_w` | Wirkung |
|---|---|---|---|
| Heizstab vom HEMS auf 2 kW | 2000 | 2000 | identisch, kein Unterschied |
| Heizstab von Hand auf 2 kW, HEMS fordert 0 | 0 | 2000 | Pool unverändert; `hausdefizit_w` **2 kW kleiner** → Speicher deckt ihn nicht |
| Speicher lädt 3 kW aus dem Netz (v2) | 0 | 3000 | verhindert, dass ein **anderer** Speicher diese 3 kW als Hauslast deckt (Kreisstrom über zwei Geräte) |

Der letzte Fall ist der Grund, warum die Battery‑Seite ihre Ladeleistung in
`gemessene_last_w` **immer** meldet, auch wenn `current_w` bei Netzladen
bewusst 0 ist (7.3). D‑B16 sperrt nur die Entladung **desselben** Speichers;
gegen den Kreisstrom über zwei Speicher schützt erst diese Summe.

### 4.3 Vier Formeln, zwei Bedeutungen

```python
# Verbraucher-Abregelung: echter Netzbezug ohne Batteriestützung
current_deficit_w = max(-residual_bereinigt_w, 0.0)

# Speicher-Entladung: Hausgrundlast-Defizit ohne JEDE HEMS-Geräte-Last
hausdefizit_w     = max(-entlade_basis_w, 0.0)
```

Es gilt immer `hausdefizit_w ≤ current_deficit_w`, weil
`hems_last_gemessen_w ≥ 0`. Die Differenz ist genau die gemessene HEMS‑Last:

```
current_deficit_w − hausdefizit_w  =  min(hems_last_gemessen_w, current_deficit_w)
```

Davon ist nur der Anteil `hems_last_w` durch das HEMS abregelbar; der
Force‑Anteil bleibt Netzbezug. Das ist gewollt: einen von Hand
eingeschalteten Heizstab soll weder der Speicher decken noch das HEMS
stillschweigend als Grundlast behandeln.

**Arbeitsteilung, die daraus folgt:**

| Anteil des Defizits | Wird gedeckt durch |
|---|---|
| `hausdefizit_w` | Speicher‑Entladung |
| HEMS‑angeforderte Last | Abregeln der Verbraucher (bestehende Logik, [devices.py:525-526](app/ems/devices.py#L525-L526)) |
| Force‑Anteil | niemand – bleibt Netzbezug (F‑5) |

Alles läuft im selben Zyklus parallel und stört sich nicht.

### 4.4 Warum das die Invariante geschenkt liefert

`pool_w > 0` ⇒ `hausdefizit_w == 0` und umgekehrt – die beiden schließen sich
mathematisch aus. Damit gilt **„nie gleichzeitig laden und entladen"**
strukturell, nicht per nachträglicher Prüfung.

Der Beweis überlebt die zweite Summe aus 4.2, weil sie nur in **eine**
Richtung abweicht:

```
gemessene_last_w ≥ current_w   (je Gerät, der Force-Anteil ist die Differenz)
⇒ entlade_basis_w ≥ pool_roh_w
⇒ pool_w > 0 ⇒ pool_roh_w > 0 ⇒ entlade_basis_w > 0 ⇒ hausdefizit_w = 0   ✓
```

Die Umkehrung gilt ebenso (`hausdefizit_w > 0 ⇒ entlade_basis_w < 0 ⇒
pool_roh_w < 0 ⇒ pool_w = 0`). Property P2 bleibt damit unverändert gültig
und wird in [15.3](#153-property-tests-in-teststest_allocation_propertiespy)
gegen **beide** Summen getestet.

> **Ausnahme:** Netzladen ([Abschnitt 11](#11-netzladen-mit-dynamischen-tarifen-vorbereitung))
> bricht diese Eigenschaft bewusst auf – dort wird bei `hausdefizit_w > 0`
> geladen. Deshalb braucht Netzladen eine **explizite** Vorrangregel gegenüber
> dem Entladen, sonst entsteht ein Kreisstrom Netz→Speicher→Haus.

### 4.5 Warum „gemessen" und nicht „angefordert"

| Richtung | Basis | Begründung |
|---|---|---|
| **Laden** → `current_w` | `min(lade_ist_w, lade_anf_w)` | Force‑Modus‑Regel wie bei allen Verbrauchern ([devices.py:295](app/ems/devices.py#L295)): extern erzwungenes Laden kann das HEMS nicht freigeben |
| **Entladen** → `netz_support_w` | `entlade_ist_w` (**immer Messwert**) | Jede Entladung verfälscht `residual_w`, unabhängig von der Ursache. Wichtig bei Sollwert‑Nachlauf, WR‑Derating und im Hüllen‑Modus (D‑B05), wo der WR unterhalb der Hülle selbst regelt |
| **Entladebasis** → `gemessene_last_w` | `_actual_w` bzw. `power_w` (**immer Messwert**) | F‑5: fremdgesteuerte HEMS‑Lasten sollen der Speicher **nicht** decken. Der Force‑Filter aus `current_w` würde sie genau dorthin schieben |

### 4.6 Stabilität

Sollwert `entlade_soll = hausdefizit_w − abschlag_w`.

Setzt der Speicher das um, steigt `residual_w` um denselben Betrag,
`residual_bereinigt_w` bleibt aber unverändert → `hausdefizit_w` bleibt
konstant → **Fixpunkt**. Sinkt die Hauslast, sinkt `hausdefizit_w`, die
Entladung wird zurückgenommen.

Der Kreis konvergiert gegen „Netzbezug = `abschlag_w`". Die
**Konvergenzgeschwindigkeit** ist durch Taktzeit und Rampe begrenzt – das ist
H‑4/H‑5, nicht ein Stabilitätsproblem der Formel.

---

## 5. Regelgüte bei 3 s Takt

Mit `interval_s = 3` ist die Taktzeit **kein** limitierender Faktor mehr – der
HEMS‑Zyklus ist schneller als jede Alternative (Shelly‑Eigenregelung >5 s).
Die verbleibenden Themen sind Sensor‑Versatz (H‑7), Asymmetrie und
Schreiblast.

### 5.1 Was bei 3 s die Regelgüte bestimmt

| Faktor | Beitrag | Handhabung |
|---|---|---|
| Taktzeit 3 s | klein | erledigt |
| Totzeit ~5–10 s | Verzögerung, keine Instabilität (H‑4) | Rampe |
| **Sensor‑Versatz** | **Oszillationsrisiko** (H‑7) | **Rampe auf Versatz dimensionieren** |
| Sensor‑Update‑Rate | Obergrenze der Reaktionszeit (H‑6) | Phase 0 messen |
| Schreiblast auf HA | 10× mehr Writes als bei 30 s | Deadband (D‑B08) |

Fehlmenge je Lastsprung ≈ `Sprunghöhe × (Totzeit + Taktzeit)`. Bei 3 kW und
~8 s ≈ 0,007 kWh – bei 20 Sprüngen/Tag ≈ 0,13 kWh/Tag. Das ist die Größe, gegen
die alle weiteren Optimierungen antreten. Viel ist da nicht mehr zu holen.

### 5.2 Die Rampe ist das Stabilitätswerkzeug, nicht die Taktzeit

Weil H‑4 entschärft und H‑7 das reale Risiko ist, ergibt sich eine klare
Dimensionierungsregel:

> **`hoch_regelzeit_s` ≥ gemessener Sensor‑Versatz.**
> Die Rampe überbrückt genau das Fenster, in dem Zähler und Batteriesensor
> nicht zueinander passen.

Bei 3 s Takt und z. B. 6 s Versatz heißt das: `hoch_regelzeit_s ≈ 6…9`, also
Korrektur nur jeden zweiten bis dritten Zyklus. Zusätzlich begrenzt
`max_anderung_pro_schritt_w` die Sprunghöhe.

**Optional, falls die Absolutschritt‑Begrenzung zu grob ist:** eine
proportionale Dämpfung statt eines festen Schrittes.

```python
# P-Anteil: nur einen Bruchteil des Fehlers je Zyklus stellen.
# K_p ≈ Taktzeit / (Versatz + Taktzeit), gedeckelt auf 0,5
schritt_w = self.entlade_regelverstarkung * (ziel_w - self._entlade_anf_w)
schritt_w = max(-self.max_anderung_pro_schritt_w,
                min(schritt_w, self.max_anderung_pro_schritt_w))
```

Vorteil gegenüber dem festen Schritt: die Korrektur skaliert mit dem Fehler –
große Lastsprünge werden schnell, kleine Restfehler sanft ausgeregelt. Der
feste Schritt bleibt als harter Deckel darüber.

> **Empfehlung:** In Phase 3 mit dem geerbten Absolutschritt starten (kein
> neuer Mechanismus). `entlade_regelverstarkung` nur einbauen, wenn die
> Messung in Phase 3 zeigt, dass ein einziger Schrittwert nicht beide
> Betriebspunkte (kleiner Restfehler / großer Lastsprung) abdeckt.

### 5.3 Asymmetrie – billig und weiterhin sinnvoll

Aus H‑5 (Export kostet mehr als Bezug) folgt:

**Aber nicht naiv „runter immer sofort".** H‑5 und H‑7 ziehen hier in
entgegengesetzte Richtungen:

* H‑5 will *schnell runter*, damit kein Batteriestrom exportiert wird.
* H‑7 will *gedämpft runter*, weil ein kurzzeitig zu klein gemessenes
  `hausdefizit_w` sonst die Entladung einbrechen lässt – und genau daraus wird
  der Grenzzyklus.

Ein sofortiges, ungedämpftes Absenken würde H‑7 also **verstärken**. Die
Auflösung: nach Sprunghöhe unterscheiden.

```python
def _ramp_entladen(self, ziel_w: float) -> float:
    """RUNTER schnell bei echtem Lastabwurf, gedämpft bei kleinen Abweichungen.

    Grosse Absenkungen sind reale Lastabwuerfe (Backofen aus) -> sofort, sonst
    exportieren wir Batteriestrom (H-5).
    Kleine Absenkungen sind meist Sensor-Versatz oder Rauschen -> daempfen,
    sonst entsteht ein Grenzzyklus (H-7).
    """
    delta = self._entlade_anf_w - ziel_w                  # > 0 = runter

    if delta > self.entlade_sofort_schwelle_w:            # echter Lastabwurf
        return ziel_w                                     # sofort, ungerampt
    if delta > 0:                                         # kleine Abweichung
        return max(ziel_w, self._entlade_anf_w - self.max_anderung_pro_schritt_w)

    if self._entlade_age_s < self.hoch_regelzeit_s:       # HOCH: gerampt
        return self._entlade_anf_w
    return min(ziel_w, self._entlade_anf_w + self.max_anderung_pro_schritt_w)
```

`entlade_sofort_schwelle_w` (Vorschlag 300 W) trennt die beiden Regime. Sie
muss **größer als der Sensor‑Versatzfehler** sein – der wird in Phase 0
gemessen.

Die Richtungsasymmetrie bleibt damit erhalten (runter kann sofort, hoch nie),
ist aber gegen H‑7 abgesichert. Konzeptionell spiegelbildlich zur bestehenden
Verbraucherlogik in [devices.py:519-531](app/ems/devices.py#L519-L531) – dort ist
„runter" schnell, weil Netzbezug teuer ist; hier, weil Batterieexport teuer ist.

### 5.4 Unterschuss‑Abschlag

```
entlade_soll_w = max(hausdefizit_w − entlade_abschlag_w, 0)
```

Sorgt dafür, dass im eingeschwungenen Zustand ein kleiner Restbezug bleibt
statt eines Exports.

**Bei 3 s Takt klein halten – Vorschlag 20–30 W.** Begründung: Der Abschlag
kostet **dauerhaft** Netzbezug, der Export ist nur **transient**. Bei 30 s Takt
lohnte ein größerer Abschlag, weil die Transienten lang waren; bei 3 s dreht
sich das Verhältnis um. 30 W Dauerbezug ≈ 260 kWh/Jahr wären deutlich teurer
als die ~12 €/Jahr Exportverlust aus H‑5.

> **F‑9 beantwortet:** Für diese Anlage besteht Anspruch auf
> Einspeisevergütung, Batterieexport ist zulässig. Die Rechnung oben gilt
> also unverändert: **kleiner Abschlag (20–30 W), kein harter Export‑Stopp.**
> Der transiente Export wird vergütet, nur der Round‑Trip‑Verlust bleibt.
> Die Ausnahme aus v3 („bei Einspeiseverbot Abschlag hochziehen") entfällt –
> sie müsste erst wieder eingeführt werden, wenn sich die Förderlage ändert.

### 5.5 Was mit 3 s **nicht** mehr nötig ist

Aus v2 dieses Dokuments gestrichen:

* **Separater Speicher‑Subzyklus** (`_battery_scheduler`, `fetch_states()`,
  `asyncio.Lock`, Eigentumsregeln). Der Hauptzyklus ist bereits schnell genug;
  ein zweiter Regelpfad wäre reine Komplexität mit eigenem Ausfallmodus.
* **Phase 3b** entfällt ersatzlos.
* **Option `battery_interval_s`** in der Add‑on‑Config entfällt.

Damit spart der Entwurf ~60 Zeilen Code, einen zweiten Watchdog und eine
Klasse von Schreibkonflikten.

**Schreiblast beachten:** Bei 3 s und n Speichern sind es bis zu
`3 Writes × n` alle 3 Sekunden. Das Deadband (D‑B08) ist deshalb nicht nur
für die Rampen‑Alterung wichtig, sondern auch für die HA‑Last. Im
eingeschwungenen Zustand soll **gar nichts** geschrieben werden.

---

## 6. Architekturentscheidungen

### D‑B01 · `BatteryDevice` erbt von `ControllableDevice`

**Empfehlung: ja.**

*Pro:* Der Ladepfad ist funktional deckungsgleich mit einem regelbaren
Verbraucher – Rampen, Deadband, `min_/max_technisch_w`, die 2‑Pass‑Allokation
([controller.py:212-228](app/ems/controller.py#L212-L228)), `schutz_w`‑Reservierung
und die EP‑Übernahme funktionieren ohne eine Zeile neuen Code. Der
`isinstance(d, ControllableDevice)`‑Filter in
[controller.py:219](app/ems/controller.py#L219) nimmt den Speicher automatisch
in die Ladeallokation auf.

*Zu überschreiben:*

| Member | Grund |
|---|---|
| `current_w` | `_actual_w` = **Ladeleistung**, nicht netto; bei Netzladen 0 (siehe Abschnitt 11) |
| `gemessene_last_w` | Ladeleistung **immer**, auch bei Netzladen (D‑B14) |
| `netz_support_w` | neu, gemessene Entladung |
| `max_relief_w` | abschaltbare Ladeleistung, **ohne** `− min_technisch_w` |
| `select_phases()` | No‑Op |
| `calculate_ramp()` | asymmetrische Entladedynamik + Richtungsauflösung |
| `get_write_ops()` | drei Ausgabe‑Entitäten, feste Reihenfolge |
| `to_status_dict()` | `type: "battery"` + Speicherfelder |

*Alternative:* eigenständig von `Device` + gemeinsamer `_RampLimiter`. Sauberer
getrennt, aber ~60 Zeilen Duplikat und manuelles Einhängen in alle
Controller‑Schleifen. **Nur wechseln, wenn die Overrides in Phase 2 ausufern.**

### D‑B02 · Ladepriorität über die bestehende `prioritat`

> Gilt ausschließlich für die **Ladeseite**. Die Entladereihenfolge hat seit
> F‑3 eine eigene Größe → [D‑B17](#d-b17--getrennte-lade-und-entladepriorität).

Kein Sonderweg – der Speicher konkurriert in derselben Sortierung wie alle
anderen. Damit sind beide Strategien reine Konfiguration:

* `prioritat = 1` → Speicher zuerst voll, dann Heizstab (Winter)
* `prioritat = 50` → Heizstab/Wallbox zuerst, Speicher nimmt den Rest (Sommer)

Round‑Trip‑Wirkungsgrad ~85–90 %: Direktnutzung im Heizstab ist energetisch
besser – aber nur, wenn die Wärme gebraucht wird. Nutzerentscheidung, keine
Automatik. Die dynamische Bewertung ist Energy‑Pilot‑Territorium
([Abschnitt 13](#13-energy-pilot-anbindung)).

### D‑B03 · Messpunkt des Überschusssensors

Die Formeln aus 4.2 setzen voraus, dass der Speicher in `residual_w`
**enthalten** ist (Sensor am Netzübergabepunkt). Manche Installationen rechnen
`residual_power_entity` bereits als „PV − Hauslast" ohne Speicher.

Neue globale Add‑on‑Option:

```yaml
speicher_in_residual_enthalten: true   # Default
```

* `true`  → `residual_bereinigt_w = residual_w − netz_support_w` (AC‑gekoppelt, Normalfall)
* `false` → `residual_bereinigt_w = residual_w`

**Muss beim Setup verifiziert werden** – ein Fehler hier *ist* H‑1.
Prüfrezept: HEMS deaktivieren, Speicher manuell auf 1 kW Entladung zwingen,
prüfen ob `residual_power_entity` um 1 kW steigt. Steigt es → `true`.

> **F‑10 beantwortet:** Es wird die **Netzübergabeleistung** angegeben, und
> dieser eine Wert gilt für alle Speicher. Damit steht fest:
> `speicher_in_residual_enthalten = true` ist für diese Anlage korrekt, es gibt
> **einen** Messpunkt und nicht einen pro Speicher. Der Einwand 1 aus D‑B05
> (n autonome Regler auf derselben Messgröße) gilt damit ohne Abschwächung –
> zentrale Koordination ist zwingend, nicht optional.
>
> Nicht beantwortet ist damit die **Quelle** dieses Sensors → F‑12 bleibt
> offen, weil sie den Sensor‑Versatz (H‑7) und damit `hoch_regelzeit_s`
> bestimmt.

### D‑B04 · Betriebsarten

`input_select.ems_<prefix>_betriebsart`:

| Wert | Laden | Entladen | Einsatz |
|---|---|---|---|
| `auto` | HEMS regelt | HEMS regelt | Normalbetrieb |
| `nur_laden` | HEMS regelt | gesperrt | Speicher soll füllen |
| `nur_entladen` | gesperrt | HEMS regelt | z. B. vor angekündigtem PV‑Überschuss |
| `standby` | 0 | 0 | stillgelegt, Messwerte fließen weiter |
| `inverter` | – | – | **Shelly‑Nulleinspeisung dieses Speichers aktivieren** – Rückfallebene, nicht Normalbetrieb |

`inverter` ist im laufenden Betrieb **nie** der Zielzustand – solange das HEMS
regelt, muss die Shelly‑Regelung aus sein (D‑B05). Er wird ausschließlich als
sicherer Zustand des designierten Fallback‑Speichers geschrieben
(`shelly_fallback: true`, siehe [12.1](#121-der-sichere-zustand-hängt-vom-wechselrichter-ab)).
Bei allen anderen Speichern ist der sichere Zustand `standby`.

### D‑B05 · Warum HEMS zentral regelt und nicht jeder Speicher für sich

> **Diese Entscheidung ist gegenüber v2 umgekehrt.** Dort war `wr_huelle`
> (Wechselrichter/Shelly regelt selbst, HEMS setzt nur die Obergrenze) die
> Empfehlung. Zwei Einwände kippen sie.

#### Einwand 1 – dezentrale Nulleinspeisung skaliert nicht auf n > 1

Zwei autonome Regler am selben Netzpunkt messen dieselbe Größe
`grid = L − D₁ − D₂` und wollen sie beide auf 0 ziehen. Das Gleichgewicht
verlangt `D₁ + D₂ = L` – **eine Gleichung, zwei Unbekannte.** Es gibt unendlich
viele Lösungen und nichts wählt eine aus.

Was praktisch passiert (Hauslast 3 kW, zwei Speicher à 2 kW):

```
t0  beide sehen 3 kW Bezug   → beide fahren hoch
t1  beide bei 2 kW           → 1 kW Export → beide sehen Export → beide runter
t2  beide bei 0,5 kW         → 2 kW Bezug  → beide hoch
    …Grenzzyklus, Periode ≈ 2× Reglertotzeit
```

Verschärfend: Mit `min_entladeleistung_w > 0` kann bei kleiner Hauslast keiner
unter sein Minimum – es springt hart zwischen „einer an" und „beide an".

Der einzige dezentrale Fix wäre **Droop**: jedem Regler einen anderen
Sollwert‑Offset bzw. eine andere Verstärkung geben, damit sie sich natürlich
aufteilen. Funktioniert prinzipiell, aber:

* kein SoC‑Bewusstsein → der volle Speicher wird nicht bevorzugt entladen
* keine Prioritäten, keine Tarif‑Logik (Abschnitt 11) möglich
* pro Shelly von Hand zu tunen, driftet bei jeder Konfig‑Änderung
* die Aufteilung hängt von Lastniveau und Bauteiltoleranzen ab, nicht von
  deiner Absicht

→ **Für n > 1 ist zentrale Koordination die einzige Architektur, die
deterministisch aufteilt.** Genau das leistet
[`_allocate_discharge`](#d-b15--entlade-koordination-im-controller-nicht-im-gerät).

#### Einwand 2 – der Shelly ist langsamer als das HEMS

Shelly‑Regelung >5 s gegen HEMS‑Zyklus 3 s. Damit fällt das Argument
„bessere Regelgüte durch den WR" auch für **n = 1** weg. Es gibt keinen
Betriebspunkt mehr, an dem `wr_huelle` besser wäre.

#### Konsequenz

`entlade_regelmodus` wird auf **einen** Wert reduziert: HEMS schreibt den
exakten Sollwert.

```
input_select.ems_<p>_entlade_regelmodus  →  entfällt
input_number.ems_<p>_huellen_aufschlag_w →  entfällt
```

**Die Shelly‑Nulleinspeisung bleibt trotzdem installiert und konfiguriert** –
aber deaktiviert, als Rückfallebene. Sie ist damit der wertvollste Teil des
Watchdogs ([12.2](#122-watchdog--pflicht-nicht-empfehlung)): stirbt das HEMS,
übernimmt genau **ein** designierter Speicher wieder seine Shelly‑Regelung,
alle anderen gehen auf `standby`. Ein einzelner autonomer Regler hat das
Aufteilungsproblem nicht – deshalb funktioniert der Fallback, obwohl die
Dauerlösung nicht funktioniert.

Neues Konfigfeld dafür:

```yaml
shelly_fallback: true      # dieser Speicher übernimmt bei HEMS-Ausfall
                           # DARF BEI HÖCHSTENS EINEM SPEICHER true SEIN
```

`_build_devices` muss das validieren und bei mehr als einem `true` einen Fehler
loggen und alle bis auf den ersten auf `false` zwingen – sonst baut man sich
den Grenzzyklus als Fehlerfall wieder ein.

#### Wichtig im Normalbetrieb

Solange das HEMS regelt, **muss die Shelly‑Regelung aus sein.** HEMS und Shelly
gleichzeitig aktiv = zwei Regler auf einer Größe = derselbe Grenzzyklus wie in
Einwand 1, nur mit einem Speicher. Das Umschalten gehört in die
HA‑Automation, die auch die Sollwerte überträgt.

### D‑B06 · Kein separater Speicher‑Subzyklus

Bei `interval_s = 3` ist der Hauptzyklus schnell genug. Der in v2 geplante
`_battery_scheduler` (eigener Task, `fetch_states()`, `asyncio.Lock`,
Eigentumsregeln, zweiter Watchdog) **entfällt ersatzlos** – siehe
[5.5](#55-was-mit-3-s-nicht-mehr-nötig-ist).

Sollte sich später herausstellen, dass 3 s nicht reichen, ist der einfachere
Hebel `interval_s` selbst (Untergrenze laut Schema:
[config.yaml:69](config.yaml#L69) erlaubt `int(1,300)`). Bremse ist dann
`fetch_all_states()` ([ha_client.py:41](app/ha_client.py#L41)), das bei jedem
Zyklus den kompletten HA‑Zustand überträgt – das wäre der Punkt, an dem sich
gezieltes Polling lohnt, nicht ein zweiter Regelpfad.

### D‑B07 · Entladeplanung **nach** der Verbraucher‑Allokation

In v1 dieses Dokuments stand die Entladeplanung vor der Verbraucherverteilung
und musste mit `max_relief_w` schätzen. Mit `pool_roh_w` ist das unnötig –
aber die Reihenfolge bleibt trotzdem wichtig:

`hausdefizit_w` beruht auf `hems_last_w = Σ current_w`, also den **gemessenen**
HEMS‑Lasten aus dem HA‑Snapshot. Diese Größe steht direkt nach Schritt 2 fest,
die Entladeplanung könnte also früh laufen. Sie läuft trotzdem **nach** der
Verbraucher‑Allokation, damit sie optional die *geplanten* statt der
*gemessenen* Verbraucherleistungen nutzen kann:

```python
# Vorausschauende Variante (Phase 4): Verbraucher, die dieses Mal abgeregelt
# werden, verschwinden bereits im nächsten Zyklus aus hems_last_w - das
# vorwegzunehmen vermeidet einen Zyklus Unterdeckung.
hems_last_geplant_w = sum(d.new_w for d in ctrl) + sum(d.power_w for d in bin if d.final_on)
hausdefizit_prognose_w = max(-(residual_bereinigt_w + hems_last_geplant_w), 0.0)
```

Für v1 reicht die gemessene Variante. Die Reihenfolge kostet nichts und hält
den Weg offen. **Zwingend ist nur: vor `calculate_ramp`**, weil der Speicher
dort seine Richtung auflöst.

### D‑B08 · Asymmetrische Entladedynamik

Siehe [Abschnitt 5.2](#52-asymmetrie-ist-die-billigste-verbesserung). Dazu:

* `entlade_abschlag_w` – bewusster Unterschuss, Default 50 W
* `umschalt_totzone_w` – Netto‑Wunsch betragsmäßig darunter → `standby`,
  verhindert Mikrozyklen
* `min_umschaltzeit_s` – Sperrzeit nach Richtungswechsel laden↔entladen,
  Zustand `_last_direction_change_ts` überlebt Zyklen (Geräte sind langlebig,
  [controller.py:4-7](app/ems/controller.py#L4-L7))
* **Deadband beim Schreiben** – gleiche Begründung wie
  [devices.py:543-546](app/ems/devices.py#L543-L546): würde jeden Zyklus derselbe
  Wert geschrieben, setzte das `last_changed` zurück und die Rampen‑Alterung
  wäre kaputt. Gilt für alle drei neuen Ausgabe‑Entitäten.
  **Ausnahme: beim Senken der Entladeleistung kein Deadband** – dort zählt
  Geschwindigkeit mehr als Schreibsparsamkeit.

### D‑B09 · SoC‑Grenzen mit Taper

Reale Wechselrichter drosseln nahe der Grenzen (CV‑Phase). Ohne Nachbildung
sitzt das HEMS auf einem Sollwert, den der Speicher nicht liefert – das
Ist/Soll‑Delta wandert in `residual_w` und stört die Regelung.

```python
def _lade_limit_w(self) -> float:
    if not self.laden_erlaubt or self._soc >= self.soc_max_prozent:
        return 0.0
    kopf = self.soc_max_prozent - self._soc
    basis = self.max_ladeleistung_w
    if 0 < self.soc_taper_band_prozent and kopf < self.soc_taper_band_prozent:
        basis *= kopf / self.soc_taper_band_prozent
    return min(basis, self._wr_lade_limit_w())     # WR-Derating hat Vorrang
```

Analog `_entlade_limit_w()` gegen `soc_min_prozent` bzw. `soc_reserve_prozent`.
Optionale Entitäten `available_charge_power_entity` /
`available_discharge_power_entity` (Temperatur‑, Zell‑Derating) haben Vorrang.

Hysterese am Deckel: `soc_max_hysterese_prozent` (z. B. 2 %), damit bei 100 %
nicht im Takt zwischen Laden und Standby geflippt wird.

### D‑B10 · Netzladen: architektonisch vorbereiten, in v1 gesperrt

In v1 gilt hart:

```python
if hausdefizit_w > 0 and not self.netzladen_aktiv:
    lade_soll_w = 0.0
```

`netzladen_aktiv` ist in v1 immer `False`. Die Klemme ist die Absicherung gegen
Rechenfehler an anderer Stelle. Die Schnittstellen für v2 stehen in
[Abschnitt 11](#11-netzladen-mit-dynamischen-tarifen-vorbereitung) und sind so
gewählt, dass später **keine Config‑Migration** nötig ist.

### D‑B11 · Ausgabe über HA‑Helfer, feste Reihenfolge

```
input_number.ems_<prefix>_anforderung_ladeleistung_w
input_number.ems_<prefix>_anforderung_entladeleistung_w
input_select.ems_<prefix>_anforderung_betriebsart      # laden|entladen|standby|inverter
```

`get_write_ops()` liefert in fester Reihenfolge: **Betriebsart zuerst, dann
Leistung.** Viele Wechselrichter brauchen den Moduswechsel vor dem
Leistungsregister. Beim *Abschalten* die umgekehrte Reihenfolge (erst Leistung
auf 0, dann Modus) – sonst kann ein Modussprung bei stehender Leistung einen
Stromstoß erzeugen.

> Konfigfeld `steuerprofil` reserviert für spätere Varianten
> (`zwei_entitaeten` | `signiert` | `modus_und_leistung`). v1 baut nur
> `zwei_entitaeten` + Betriebsart.

### D‑B12 · Ist‑Leistung: zwei Sensoren oder einer signiert

```yaml
# Variante A - getrennte Sensoren (bevorzugt, eindeutig)
charge_power_entity:    sensor.speicher_1_ladeleistung
discharge_power_entity: sensor.speicher_1_entladeleistung

# Variante B - ein signierter Sensor
power_entity: sensor.speicher_1_leistung
power_sign:   positiv_laden          # oder positiv_entladen
```

Intern immer normalisieren:

```python
if self.power_entity:
    p = safe_float(st.get(self.power_entity))
    if self.power_sign == "positiv_entladen":
        p = -p
    self._lade_ist_w    = max( p, 0.0)
    self._entlade_ist_w = max(-p, 0.0)
```

### D‑B13 · Sicherer Zustand ist `standby`, nicht „aus lassen"

Ohne WR‑Eigenverbrauchsmodus gibt es kein Auffangnetz. Details und vollständige
Matrix in [Abschnitt 12](#12-sicherheit-fehlerfälle-watchdog).

### D‑B14 · Fremdgesteuerte HEMS‑Lasten deckt der Speicher **nicht**

> **Entschieden durch F‑5: nein.** Das Konfigfeld
> `entladung_deckt_fremdgesteuerte_lasten` aus v3 **entfällt ersatzlos** –
> es hätte nur eine Variante konfigurierbar gemacht, die niemand will.

`hems_last_w` zählt nur **HEMS‑angeforderte** Last (Force‑Modus‑Regel,
[devices.py:295-305](app/ems/devices.py#L295-L305)). Ein von Hand
eingeschalteter Heizstab liefert `current_w = 0` und landete damit im
Hausverbrauch – der Speicher würde ihn decken. Ein von Hand eingeschalteter
Heizstab ist aber immer noch ein Überschussverbraucher.

Deshalb bekommt die Entladeseite eine **eigene Summe** über eine neue
Default‑Property (4.2, 7.1):

```python
hems_last_gemessen_w = sum(d.gemessene_last_w for d in self._devices)
entlade_basis_w      = residual_bereinigt_w + hems_last_gemessen_w
hausdefizit_w        = max(-entlade_basis_w, 0.0)
```

| Klasse | `gemessene_last_w` |
|---|---|
| `Device` (Default) | `0.0` |
| `ControllableDevice` | `self._actual_w` (kein `eligible`‑Gate, kein Force‑Filter) |
| `BinaryDevice` | `self.power_w if self._actual_on else 0.0` |
| `BatteryDevice` | `self._lade_ist_w` (Ladeleistung, auch bei Netzladen) |

**Kein `eligible`‑Gate** – anders als bei `current_w`. Ein Gerät, das gerade
nicht freigegeben ist, aber trotzdem Leistung zieht, ist erst recht ein Fall
für „das deckt der Speicher nicht". Dieselbe Begründung wie bei
`netz_support_w` (4.5): sobald es den Netzpunkt verfälscht, zählt der
Messwert, nicht die Absicht.

Der Preis dieser Entscheidung, offen benannt: Läuft der Heizstab von Hand,
sinkt `hausdefizit_w` und der Restbezug erscheint am Netz statt aus dem
Speicher. Das ist gewollt – aber es sieht im Energiedashboard aus wie ein
Regelfehler. Gehört in die README.

### D‑B15 · Entlade‑Koordination im Controller, nicht im Gerät

Wegen H‑3: `EMSController._allocate_discharge(...)` teilt `hausdefizit_w`
**einmal** über alle entladebereiten Speicher auf und setzt je Gerät
`set_discharge_target(w)`. Das Gerät rechnet nicht selbst.

Die Reihenfolge liefert `_discharge_order()` und sortiert seit F‑3/F‑6
ausschließlich nach `entlade_prioritat` (D‑B17), Gleichstand → Config‑
Reihenfolge über die stabile Sortierung. Keine Strategien, keine Heuristik
(D‑B18).

### D‑B17 · Getrennte Lade‑ und Entladepriorität

**Entschieden durch F‑3.** Ein Speicher hat zwei Rollen, die nichts
miteinander zu tun haben:

| Rolle | Größe | Konkurriert mit |
|---|---|---|
| Laden | `prioritat` (bestehender Helfer, alle Gerätetypen) | Heizstab, Wallbox, Heizlüfter, andere Speicher |
| Entladen | **`entlade_prioritat`** (neu, nur Speicher) | ausschließlich anderen Speichern |

Eine gemeinsame Zahl wäre nicht nur unbequem, sondern schlicht
unterbestimmt: „lade mich zuletzt, entlade mich zuerst" ist eine sinnvolle
und mit einer Größe nicht ausdrückbare Konfiguration (kleiner Pufferspeicher
neben einem großen Hausspeicher).

```python
# _discharge_order - stabile Sortierung, Config-Reihenfolge bricht Gleichstand
return sorted(kandidaten, key=lambda b: b.entlade_priority)
```

* Helfer `input_number.ems_<p>_entlade_prioritat`, Default **50**, gleiche
  Semantik wie `prioritat`: **kleiner = wichtiger**.
* EP‑Vorschlag `sensor.ep_<p>_entlade_prio_vorschlag` mit der üblichen
  Fallback‑Semantik (Abschnitt 13).
* Nur `BatteryDevice` kennt das Feld – `Device` bleibt unangetastet.

**Nebenwirkung, die man kennen muss:** Lade‑ und Entladereihenfolge dürfen
sich widersprechen. Wird Speicher A zuerst geladen und B zuerst entladen,
bleibt A dauerhaft voll und B zykelt allein. Das ist eine legitime Absicht
(Reserve vs. Arbeitsspeicher), aber es ist keine Fehlkonfiguration, die das
HEMS erkennen kann – höchstens ein Hinweis in der UI.

### D‑B18 · Keine Entladestrategien – strikt nach Priorität

**Entschieden durch F‑6.** `speicher_entlade_strategie` (`prioritaet` |
`soc_ausgleich` | `proportional` | `kapazitaet`) **entfällt ersatzlos**,
ebenso `_discharge_order` als Strategie‑Schalter und der
`proportional`‑Zweig in `_allocate_discharge`.

Es bleibt: **Serienbedienung nach `entlade_prioritat`.** Der erste Speicher
liefert bis `entlade_kapazitaet_w()`, der Rest geht an den nächsten.

*Was das kostet:* Der erstplatzierte Speicher zykelt deutlich stärker und
SoC‑Stände laufen auseinander. Das ist bewusst in Kauf genommen – der
Ausgleich ist über `entlade_prioritat` von Hand oder später über einen
EP‑Vorschlag herstellbar, ohne dass das HEMS eine eigene Bewertung braucht.

*Was das spart:* die Mindestleistungs‑Umverteilung aus v3 (10.2), einen
Config‑Wert, einen Testfall und eine ganze Klasse von „warum entlädt der
falsche Speicher"‑Fragen. `capacity_kwh` bleibt in der Add‑on‑Config
erhalten – für Anzeige, `energie_kwh` und eine spätere EP‑Integration
(F‑6 ausdrücklich).

### D‑B16 · Vorrangregel Netzladen vor Entladen

Sobald Netzladen existiert (v2), gilt zwingend:

> Ist `netzladen_aktiv` für einen Speicher gesetzt, ist **jede** Entladung
> dieses Speichers gesperrt – auch bei `hausdefizit_w > 0`.

Ohne diese Regel entsteht ein Kreisstrom: Netz → Speicher (Laden) → Haus
(Entladen) → mit Round‑Trip‑Verlust bezahlt. Bei n Speichern gilt die Regel
pro Gerät; ein Speicher darf laden, während ein anderer entlädt, wenn der
Nutzer das explizit so konfiguriert – aber eine Warnung ins Log gehört dazu.

---

## 7. Neue Klasse `BatteryDevice`

Datei: [app/ems/devices.py](app/ems/devices.py), unterhalb von `BinaryDevice`.

### 7.1 Ergänzungen an `Device`

Zwei neue Properties. Die erste hat Default 0.0, die zweite muss in beiden
Bestandsklassen überschrieben werden – in beiden Fällen mit einem Wert, den
die Klasse ohnehin schon führt, also ohne neue Zustandshaltung:

```python
class Device(ABC):
    ...
    @property
    def gemessene_last_w(self) -> float:
        """Gemessene Leistungsaufnahme, OHNE Force-Modus-Filter.

        Basis der Entladeplanung (D-B14/F-5): Was hier zurückaddiert wird,
        gilt NICHT als Hausverbrauch und wird vom Speicher nicht gedeckt.
        Anders als current_w ohne eligible-Gate und ohne Deckelung auf die
        HEMS-Anforderung - sobald eine Last den Netzpunkt verfaelscht, zaehlt
        sie hier, unabhaengig davon wer sie eingeschaltet hat.
        """
        return 0.0

# ControllableDevice
    @property
    def gemessene_last_w(self) -> float:
        return self._actual_w

# BinaryDevice
    @property
    def gemessene_last_w(self) -> float:
        return self.power_w if self._actual_on else 0.0
```

```python
class Device(ABC):
    ...
    @property
    def netz_support_w(self) -> float:
        """Leistung, die dieses Gerät AKTIV ins Hausnetz einspeist.

        Erhöht residual_w, ist aber kein PV-Überschuss und muss daher aus Pool-
        und Defizitrechnung herausgerechnet werden. Anders als current_w wird
        hier IMMER der Messwert verwendet - auch Entladung, die das HEMS nicht
        selbst angefordert hat (Sollwert-Nachlauf, WR-Feinregelung im
        Hüllen-Modus), verfälscht den Pool.
        Für alle reinen Verbraucher: 0.0.
        """
        return 0.0
```

### 7.2 Gerüst

```python
class BatteryDevice(ControllableDevice):
    """AC-gekoppelter Batteriespeicher, vollständig vom HEMS gesteuert.

    Der Speicher regelt NICHT selbst auf Netzpunkt +-0 - das macht das HEMS.

    Ladepfad:   geerbter ControllableDevice-Pfad (Pool-Allokation, Rampe, Deadband).
    Entladepfad: Ziel vom Controller zugeteilt (_allocate_discharge), hier nur
                 begrenzt, asymmetrisch gerampt und geschrieben.

    Invariante: new_lade_w == 0 or new_entlade_w == 0.
    """

    def __init__(self, id, allowed_modes, *,
                 soc_entity: str,
                 charge_power_entity: Optional[str] = None,
                 discharge_power_entity: Optional[str] = None,
                 power_entity: Optional[str] = None,
                 power_sign: str = "positiv_laden",
                 available_charge_power_entity: Optional[str] = None,
                 available_discharge_power_entity: Optional[str] = None,
                 capacity_kwh: float = 0.0,
                 shelly_fallback: bool = False,
                 entity_prefix=None, label=None):
        prefix = entity_prefix or id
        super().__init__(
            id, allowed_modes,
            entity_actual_w=charge_power_entity or power_entity or "",
            entity_anforderung_w=f"input_number.ems_{prefix}_anforderung_ladeleistung_w",
            entity_prefix=prefix, label=label,
            output_unit="watt",              # Speicher immer in Watt
        )
        ...

    # ---- Konfigparameter (je Zyklus aus HA) ----
    #   max_ladeleistung_w, min_ladeleistung_w
    #   max_entladeleistung_w, min_entladeleistung_w
    #   soc_min_prozent, soc_max_prozent, soc_reserve_prozent
    #   soc_taper_band_prozent, soc_max_hysterese_prozent
    #   entlade_abschlag_w, entlade_sofort_schwelle_w
    #   umschalt_totzone_w, min_umschaltzeit_s
    #   laden_erlaubt, entladen_erlaubt
    #   entlade_priority                          (D-B17, Default 50)
    #   betriebsart
    #   netzladen_aktiv, netzlade_leistung_w      (v2, in v1 immer aus)

    # ---- Laufzeitzustand ----
    #   _soc, _lade_ist_w, _entlade_ist_w
    #   _lade_anf_w, _entlade_anf_w                (aus HA zurückgelesen)
    #   _lade_age_s, _entlade_age_s
    #   _entlade_ziel_w                            (vom Controller gesetzt)
    #   _last_direction_change_ts                  (überlebt Zyklen)
    #   _new_lade_w, _new_entlade_w, _new_betriebsart
    #   _blockiert_grund
```

### 7.3 Pool‑Semantik

```python
@property
def current_w(self) -> float:
    """Nur HEMS-angeforderte LADEleistung aus PV-Überschuss.

    Bei Netzladen (v2) bewusst 0: diese Leistung stammt nicht aus dem
    PV-Überschuss und darf nicht in den Pool zurückgerechnet werden - sonst
    würden die Überschussverbraucher aus dem Netz mitgespeist.
    """
    if not self.eligible or self.netzladen_aktiv:
        return 0.0
    return min(self._lade_ist_w, self._lade_anf_w)

@property
def gemessene_last_w(self) -> float:
    """Gemessene LADEleistung - auch bei Netzladen, anders als current_w.

    Verhindert, dass ein Speicher, der aus dem Netz laedt, fuer einen ANDEREN
    Speicher wie Hausverbrauch aussieht (Kreisstrom ueber zwei Geraete).
    D-B16 sperrt nur die Entladung desselben Speichers.
    """
    return self._lade_ist_w

@property
def netz_support_w(self) -> float:
    """Gemessene Entladung - immer, unabhängig von eligible/source (4.5)."""
    return self._entlade_ist_w

@property
def max_relief_w(self) -> float:
    """Sofort abschaltbare Ladeleistung.

    Anders als bei einem Heizstab ist min_technisch_w hier KEINE Untergrenze
    fürs Abschalten - der Speicher kann von jedem Ladewert unverzüglich auf 0.
    """
    return self.current_w

def select_phases(self, pool_w, now_ts) -> None:
    return                                   # Speicher immer Watt-geregelt
```

### 7.4 Ladeseite – geerbte Allokation nur begrenzen

```python
def _darf_laden(self) -> bool:
    if not self.eligible:                       self._blockiert("nicht_freigegeben"); return False
    if self.betriebsart not in ("auto", "nur_laden"): self._blockiert("betriebsart"); return False
    if not self.laden_erlaubt:                  self._blockiert("laden_gesperrt");   return False
    if self._lade_limit_w() <= 0:               self._blockiert("soc_max");          return False
    return True

def allocate_minimum(self, remaining_w: float) -> float:
    if not self._darf_laden():
        self._alloc_w = 0.0
        return remaining_w
    return super().allocate_minimum(remaining_w)

def allocate_surplus(self, remaining_w: float) -> float:
    return super().allocate_surplus(remaining_w) if self._darf_laden() else remaining_w
```

`min_technisch_w` / `max_technisch_w` der Basisklasse werden in
`update_from_ha` aus `min_ladeleistung_w` bzw. `_lade_limit_w()` befüllt.
Dadurch greift die komplette geerbte 2‑Pass‑Allokation unverändert und der
SoC‑Taper wirkt automatisch als Cap.

### 7.5 Entladeseite

```python
def entlade_kapazitaet_w(self) -> float:
    """Wie viel dieser Speicher JETZT beisteuern könnte (für die Aufteilung, H-3)."""
    if not self.eligible or not self.entladen_erlaubt:            return 0.0
    if self.betriebsart not in ("auto", "nur_entladen"):          return 0.0
    if self.netzladen_aktiv:                                      return 0.0   # D-B16
    return self._entlade_limit_w()

def set_discharge_target(self, w: float) -> None:
    """Vom EMSController._allocate_discharge aufgerufen."""
    self._entlade_ziel_w = max(0.0, min(w, self.entlade_kapazitaet_w()))
```

### 7.6 Richtungsauflösung und asymmetrische Rampe

```python
def calculate_ramp(self, current_deficit_w: float = 0.0) -> None:
    """Löst die Richtung auf, wendet Totzone/Umschaltsperre an, rampt asymmetrisch.

    Wird vom Controller für ALLE Geräte aufgerufen (controller.py:231) - die
    Entladeplanung muss also vorher gelaufen sein (D-B07).
    """
    if not self.eligible or self.betriebsart in ("standby", "inverter"):
        self._new_lade_w = self._new_entlade_w = 0.0
        self._new_betriebsart = self._sicherer_zustand()
        return

    lade_wunsch    = self._alloc_w        if self._darf_laden()   else 0.0
    entlade_wunsch = self._entlade_ziel_w

    # D-B10: bei Hausdefizit niemals aus PV-Logik heraus laden
    if entlade_wunsch > 0 and not self.netzladen_aktiv:
        lade_wunsch = 0.0
    # D-B16: Netzladen schlägt Entladen
    if self.netzladen_aktiv:
        entlade_wunsch = 0.0
        lade_wunsch    = self.netzlade_leistung_w

    netto = lade_wunsch - entlade_wunsch                 # + laden / - entladen

    # Totzone -> Standby, verhindert Mikrozyklen
    if abs(netto) < self.umschalt_totzone_w:
        netto = 0.0

    # Umschaltsperre: Richtungswechsel erst nach min_umschaltzeit_s.
    # In der Sperrzeit wird STANDBY gefahren, nicht die alte Richtung
    # fortgesetzt - sonst entlädt der Speicher in den PV-Überschuss hinein.
    richtung_neu = 0 if netto == 0 else (1 if netto > 0 else -1)
    richtung_alt = self._aktuelle_richtung()
    if (richtung_neu and richtung_alt and richtung_neu != richtung_alt
            and self._now_ts - self._last_direction_change_ts < self.min_umschaltzeit_s):
        self._blockiert("umschaltsperre")
        netto, richtung_neu = 0.0, 0
    if richtung_neu and richtung_neu != richtung_alt:
        self._last_direction_change_ts = self._now_ts

    if netto > 0:                                        # LADEN - symmetrisch gerampt
        self._new_lade_w    = self._ramp_symmetrisch(netto, self._lade_anf_w, self._lade_age_s)
        self._new_entlade_w = 0.0
        self._new_betriebsart = "laden"
    elif netto < 0:                                      # ENTLADEN - asymmetrisch (5.2)
        self._new_lade_w    = 0.0
        self._new_entlade_w = self._ramp_entladen(-netto)
        self._new_betriebsart = "entladen"
    else:
        self._new_lade_w = self._new_entlade_w = 0.0
        self._new_betriebsart = "standby"

    self._new_lade_w    = self._raste(self._new_lade_w,    self.min_ladeleistung_w)
    self._new_entlade_w = self._raste(self._new_entlade_w, self.min_entladeleistung_w)


def _ramp_entladen(self, ziel_w: float) -> float:
    """RUNTER sofort, HOCH gerampt - Batterieexport ist teurer als Restbezug (H-5)."""
    if ziel_w < self._entlade_anf_w:
        return ziel_w                                    # sofort, ungerampt
    if self._entlade_age_s < self.hoch_regelzeit_s:
        return self._entlade_anf_w
    return min(ziel_w, self._entlade_anf_w + self.max_anderung_pro_schritt_w)
```

### 7.7 Ausgabe

```python
def get_write_ops(self):
    ops = []
    ab = f"input_select.ems_{self._entity_prefix}_anforderung_betriebsart"
    lw = f"input_number.ems_{self._entity_prefix}_anforderung_ladeleistung_w"
    ew = f"input_number.ems_{self._entity_prefix}_anforderung_entladeleistung_w"

    schaltet_ab = self._new_betriebsart in ("standby", "inverter")

    if schaltet_ab:
        # Beim Abschalten: erst Leistung auf 0, dann Modus (D-B11)
        ops += self._write(lw, 0.0, self._lade_anf_w,    deadband=True)
        ops += self._write(ew, 0.0, self._entlade_anf_w, deadband=False)
        ops += self._write_select(ab, self._new_betriebsart)
    else:
        # Beim Einschalten/Ändern: erst Modus, dann Leistung
        ops += self._write_select(ab, self._new_betriebsart)
        ops += self._write(lw, self._new_lade_w, self._lade_anf_w, deadband=True)
        # Deadband beim SENKEN der Entladung bewusst aus (D-B08)
        ops += self._write(ew, self._new_entlade_w, self._entlade_anf_w,
                           deadband=self._new_entlade_w >= self._entlade_anf_w)
    return ops
```

### 7.8 `to_status_dict()`

```python
{
  "type": "battery",
  "id": ..., "label": ..., "priority": ..., "eligible": ..., "source": ...,
  "entlade_prioritat":      30,            # D-B17, unabhängig von priority
  "soc_prozent":            72.5,
  "capacity_kwh":           10.0,
  "energie_kwh":            7.25,          # nur wenn capacity_kwh > 0
  "betriebsart":            "auto",        # gewünscht (Nutzer/EP)
  "betriebsart_effektiv":   "entladen",    # was HEMS diesen Zyklus schreibt
  "shelly_fallback":        false,         # ist dieser Speicher der Watchdog-Master?
  "lade_ist_w":             0,
  "entlade_ist_w":          1840,
  "lade_anforderung_w":     0,
  "entlade_anforderung_w":  1800,
  "new_lade_w":             0,
  "new_entlade_w":          1900,
  "netto_w":               -1900,          # + laden / - entladen
  "lade_limit_w":           5000,          # nach SoC-Taper + WR-Derating
  "entlade_limit_w":        5000,
  "hausdefizit_anteil_w":   1900,          # was diesem Speicher zugeteilt wurde
  "schutz_w":               ...,           # geerbt
  "laden_erlaubt":          true,
  "entladen_erlaubt":       true,
  "netzladen_aktiv":        false,
  "soc_min_prozent":        10,
  "soc_max_prozent":        100,
  "umschaltsperre_rest_s":  0,
  "blockiert_grund":        null           # siehe unten
}
```

`blockiert_grund` ∈ `null | "nicht_freigegeben" | "betriebsart" |
"laden_gesperrt" | "entladen_gesperrt" | "soc_min" | "soc_max" |
"soc_reserve" | "umschaltsperre" | "totzone" | "wr_derating" | "netzladen"`

Ohne dieses Feld ist „warum lädt/entlädt der Speicher gerade nicht?" nur über
Debug‑Logs beantwortbar. Bei einem Regler mit sechs Sperrmechanismen ist das
im Feld praktisch unbrauchbar.

---

## 8. Entitäten und Konfiguration

### 8.1 Add‑on‑Konfiguration (`config.yaml`)

```yaml
options:
  speicher_in_residual_enthalten: true        # D-B03, durch F-10 bestaetigt
schema:
  speicher_in_residual_enthalten: bool?
```

> `speicher_entlade_strategie` aus v3 ist durch F‑6 entfallen (D‑B18) –
> es gibt nur noch die Reihenfolge nach `entlade_prioritat`.

Geräteklasse erweitern – [config.yaml:76](config.yaml#L76):

```yaml
class: list(controllable|binary|battery)
```

Neue optionale Gerätefelder (alle `?`, bestehende Configs bleiben valide):

```yaml
      soc_entity: str?
      charge_power_entity: str?
      discharge_power_entity: str?
      power_entity: str?
      power_sign: list(positiv_laden|positiv_entladen)?
      available_charge_power_entity: str?
      available_discharge_power_entity: str?
      capacity_kwh: float?
      shelly_fallback: bool?
      steuerprofil: list(zwei_entitaeten|signiert|modus_und_leistung)?
```

> `capacity_kwh` bleibt bewusst in der **Add‑on‑Config**, nicht als HA‑Helfer
> (F‑6): der Wert ist Hardware, ändert sich nie im Betrieb, und eine spätere
> Energy‑Pilot‑Integration soll ihn aus der Config lesen können, ohne einen
> Helfer‑Roundtrip.
>
> `entladung_deckt_fremdgesteuerte_lasten` aus v3 ist durch F‑5 entfallen
> (D‑B14) – das Verhalten ist jetzt fest verdrahtet.
>
> `steuerprofil` bleibt reserviert, solange **F‑2** offen ist. v1 baut nur
> `zwei_entitaeten`.

Beispiel:

```yaml
    - name: speicher_1
      label: "Hausspeicher"
      class: battery
      entity_prefix: speicher1
      allowed_modes: "manuell,nur_heizen,nur_laden"
      soc_entity: sensor.speicher_1_soc
      charge_power_entity: sensor.speicher_1_ladeleistung
      discharge_power_entity: sensor.speicher_1_entladeleistung
      capacity_kwh: 10.0
      shelly_fallback: true          # höchstens EIN Speicher darf true sein (D-B05)
```

> **`allowed_modes`:** In [controller.py:56-57](app/ems/controller.py#L56-L57)
> wird `auto` aus Rückwärtskompatibilität auf `manuell` gemappt. Für einen
> Speicher, der in allen Betriebsmodi mitlaufen soll, alle Nicht‑`aus`‑Modi
> auflisten: `"manuell,nur_heizen,nur_laden"`.

### 8.2 Gemeinsame Helfer (existieren für jedes Gerät)

`input_boolean.ems_<p>_freigabe`, `…_technische_freigabe`,
`input_select.ems_<p>_modus`, `input_number.ems_<p>_prioritat`

### 8.3 Speicherspezifische Helfer – Eingang

| `input_number.ems_<p>_…` | Einheit | Default | Funktion |
|---|---|---|---|
| **`entlade_prioritat`** | – | **50** | **Reihenfolge beim Entladen (D‑B17), klein = zuerst. Unabhängig von `prioritat`** |
| `max_ladeleistung_w` | W | – | Obergrenze Laden |
| `min_ladeleistung_w` | W | 0 | WR‑Untergrenze; darunter → 0 |
| `max_entladeleistung_w` | W | – | Obergrenze Entladen |
| `min_entladeleistung_w` | W | 0 | WR‑Untergrenze Entladen |
| `soc_min_prozent` | % | 10 | Entladeschluss (Tiefentladeschutz) |
| `soc_max_prozent` | % | 100 | Ladeschluss |
| `soc_reserve_prozent` | % | 0 | Notstromreserve; darunter keine HEMS‑Entladung |
| `soc_taper_band_prozent` | % | 5 | Drosselband vor der Grenze (D‑B09) |
| `soc_max_hysterese_prozent` | % | 2 | Wiedereinstiegsschwelle unter `soc_max` |
| **`entlade_abschlag_w`** | W | **20** | bewusster Unterschuss (H‑5/5.4) – bei 3 s klein halten |
| **`entlade_sofort_schwelle_w`** | W | **300** | ab dieser Absenkung ungerampt (5.3); **> Sensor‑Versatzfehler** |
| `umschalt_totzone_w` | W | 100 | Totzone um 0 → Standby |
| `min_umschaltzeit_s` | s | 300 | Sperrzeit nach Richtungswechsel |
| **`hoch_regelzeit_s`** | s | **≥ Sensor‑Versatz** | Mindestabstand Hoch‑Regelschritte – **Stabilitätsparameter gegen H‑7**, nicht nur Komfort |
| `runter_regelzeit_s` | s | geerbt | nur Ladepfad |
| `max_anderung_pro_schritt_w` | W | geerbt | Rampe |
| `min_anderung_pro_schritt_w` | W | geerbt | Deadband (D‑B08) |
| `geschutzte_mindestleistung_w` | W | geerbt | reservierte Ladeleistung ggü. binären Geräten |
| `reserve_w` | W | geerbt | Teil von `schutz_w` |
| `netzlade_leistung_w` | W | 0 | **v2**, Abschnitt 11 |
| `netzlade_soc_ziel_prozent` | % | 0 | **v2** |

| Entität | Domain | Funktion |
|---|---|---|
| `input_boolean.ems_<p>_laden_erlaubt` | boolean | Ladepfad freigeben |
| `input_boolean.ems_<p>_entladen_erlaubt` | boolean | Entladepfad freigeben |
| `input_boolean.ems_<p>_netzladen_aktiv` | boolean | **v2**, Abschnitt 11 |
| `input_select.ems_<p>_betriebsart` | select | `auto`/`nur_laden`/`nur_entladen`/`standby`/`inverter` |

### 8.4 Helfer – Ausgang (vom HEMS geschrieben)

| Entität | Domain | Funktion |
|---|---|---|
| `input_number.ems_<p>_anforderung_ladeleistung_w` | number | Sollwert Laden |
| `input_number.ems_<p>_anforderung_entladeleistung_w` | number | Sollwert Entladen |
| `input_select.ems_<p>_anforderung_betriebsart` | select | `laden`/`entladen`/`standby`/`inverter` |

### 8.5 Externe Sensoren

| Config‑Feld | Einheit | Pflicht | Funktion |
|---|---|---|---|
| `soc_entity` | % | ja | Ladezustand |
| `charge_power_entity` | W ≥ 0 | Variante A | Ist‑Ladeleistung |
| `discharge_power_entity` | W ≥ 0 | Variante A | Ist‑Entladeleistung |
| `power_entity` + `power_sign` | W signiert | Variante B | eine Entität für beides |
| `available_charge_power_entity` | W | nein | momentanes WR‑Ladelimit |
| `available_discharge_power_entity` | W | nein | momentanes WR‑Entladelimit |

### 8.6 Vollständige Liste für `entity_prefix: speicher1`

```
# Eingang
input_boolean.ems_speicher1_freigabe
input_boolean.ems_speicher1_technische_freigabe
input_boolean.ems_speicher1_laden_erlaubt
input_boolean.ems_speicher1_entladen_erlaubt
input_boolean.ems_speicher1_netzladen_aktiv              # v2
input_select.ems_speicher1_modus                         # auto|manuell|aus
input_select.ems_speicher1_betriebsart                   # auto|nur_laden|nur_entladen|standby|inverter
input_number.ems_speicher1_prioritat                      # Laden
input_number.ems_speicher1_entlade_prioritat             # Entladen (D-B17)
input_number.ems_speicher1_max_ladeleistung_w
input_number.ems_speicher1_min_ladeleistung_w
input_number.ems_speicher1_max_entladeleistung_w
input_number.ems_speicher1_min_entladeleistung_w
input_number.ems_speicher1_soc_min_prozent
input_number.ems_speicher1_soc_max_prozent
input_number.ems_speicher1_soc_reserve_prozent
input_number.ems_speicher1_soc_taper_band_prozent
input_number.ems_speicher1_soc_max_hysterese_prozent
input_number.ems_speicher1_entlade_abschlag_w
input_number.ems_speicher1_entlade_sofort_schwelle_w
input_number.ems_speicher1_umschalt_totzone_w
input_number.ems_speicher1_min_umschaltzeit_s
input_number.ems_speicher1_hoch_regelzeit_s
input_number.ems_speicher1_runter_regelzeit_s
input_number.ems_speicher1_max_anderung_pro_schritt_w
input_number.ems_speicher1_min_anderung_pro_schritt_w
input_number.ems_speicher1_geschutzte_mindestleistung_w
input_number.ems_speicher1_reserve_w
input_number.ems_speicher1_netzlade_leistung_w           # v2
input_number.ems_speicher1_netzlade_soc_ziel_prozent     # v2

# Ausgang (HEMS schreibt)
input_number.ems_speicher1_anforderung_ladeleistung_w
input_number.ems_speicher1_anforderung_entladeleistung_w
input_select.ems_speicher1_anforderung_betriebsart

# Extern (HEMS liest)
sensor.speicher_1_soc
sensor.speicher_1_ladeleistung
sensor.speicher_1_entladeleistung
```

**~34 Helfer pro Speicher.** Bei n Speichern identisch je Prefix.

> **Zwingend für die Praxis:** Ein HA‑Package als Vorlage beilegen
> (`packages/hems_speicher.yaml`), je Speicher kopieren und Prefix ersetzen.
> 33 Helfer von Hand anzulegen ist bei 3 Speichern ~100 Klickstrecken und
> praktisch garantiert fehlerhaft. Ein Skript, das die Package‑YAML aus der
> Add‑on‑Config generiert, wäre eine lohnende kleine Beigabe.

---

## 9. Änderungen am Regelzyklus

`EMSController.run_cycle()` – [controller.py:135](app/ems/controller.py#L135):

```
 1. Globale Eingänge lesen                                       unverändert
    + speicher_in_residual_enthalten                             NEU
    + ems_speicher_entlade_abschlag_w (global, 10.3)             NEU

 2. Geräte aus HA aktualisieren                                  unverändert
    (Speicher liest SoC, Ist-Leistungen, Betriebsart, Regelmodus)

 3. NEU  Netz-Bereinigung
         netz_support_w       = Σ d.netz_support_w
         residual_bereinigt_w = residual_w - netz_support_w
                                if speicher_in_residual_enthalten else residual_w

 4. GEÄNDERT  Pool + Hausdefizit  (zwei Summen, siehe 4.2/D-B14)
         hems_last_w          = Σ d.current_w           (Force gefiltert)
         hems_last_gemessen_w = Σ d.gemessene_last_w    (Messwert, F-5)
         pool_roh_w      = residual_bereinigt_w + hems_last_w
         entlade_basis_w = residual_bereinigt_w + hems_last_gemessen_w
         pool_w        = max( pool_roh_w,      0)  falls nicht lockout/aus, sonst 0
         hausdefizit_w = max(-entlade_basis_w, 0)  falls nicht lockout/aus, sonst 0

 5. GEÄNDERT  Defizit der Verbraucher
         current_deficit_w    = max(-residual_bereinigt_w, 0)
         total_relief_w       = Σ d.max_relief_w
         binary_immediate_off = current_deficit_w > total_relief_w

 6. Binärer Wunschzustand (consume_from_pool, Prio-Reihenfolge)  unverändert
 7. Binärer Kandidat / Kaskade / One-Change                      unverändert
 8. Regelbare Geräte: 2-Pass-Allokation                          unverändert
                                                                  (Speicher ist
                                                                   ControllableDevice
                                                                   -> automatisch dabei)

 9. NEU  Entladeplanung
         _allocate_discharge(batteries, hausdefizit_w, now_ts)
         -> je Speicher set_discharge_target(w)
         MUSS nach Schritt 8 und vor Schritt 10 laufen (D-B07)

10. Rampenbegrenzung  for d: d.calculate_ramp(current_deficit_w) unverändert
                                                                  (Speicher löst hier
                                                                   die Richtung auf)
11. Debug-Logging  + Speicherzeile                               ERWEITERT
12. Write-Ops sammeln                                            unverändert
13. Status-Snapshot  + pool_roh_w, hausdefizit_w, netz_support_w ERWEITERT
```

### Konkret

```python
# --- Schritt 3-5, ersetzt controller.py:179-184 ---
netz_support_w = sum(d.netz_support_w for d in self._devices)
residual_bereinigt_w = (residual_w - netz_support_w
                        if self._speicher_in_residual else residual_w)

hems_last_w          = sum(d.current_w        for d in self._devices)
hems_last_gemessen_w = sum(d.gemessene_last_w for d in self._devices)

pool_roh_w      = residual_bereinigt_w + hems_last_w
entlade_basis_w = residual_bereinigt_w + hems_last_gemessen_w

if not ems_enabled or global_mode == "aus" or hard_lockout:
    pool_w = hausdefizit_w = 0.0
else:
    pool_w        = max( pool_roh_w,      0.0)
    hausdefizit_w = max(-entlade_basis_w, 0.0)   # F-5: Force-Lasten draussen

current_deficit_w    = max(-residual_bereinigt_w, 0.0)
total_relief_w       = sum(d.max_relief_w for d in self._devices)
binary_immediate_off = current_deficit_w > total_relief_w
```

`_calc_pool()` wird durch die zwei Zeilen ersetzt bzw. auf
`_calc_pool_roh()` umgebaut – die Klemme wandert nach außen, weil beide
Hälften gebraucht werden.

**Hard‑Lockout weiterhin gegen den ROHwert** prüfen
([controller.py:160-161](app/ems/controller.py#L160-L161)): der Lockout ist eine
Sensor‑Plausibilitätsprüfung, keine Regelgröße. Bereinigung würde einen
defekten Sensor kaschieren.

```python
def _allocate_discharge(self, batteries, hausdefizit_w, now_ts) -> None:
    """Verteilt den Hausverbrauchs-Fehlbetrag auf die entladebereiten Speicher.

    hausdefizit_w enthält per Konstruktion KEINE HEMS-Geraete-Last, auch keine
    fremdgesteuerte (Abschnitt 4.2, D-B14) - die Abgrenzung 'nicht fuer
    Ueberschussverbraucher' ist damit bereits erledigt und braucht hier keine
    Sonderbehandlung.

    Reihenfolge strikt nach entlade_prioritat (D-B17/D-B18), keine Strategien.
    """
    for b in batteries:
        b.set_discharge_target(0.0)

    if hausdefizit_w <= 0:
        return

    kandidaten = [b for b in batteries if b.entlade_kapazitaet_w() > 0]
    if not kandidaten:
        if hausdefizit_w > 100:
            log.info("EMS Speicher: %.0fW Hausdefizit, kein Speicher entladebereit",
                     hausdefizit_w)
        return

    # Abschlag EINMAL systemweit, nicht je Speicher (10.3, F-4 gelöst)
    ziel_w = max(hausdefizit_w - self._entlade_abschlag_w, 0.0)
    if ziel_w <= 0:
        return

    rest_w = ziel_w
    for b in self._discharge_order(kandidaten):
        take = min(rest_w, b.entlade_kapazitaet_w())
        b.set_discharge_target(take)
        rest_w -= take
        if rest_w <= 0:
            break

    if rest_w > 100:
        log.info("EMS Speicher: %.0fW Hausdefizit ungedeckt (alle Speicher am Limit)",
                 rest_w)


def _discharge_order(self, kandidaten):
    """Strikt nach Entladeprioritaet (D-B17). sorted() ist stabil, damit
    entscheidet bei Gleichstand die Reihenfolge in der Add-on-Config."""
    return sorted(kandidaten, key=lambda b: b.entlade_priority)
```

Ein Speicher, dessen Zuteilung unter seiner `min_entladeleistung_w` liegt,
rastet in [7.6](#76-richtungsauflösung-und-asymmetrische-rampe) über `_raste`
auf 0 – er entlädt dann gar nicht, statt zu überschießen. Bei serieller
Zuteilung trifft das höchstens den **letzten** bedienten Speicher und
höchstens um dessen Mindestleistung; die v3‑Umverteilung aus dem
`proportional`‑Zweig wird dafür nicht gebraucht (D‑B18).

Der `entlade_abschlag_w` wird hier **einmal auf die Systemgröße** angewandt,
nicht je Speicher – bei n Speichern wäre er sonst n‑fach wirksam (10.3). Er
gehört damit als globaler Helfer `input_number.ems_speicher_entlade_abschlag_w`
in die Konfiguration, analog zu `ems_einschaltreserve_global_w`.

Die gerätelokalen Rampenparameter (`entlade_sofort_schwelle_w`,
`hoch_regelzeit_s`, `max_anderung_pro_schritt_w`) bleiben dagegen **pro
Speicher** – sie hängen an der Hardware, nicht am System.

---

## 10. Mehrspeicher‑Koordination (1…n)

### 10.1 Laden – keine neue Logik

n Speicher = n `ControllableDevice`‑Instanzen in der bestehenden
2‑Pass‑Allokation. Pass 1 garantiert jedem `min_ladeleistung_w`, Pass 2 füllt
in Prioritätsreihenfolge bis zum Limit.

Zwei Speicher mit gleicher `prioritat`: `sorted()` ist stabil → die
Config‑Reihenfolge entscheidet, der erste wird voll geladen bevor der zweite
anfängt.

> **F‑3/F‑6 beantwortet:** Das bleibt so – **seriell nach Priorität, kein
> SoC‑Ausgleich.** Wer parallel laden will, gibt beiden Speichern
> unterschiedliche `max_ladeleistung_w` oder nimmt die Ungleichverteilung in
> Kauf. Der dritte Allokationspass aus der v3‑Diskussion entfällt.

### 10.2 Entladen – strikt nach `entlade_prioritat`

Keine Strategien (D‑B18). `_discharge_order()` sortiert nach
`entlade_prioritat` aufsteigend, Gleichstand → Config‑Reihenfolge:

```
hausdefizit 2.500 W, Abschlag 20 W  ->  ziel 2.480 W

speicher_2  entlade_prioritat 10, Kapazitaet 2.000 W  ->  2.000 W
speicher_1  entlade_prioritat 20, Kapazitaet 5.000 W  ->    480 W
speicher_3  entlade_prioritat 30                      ->      0 W
```

`entlade_prioritat` ist **unabhängig** von `prioritat` (D‑B17): oben wird
`speicher_2` zuerst entladen, obwohl beim Laden eine ganz andere Reihenfolge
gelten kann.

| Wunsch | Konfiguration |
|---|---|
| ein Hauptspeicher trägt, der Rest ist Reserve | Hauptspeicher niedrigste `entlade_prioritat` |
| kleiner Speicher zuerst leer, großer bleibt voll | kleiner niedrig, großer hoch |
| Speicher soll nur laden, nie entladen | `entladen_erlaubt = off` (nicht über die Prio) |

**SoC spielt in der Reihenfolge keine Rolle** – nur in
`entlade_kapazitaet_w()`, das bei `soc_min`/`soc_reserve` auf 0 fällt. Ein
leerer Speicher wird damit automatisch übersprungen, ohne dass die Sortierung
davon weiß.

### 10.3 Fallstricke bei n Speichern

* **`entlade_abschlag_w` nicht n‑fach anwenden.** Der Abschlag ist eine
  Systemgröße. Er gehört **einmal** auf `hausdefizit_w`, nicht je Gerät. →
  Vorschlag: globale `input_number.ems_speicher_entlade_abschlag_w`, analog zu
  `ems_einschaltreserve_global_w`. → [Offene Frage F‑4](#18-offene-fragen-an-dich).
* **Ungleicher Verschleiß ist gewollt in Kauf genommen (F‑6/D‑B18).** Der
  erstplatzierte Speicher zykelt deutlich stärker. Gegenmittel ist
  ausschließlich `entlade_prioritat` – von Hand, saisonal oder später per
  EP‑Vorschlag. Echtes Zyklenmanagement bleibt EP‑Territorium.
* **Ein defekter Speicher darf die Flotte nicht blockieren.** `soc_entity`
  `unavailable` → dieser Speicher fällt auf den sicheren Zustand zurück und
  wird aus `kandidaten` entfernt; die anderen laufen weiter. Muster:
  `_build_devices` überspringt fehlerhafte Einträge einzeln
  ([controller.py:108-109](app/ems/controller.py#L108-L109)).
* **Summen‑Istwert vs. Einzelwerte – durch F‑8 entschieden.** HA stellt
  **keinen** Summensensor bereit; `netz_support_w` summiert ausschließlich die
  Einzelsensoren je Speicher. Damit ist der Fehlerfall „doppelte Bereinigung"
  konstruktiv ausgeschlossen. Sollte später doch ein Summensensor auftauchen:
  **nicht beide mischen** – sonst wird doppelt bereinigt (wieder H‑1, nur mit
  umgekehrtem Vorzeichen: der Pool wird zu klein und nichts läuft mehr).
* **Ein Messpunkt für alle (F‑10).** `residual_power_entity` ist die
  Netzübergabeleistung und gilt für die ganze Flotte. Es gibt keinen
  speicherlokalen Netzsensor, auf den man dezentral regeln könnte – D‑B05 ist
  damit nicht nur die bessere, sondern die einzige mögliche Architektur.

---

## 11. Netzladen mit dynamischen Tarifen (Vorbereitung)

Nicht in v1 implementiert, aber die Schnittstellen werden jetzt festgelegt,
damit v2 keine Migration braucht.

### 11.1 Aufgabenteilung

| Teil | Wer |
|---|---|
| Preisprognose, Zeitfenster, „lohnt sich Netzladen?" | **extern** – EP oder eine HA‑Automation mit Tibber/aWATTar‑Integration |
| Ausführung: Leistung setzen, SoC‑Ziel überwachen, Vorrangregeln, Sicherheit | **HEMS** |

Das HEMS bewertet keine Preise. Es bekommt eine Anweisung und führt sie sicher
aus. Das hält die Preislogik austauschbar und das HEMS frei von
Tarif‑Integrationen.

### 11.2 Schnittstelle

```
input_boolean.ems_<p>_netzladen_aktiv            # extern gesetzt: "jetzt aus dem Netz laden"
input_number.ems_<p>_netzlade_leistung_w         # mit welcher Leistung
input_number.ems_<p>_netzlade_soc_ziel_prozent   # bis zu welchem SoC
```

Zusätzlich als EP‑Vorschlag: `sensor.ep_<p>_netzladen_vorschlag`,
`sensor.ep_<p>_netzlade_leistung_vorschlag` – mit derselben Fallback‑Semantik
wie alle EP‑Felder ([Abschnitt 13](#13-energy-pilot-anbindung)).

### 11.3 Regeln, die beim Einbau zwingend gelten

1. **`current_w = 0` während Netzladen** (7.3). Netzgeladene Leistung darf
   nicht in den Pool zurückgerechnet werden – sonst würden die
   Überschussverbraucher aus dem Netz mitgespeist. Der subtilste und
   wichtigste Punkt.
   **Aber `gemessene_last_w` bleibt der volle Ladewert** (D‑B14) – sonst
   sieht Speicher B das Netzladen von Speicher A als Hauslast und deckt es.
2. **Netzladen sperrt Entladen** desselben Speichers (D‑B16), sonst
   Kreisstrom mit Round‑Trip‑Verlust. Gegen den Kreisstrom **über zwei
   Speicher** schützt Regel 1, nicht D‑B16.
3. **Netzladen umgeht die D‑B10‑Klemme** – das ist der einzige Fall, in dem
   bei `hausdefizit_w > 0` geladen wird. Die Klemme muss also auf
   `and not netzladen_aktiv` erweitert, nicht entfernt werden.
4. **`netzlade_soc_ziel_prozent` beendet den Vorgang**, unabhängig vom
   externen Schalter – Schutz gegen eine hängende Automation.
5. **Ein Zeitlimit** (`netzlade_max_dauer_min`) als zweite Sicherung. Ein
   klemmendes `netzladen_aktiv = on` lädt sonst dauerhaft aus dem Netz.
6. **PV‑Überschuss hat Vorrang vor Netzladen.** Ist `pool_roh_w > 0`, wird
   normal aus Überschuss geladen und `netzladen_aktiv` ignoriert – kostenlos
   schlägt billig.

---

## 12. Sicherheit, Fehlerfälle, Watchdog

### 12.1 Der sichere Zustand hängt vom Wechselrichter ab

Im Normalbetrieb regelt das HEMS, die Shelly‑Nulleinspeisung ist deaktiviert.
Fällt das HEMS aus, ist der beste Zustand **nicht** „alles auf 0" – dann zieht
das Haus voll aus dem Netz, obwohl der Speicher voll ist.

Stattdessen: **genau ein** Speicher (`shelly_fallback: true`) reaktiviert seine
Shelly‑Regelung, alle anderen gehen auf `standby`. Ein einzelner autonomer
Regler hat das Aufteilungsproblem aus D‑B05 nicht – deshalb trägt der Fallback,
obwohl er als Dauerlösung nicht funktioniert.

```python
def _sicherer_zustand(self) -> str:
    """Zustand bei EMS-Ausfall/Lockout/fehlender Freigabe.

    'inverter' = Shelly-Nulleinspeisung dieses Speichers wieder aktivieren.
    Nur beim designierten Fallback-Speicher - sonst regeln mehrere autonome
    Regler gegeneinander (D-B05, Einwand 1).
    """
    return "inverter" if self.shelly_fallback else "standby"
```

**Diese Regel ist der Grund, warum `shelly_fallback` bei höchstens einem
Speicher `true` sein darf.** `_build_devices` muss das erzwingen.

| Ereignis | Verbraucher | Speicher |
|---|---|---|
| `ems_pv_regelung_aktiv = off` | 0 W / aus | `_sicherer_zustand()` |
| `global_mode = aus` | 0 W / aus | `_sicherer_zustand()` |
| Hard‑Lockout (Sensor `unavailable` / ≤ −50 kW) | 0 W / aus | `_sicherer_zustand()` |
| `technische_freigabe = off` | 0 W / aus | `_sicherer_zustand()` |
| `input_select.ems_<p>_modus = aus` | 0 W / aus | `standby` (bewusste Stilllegung) |
| `soc_entity` unavailable | – | `_sicherer_zustand()` + Fehlerlog |
| Ist‑Leistungssensor unavailable | – | `_sicherer_zustand()` + Fehlerlog |

Der letzte Fall ist wichtig: **ohne Messwert ist `netz_support_w` unbekannt**,
und damit ist die Pool‑Bereinigung blind → H‑1‑Gefahr. Ein Speicher ohne
gültigen Leistungsmesswert muss aus der Regelung fallen.

> **Semantischer Unterschied zu `BinaryDevice`:** In allen diesen Fällen muss
> `get_write_ops()` **aktiv** den sicheren Zustand schreiben – nicht einfach
> nichts tun. „Nichts tun" lässt den letzten Sollwert stehen. Das gehört
> prominent in den Code kommentiert.

### 12.2 Watchdog – Pflicht, nicht Empfehlung

Stirbt das Add‑on, während `anforderung_entladeleistung_w = 4000` in HA steht,
entlädt der Speicher weiter bis leer. Ohne WR‑Eigenverbrauchsmodus gibt es
keinen Automatismus, der das auffängt.

**Drei Ebenen, mindestens zwei davon bauen:**

1. **Heartbeat aus dem HEMS.** Billigste Variante ohne Codeänderung: die
   vorhandene Option `post_cycle_script` auf ein HA‑Skript zeigen lassen, das
   `input_datetime.ems_letzter_zyklus` auf `now()` setzt.
2. **HA‑Automation als Totmann.** Trigger auf
   `input_datetime.ems_letzter_zyklus` älter als 3 × `interval_s`
   (`for: 00:02:00`) → alle `ems_*_anforderung_entladeleistung_w` auf 0,
   `…_anforderung_betriebsart` auf `standby` bzw. `inverter`.
3. **Shelly‑Nulleinspeisung als Rückfallebene** (D‑B05). Dieselbe Automation
   aktiviert beim Fallback‑Speicher die Shelly‑Regelung wieder. Das ist der
   qualitativ beste Fallback: das Haus bleibt gestützt, statt voll ins Netz
   zu fallen.
4. **WR‑seitiger Modbus‑Watchdog**, falls unterstützt (Register‑Timeout →
   Rückfall in Eigenverbrauch/Standby). **Die einzige Ebene, die auch einen
   HA‑Ausfall überlebt** – wenn der WR das kann, ist sie die wichtigste.

**Gegenprobe, die zum Testfall gehört:** Nach dem Fallback darf beim
Wiederanlaufen des HEMS die Shelly‑Regelung **nicht** aktiv bleiben – sonst
regeln HEMS und Shelly gegeneinander. Die Automation muss also beide
Richtungen schalten, und der HEMS‑Start muss den Zustand aktiv
zurücksetzen, nicht nur annehmen, dass er stimmt.

### 12.3 Weitere Absicherungen

| Risiko | Maßnahme |
|---|---|
| Netzladen durch Rechenfehler | Harte Klemme D‑B10 |
| Gleichzeitig laden + entladen | strukturell ausgeschlossen (4.4) + Property‑Test P1 |
| Tiefentladung | `soc_min_prozent`, `soc_reserve_prozent`, Taper (D‑B09) |
| Batterieexport | Asymmetrie + `entlade_abschlag_w` (5.2). **Kein harter Export‑Stopp nötig** – Einspeisevergütung vorhanden (F‑9) |
| Speicher deckt fremdgesteuerten Heizstab | `gemessene_last_w` (D‑B14/F‑5) |
| Kreisstrom Netz→Speicher A→Speicher B (v2) | Netzladeleistung steckt in `gemessene_last_w` (11.3 Regel 1) |
| Mikrozyklen / Verschleiß | `umschalt_totzone_w`, `min_umschaltzeit_s`, Deadband |
| Sollwert über WR‑Grenzen | `min(max_…_w, available_…_entity, soc_taper)` |
| Falsches `speicher_in_residual_enthalten` | Prüfrezept D‑B03 + Plausibilitätswarnung (12.4) |
| Doppelte Bereinigung bei Summensensor | 10.3, letzter Punkt |
| Schreiben jeden Zyklus zerstört Rampen‑Alterung | Deadband (D‑B08) |
| Regelkreis schwingt | **Sensor‑Versatz** messen (H‑7), `hoch_regelzeit_s` ≥ Versatz. *Nicht* die Totzeit – die verzögert nur (H‑4) |
| Zwei Regler auf einer Größe (HEMS + Shelly, oder n Shellys) | Shelly‑Regelung im Normalbetrieb aus; `shelly_fallback` bei max. einem Speicher (D‑B05) |

### 12.4 Plausibilitätswarnung als Frühwarnsystem

Billig und fängt genau H‑1 ab:

```python
if netz_support_w > 200 and pool_w > 200:
    log.warning("EMS Speicher: Entladung %.0fW UND Pool %.0fW gleichzeitig - "
                "Speicher entlädt in den PV-Überschuss hinein. Prüfen: "
                "speicher_in_residual_enthalten, Summensensor doppelt gezählt, "
                "Umschaltsperre zu lang.", netz_support_w, pool_w)
```

Ein Speicher, der entlädt, während nennenswerter PV‑Überschuss verteilt wird,
ist physikalisch fast immer ein Konfigurationsfehler. Bewusst **ohne**
`debug_output`‑Bedingung – das ist eine echte Fehlkonfiguration, keine
Debug‑Information.

---

## 13. Energy‑Pilot‑Anbindung

Der bestehende Mechanismus (`_ep_num` / `_ep_bool`,
[devices.py:104-117](app/ems/devices.py#L104-L117)) trägt unverändert. Neue
Vorschlagssensoren nach demselben Schema `sensor.ep_<prefix>_<feld>_vorschlag`:

| Feld | Typ | Fallback | Wirkung |
|---|---|---|---|
| `freigabe`, `prio` | – | Nutzerwert | bereits generisch vorhanden (`prio` = **Laden**) |
| `entlade_prio` | num | Nutzerwert | Entladereihenfolge (D‑B17) – der Hebel, mit dem EP später Zyklen zwischen Speichern ausgleichen kann, ohne dass das HEMS eine Strategie kennt |
| `soc_ziel_prozent` | num | `soc_max_prozent` | dynamischer Ladeschluss („heute nur 70 %, morgen viel PV") |
| `soc_min_prozent` | num | Nutzerwert | dynamische Reserve |
| `lade_max_w` | num | `max_ladeleistung_w` | Ladeleistungsdeckel |
| `entlade_max_w` | num | `max_entladeleistung_w` | Entladeleistungsdeckel |
| `betriebsart` | str | Nutzerwert | Modusvorschlag |
| `netzladen`, `netzlade_leistung_w` | – | aus / 0 | **v2**, Abschnitt 11 |

**Fallback‑Semantik zwingend beibehalten** – fällt EP aus, greift der
Nutzerwert. Ein KI‑Ausfall darf den Speicher nie in einen gefährlichen Zustand
bringen ([devices.py:99-102](app/ems/devices.py#L99-L102)).

**Lektion aus dem CHANGELOG anwenden:** Bei `geschuetzte_mindestleistung_w` vs.
`schutz_w` verglich EP gegen die falsche Größe. Deshalb hier von Anfang an
**roh und effektiv getrennt ausliefern**: `max_ladeleistung_w` (Nutzerwert)
*und* `lade_limit_w` (nach Taper und Derating). Dasselbe für die Entladeseite.

---

## 14. Web‑UI

### 14.1 [index.html](app/templates/index.html)

```html
<div class="section">Speicher</div>
<div class="devices" id="battery"></div>
```

Platzierung **vor** „Regelbare Verbraucher" – der Speicher beeinflusst die
Pool‑Rechnung, beim Debuggen will man ihn zuerst sehen.

### 14.2 [app.js](app/static/app.js) – `renderBattery(d)`

| Zeile | Inhalt |
|---|---|
| Titel | Label + Prio‑Badge (Laden) + **Entlade‑Prio‑Badge** + SoC‑Badge |
| SoC‑Balken | Fortschritt mit Markern bei `soc_min` / `soc_max` / `soc_reserve` |
| Freigabe | ✓/✗ |
| Betriebsart | `auto → entladen` (gewünscht → effektiv) + Regelmodus‑Chip |
| Ist | `−1.840 W (Entladen)` bzw. `+2.100 W (Laden)` |
| Anforderung / Neu → HA | mit `changed`‑Highlight wie bei `renderControllable` |
| Limits | `Laden ≤ 5.000 W · Entladen ≤ 5.000 W` (nach Taper) |
| Sperre | `Umschaltsperre: 2m 15s` mit `_elapsed`‑Korrektur wie beim Phasen‑Lock |
| Grund | `blockiert_grund` als Chip, wenn gesetzt |

Kartenfarbe: `off` / `charge` (grün) / `discharge` (blau) / `idle`.

### 14.3 Statuskacheln

Nur wenn mindestens ein Speicher konfiguriert ist:

* `Speicher netto` – `Σ netto_w`
* `SoC ⌀` – kapazitätsgewichtet über `capacity_kwh` aus der Add‑on‑Config
* **`Hausdefizit`** – `hausdefizit_w`, die neue Kerngröße

Weicht `hems_last_gemessen_w` von `hems_last_w` ab, läuft mindestens ein
HEMS‑Gerät fremdgesteuert. Das ist der einzige Fall, in dem `Hausdefizit`
kleiner ist als der sichtbare Netzbezug – ohne Hinweis wirkt das wie ein
Regelfehler (D‑B14). Vorschlag: Kachel als
`1.200 W (2.000 W fremdgesteuert ausgenommen)` erweitern, sobald die Differenz
> 50 W ist.

Und für die Fehlersuche die Überschuss‑Kachel erweitern:
`2.400 W (bereinigt 400 W)`.

### 14.4 [main.py](app/main.py) – `_ctrl_items_battery`

Analog zu [main.py:56](app/main.py#L56) mit allen Helfern aus 8.3, plus
`elif cls == "battery":` in `_handle_device_controls_schema`
([main.py:176-180](app/main.py#L176-L180)).

Bei ~33 Helfern wird die Steuerungskarte lang – Gruppierung sinnvoll
(Freigaben / Leistungsgrenzen / SoC / Regelverhalten). Das erfordert eine
kleine Erweiterung des Schema‑Formats um optionale Untergruppen.

### 14.5 Übersetzungen

`translations/de.yaml` + `en.yaml` um die neuen Config‑Felder ergänzen.

---

## 15. Tests

### 15.1 Neu: `tests/test_battery_device.py`

| Test | Prüft |
|---|---|
| `test_current_w_nur_hems_ladeleistung` | extern erzwungenes Laden zählt nicht |
| `test_current_w_null_bei_netzladen` | Abschnitt 11.3 Regel 1 |
| **`test_gemessene_last_w_auch_bei_netzladen`** | **D‑B14** – Gegenstück zum Test darüber |
| `test_netz_support_immer_messwert` | zählt auch ohne HEMS‑Anforderung |
| `test_soc_max_stoppt_laden` / `test_soc_min_stoppt_entladen` | Grenzen |
| `test_soc_taper_linear` | halbe Leistung bei halbem Band |
| `test_soc_reserve_blockiert_entladung` | Notstromreserve |
| `test_wr_derating_hat_vorrang` | `available_*_entity` gewinnt |
| `test_niemals_laden_bei_hausdefizit` | D‑B10 |
| **`test_entladung_runter_sofort_ungerampt`** | **H‑5 / 5.2** |
| **`test_entladung_hoch_gerampt`** | 5.2 |
| **`test_entlade_abschlag_unterschiesst`** | Sollwert < Hausdefizit |
| `test_huellen_modus_ueberschiesst` | D‑B05, umgekehrtes Vorzeichen |
| `test_totzone_fuehrt_zu_standby` | Mikrozyklen |
| `test_umschaltsperre_blockiert_richtungswechsel` | + `…_laeuft_ab` |
| `test_umschaltsperre_faehrt_standby_nicht_alte_richtung` | 7.6 |
| `test_deadband_beim_senken_der_entladung_aus` | D‑B08 |
| `test_write_reihenfolge_ein_und_ausschalten` | D‑B11 beide Richtungen |
| `test_signierter_sensor_beide_vorzeichen` | D‑B12 |
| `test_fallback_standby_ohne_eigenverbrauchsmodus` | 12.1 |
| `test_fallback_inverter_mit_eigenverbrauchsmodus` | 12.1 |
| `test_schreibt_sicheren_zustand_aktiv_bei_lockout` | **nicht** „nichts tun" |
| `test_leistungssensor_unavailable_faellt_aus_regelung` | 12.1 |
| `test_blockiert_grund_je_sperrfall` | alle 11 Gründe |

### 15.2 Erweiterung `tests/test_run_cycle.py`

| Test | Prüft |
|---|---|
| `test_pool_ohne_speicher_unveraendert` | **Regression** – identisch zu heute |
| `test_entladung_erhoeht_pool_nicht` | **H‑1**, wichtigster Test des Features |
| `test_hausdefizit_schliesst_hems_lasten_aus` | **deine Kernanforderung** |
| `test_heizstab_laeuft_nicht_aus_speicher` | dieselbe Anforderung, Ende‑zu‑Ende |
| **`test_fremdgesteuerter_heizstab_wird_nicht_gedeckt`** | **D‑B14 / F‑5** – Force‑Modus an, `hausdefizit_w` sinkt um die volle Istleistung |
| **`test_pool_ignoriert_fremdlast_weiterhin`** | Gegenprobe: `pool_w` bleibt unverändert, die zwei Summen driften nur auf der Entladeseite |
| `test_defizit_sichtbar_trotz_entladung` | **H‑2** |
| `test_pool_und_hausdefizit_schliessen_sich_aus` | 4.4, **auch mit Fremdlast** |
| `test_speicher_in_residual_false` | D‑B03 |
| `test_zwei_speicher_teilen_hausdefizit` | **H‑3** – Σ == Defizit, nicht 2× |
| `test_drei_speicher_entlade_prioritaetsreihenfolge` | D‑B17 – letzter bleibt bei 0 |
| **`test_entlade_prio_unabhaengig_von_lade_prio`** | **D‑B17** – umgekehrte Reihenfolgen gleichzeitig |
| **`test_entlade_prio_gleichstand_config_reihenfolge`** | stabile Sortierung (D‑B18) |
| **`test_zu_kleine_zuteilung_rastet_auf_null`** | `min_entladeleistung_w`, ersetzt den `proportional`‑Test |
| **`test_netzladender_speicher_ist_keine_hauslast`** | 11.3 Regel 1, zwei Speicher (v2‑Vorbereitung) |
| `test_speicher_prio_1_verdraengt_heizstab` / `…_prio_50_bekommt_rest` | D‑B02 |
| `test_defekter_speicher_blockiert_flotte_nicht` | 10.3 |
| `test_plausibilitaetswarnung_geloggt` | 12.4 via `caplog` |

### 15.3 Property‑Tests in `tests/test_allocation_properties.py`

```python
# P1  Nie gleichzeitig laden und entladen
assert new_lade_w == 0 or new_entlade_w == 0

# P2  pool_w und hausdefizit_w sind komplementaer - auch mit Fremdlast (4.4)
assert pool_w == 0 or hausdefizit_w == 0
assert entlade_basis_w >= pool_roh_w - 1e-6      # die Ungleichung, die P2 traegt

# P3  Entladung überschreitet nie das Hausdefizit
assert sum(b.new_entlade_w for b in batteries) <= hausdefizit_w + 1e-6

# P4  Summe der Ladeleistungen überschreitet den Pool nicht
assert sum(b.new_lade_w for b in batteries) <= pool_w + 1e-6

# P5  SoC-Grenzen werden nie verletzt
assert not (soc >= soc_max and new_lade_w > 0)
assert not (soc <= soc_min and new_entlade_w > 0)

# P6  Entladung sinkt nie langsamer als das Ziel (Asymmetrie, H-5)
assert new_entlade_w <= max(ziel_w, entlade_anf_w)

# P7  Ohne Speicher identisch zum Altverhalten (Referenzimplementierung)
```

### 15.4 Regressionsschutz

Vor Beginn Baseline einfrieren:

```bash
python -m pytest tests/ -q
```

`test_pool_ohne_speicher_unveraendert` und P7 sind der Beweis, dass die
Erweiterung wirklich additiv ist.

---

## 16. Umsetzungsphasen

> **Reihenfolge‑Gate durch die offenen Fragen:** F‑2 (WR‑Anbindung), F‑11
> (Shelly an/aus) und F‑12 (Sensorquelle) sind allesamt Phase‑0‑Themen und
> blockieren **Phase 2 und 3** – dort wird zum ersten Mal geschrieben.
> **Phase 1 ist davon unabhängig** und kann sofort beginnen: sie liest nur,
> beseitigt H‑1/H‑2 und braucht weder Register noch Sollwerte.
> Das ist die praktische Konsequenz aus „F‑2 ist noch nicht sicher".

### Phase 0 · Vorbereitung: **messen**, kein Code

Diese Phase liefert die Zahlen, mit denen die Rampen dimensioniert werden.
Nicht überspringen – ohne den Versatzwert ist `hoch_regelzeit_s` geraten.

- [ ] **Messpunkt** `residual_power_entity` verifizieren (Prüfrezept D‑B03)
- [ ] **Update‑Rate des Überschusssensors** (H‑6): in der HA‑History ansehen –
      wie oft ändert er sich, wird gemittelt? Bei Shelly 3EM lokal typisch ~1 s.
      **Ergebnis notieren:** ______ s
- [ ] **★ Sensor‑Versatz messen** (H‑7, der wichtigste Wert): Entladesollwert
      von Hand von 0 auf 2 kW setzen. Dann `residual_power_entity` und den
      Batterie‑Leistungssensor in der HA‑History **übereinanderlegen** und
      ablesen, wie weit ihre Sprünge zeitlich auseinanderliegen.
      → `hoch_regelzeit_s` ≥ dieser Wert, `entlade_sofort_schwelle_w` > dem
      dabei sichtbaren Leistungsfehler.
      **Ergebnis notieren:** ______ s / ______ W
- [ ] **Totzeit der Gesamtschleife** (H‑4, nur informativ): wann reagiert
      `residual_power_entity` überhaupt auf den Sprung? Bestimmt die
      Reaktionsgeschwindigkeit, **nicht** die Stabilität.
      **Ergebnis notieren:** ______ s
- [ ] **★ F‑11 · Shelly‑Regelung abschaltbar?** Wie wird sie aktiviert/
      deaktiviert (API, MQTT, Schalter)? → Voraussetzung für D‑B05 und den
      Watchdog. **Ist sie nicht abschaltbar, darf Phase 3 nicht starten** –
      HEMS und Shelly gleichzeitig aktiv ist der Grenzzyklus aus Merksatz 2.
- [ ] **Hat der WR einen Modbus‑Watchdog?** → 12.2 Ebene 4
- [ ] **★ F‑2 · Wechselrichter‑Steuerung festlegen** (aktuell offen):
      Register/Services, nötige Reihenfolge Modus↔Leistung, Übernahmezeit.
      Ergebnis entscheidet über `steuerprofil` und die Schreibreihenfolge in
      D‑B11. **Gate für Phase 2.**
- [ ] **F‑12 · Quelle von `residual_power_entity`** notieren (welches Gerät,
      lokal oder Cloud) – zusammen mit dem Batteriesensor bestimmt sie den
      Versatz aus dem Punkt darüber
- [ ] HA‑Package mit allen Helfern anlegen (Vorlage 8.6)
- [ ] HA‑Automation „Helfer → WR" schreiben und **ohne HEMS** testen
- [ ] Baseline: `pytest tests/ -q`

**Akzeptanz:** Speicher vollständig von Hand steuerbar; Shelly‑Regelung
gezielt an/aus schaltbar; **Sensor‑Versatz ist eine gemessene Zahl.**

### Phase 1 · Read‑only: Pool‑Bereinigung

Beseitigt H‑1 und H‑2 sofort, ohne jedes Steuerrisiko.

- [ ] `Device.netz_support_w` (Default 0.0)
- [ ] `Device.gemessene_last_w` + Overrides in `ControllableDevice` und
      `BinaryDevice` (D‑B14) – **einzige Änderung an Bestandsklassen**
- [ ] `BatteryDevice`‑Grundgerüst: `update_from_ha`, `current_w`,
      `gemessene_last_w`, `netz_support_w`, `max_relief_w`, `to_status_dict`
- [ ] `get_write_ops()` gibt **`[]`** zurück (Phase‑1‑Stub, klar kommentiert)
- [ ] `_build_devices` Zweig `battery`; `config.yaml` erweitern
- [ ] `run_cycle`: `residual_bereinigt_w`, `pool_roh_w`, `entlade_basis_w`,
      `pool_w`, `hausdefizit_w`, geändertes Defizit
- [ ] Plausibilitätswarnung (12.4)
- [ ] Status‑Snapshot + UI‑Karte (read‑only) + Kachel `Hausdefizit`
- [ ] Tests aus 15.2 außer den Schreibtests

**Akzeptanz:** Bei manueller Speicherentladung steigt `pool_w` **nicht**;
`hausdefizit_w` zeigt den Hausverbrauchs‑Fehlbetrag; Heizlüfter schaltet nicht
mehr wegen Batteriestrom zu; ein von Hand eingeschalteter Heizstab senkt
`hausdefizit_w` um seine volle Istleistung (F‑5). Bestehende Tests unverändert
grün.

### Phase 2 · Ladesteuerung  *(Gate: F‑2 beantwortet)*

- [ ] SoC‑Limits + Taper (`_lade_limit_w`), WR‑Derating
- [ ] `min_technisch_w` / `max_technisch_w` aus den Speicherhelfern befüllen
- [ ] `calculate_ramp` Ladeseite, D‑B10‑Klemme
- [ ] `get_write_ops`: Ladeleistung + Betriebsart, feste Reihenfolge, Deadband
- [ ] Sicherer Zustand (12.1) für den Ladepfad
- [ ] Tests Ladepfad, SoC‑Grenzen, Prioritätskonkurrenz

**Akzeptanz:** Speicher lädt aus Überschuss, respektiert `prioritat`, stoppt
bei `soc_max`, lädt nie bei Hausdefizit.

### Phase 3 · Entladesteuerung, ein Speicher  *(Gate: F‑2 + F‑11)*

- [ ] `_entlade_limit_w`, `entlade_kapazitaet_w`, `set_discharge_target`
- [ ] `EMSController._allocate_discharge` (Einzelspeicher‑Pfad)
- [ ] `calculate_ramp` Entladeseite **mit Asymmetrie (5.2)**, Totzone,
      Umschaltsperre
- [ ] `entlade_abschlag_w` (global) + `entlade_sofort_schwelle_w` (pro Gerät),
      dimensioniert nach den Phase‑0‑Messwerten
- [ ] Vollständige Sicherheitsmatrix 12.1 inkl. aktivem Schreiben
- [ ] Watchdog: `post_cycle_script`‑Heartbeat + HA‑Automation (12.2)
- [ ] Tests Entladepfad, Asymmetrie, Fallbacks

**Akzeptanz:** Hausverbrauch wird gedeckt, Überschussverbraucher nicht; kein
Pendeln; HEMS‑Absturz führt binnen 2 Minuten zum sicheren Zustand.

### Phase 3b · entfällt

In v2 war hier ein separater Speicher‑Subzyklus geplant. Bei `interval_s = 3`
ist er gegenstandslos (D‑B06, 5.5). Stattdessen nach zwei Wochen Betrieb:

- [ ] Netzbezug/Export im HA‑Energiedashboard auswerten
- [ ] Prüfen, ob ein Grenzzyklus in der Entladeleistung sichtbar ist (H‑7) –
      falls ja, `hoch_regelzeit_s` erhöhen, **nicht** den Takt verkürzen

### Phase 4 · Mehrspeicher + Feinschliff

- [ ] Helfer `entlade_prioritat` + `_discharge_order` (D‑B17/D‑B18)
- [ ] Mehrspeicher‑Pfad in `_allocate_discharge` (serielle Zuteilung, Reste)
- [ ] Vorausschauendes `hausdefizit_prognose_w` (D‑B07)
- [ ] Ausfall eines Speichers isolieren
- [ ] Property‑Tests P1–P7

> Entfallen gegenüber v3: `speicher_entlade_strategie` und der
> `proportional`‑Zweig (F‑6/D‑B18), `entladung_deckt_fremdgesteuerte_lasten`
> (F‑5 → nach Phase 1 vorgezogen und fest verdrahtet), globaler
> `entlade_abschlag` (F‑4 bereits in v3 entschieden).

### Phase 5 · Energy Pilot + Doku

- [ ] EP‑Vorschlagsfelder (Abschnitt 13), roh + effektiv getrennt
- [ ] README: Abschnitt „Speicher (`BatteryDevice`)" mit Entitätstabellen,
      Prüfrezept D‑B03, Totzeitmessung, Watchdog‑Anleitung, Wirkungsgrad‑Hinweis
- [ ] CHANGELOG unter `Unreleased`
- [ ] `translations/de.yaml` + `en.yaml`
- [ ] HA‑Package‑Vorlage beilegen

### Phase 6 · Netzladen (v2)

Abschnitt 11, erst wenn Phase 1–5 stabil laufen.

---

## 17. Nicht in Scope v1

| Thema | Begründung / Ausblick |
|---|---|
| **Netzladen** | Phase 6, Schnittstellen stehen (Abschnitt 11) |
| **Peak Shaving** | Braucht 15‑min‑Leistungsmittelwerte + Leistungspreis‑Modell |
| **Notstrom / Ersatzstrombetrieb** | WR‑Domäne; bei Netzausfall gibt es keinen verwertbaren Überschuss. `soc_reserve_prozent` bildet nur die Vorhaltung ab |
| **SoC‑Prognose / Zielladung bis Uhrzeit** | Prognosethema → EP (`soc_ziel_prozent`‑Vorschlag ist die Schnittstelle) |
| **SoC‑Ausgleich zwischen Speichern** | **Durch F‑6 dauerhaft ausgeschlossen**, nicht nur vertagt. Entladereihenfolge ist strikt `entlade_prioritat` (D‑B18); Ausgleich ist Konfigurations‑ oder EP‑Sache |
| **Proportionale / kapazitätsgewichtete Entladung** | dito – ersatzlos gestrichen, spart die Mindestleistungs‑Umverteilung |
| **Zyklenzählung / Alterungsmodell** | Braucht Langzeit‑Persistenz; das HEMS ist bewusst zustandsarm |
| **DC‑gekoppelte Hybridspeicher** | Andere Physik – Speicher hinter dem PV‑WR, `residual_w` verhält sich anders. Eigene Klasse |
| **Wirkungsgrad‑optimierte Prioritätsumkehr** (Sommer/Winter automatisch) | Bewertungsfrage → EP via `prio_vorschlag` |
| **Regelung auf ein anderes Ziel als Netz ±0** | z. B. konstanter Bezug für einen Tarif – erst wenn Netz‑±0 sauber läuft |

---

## 18. Offene Fragen an dich

**Erledigt (v3):**

* ~~F‑1 (Kann der WR selbst regeln?)~~ → Ja über Shelly 3EM, aber skaliert nicht
  auf n und ist mit >5 s langsamer als der HEMS‑Zyklus. **HEMS regelt zentral**
  (D‑B05); Shelly wird Rückfallebene.
* ~~F‑4 (Abschlag pro Speicher oder global?)~~ → **global**, einmal in
  `_allocate_discharge` angewandt.
* ~~F‑7 (`interval_s = 30` akzeptabel?)~~ → gegenstandslos, du fährst 3 s.
  Phase 3b entfällt.

**Erledigt (v4, aus
[`erweiterung_ac_speicher_1_antworten.md`](erweiterung_ac_speicher_1_antworten.md)):**

| # | Antwort | Wohin sie geflossen ist |
|---|---|---|
| ~~**F‑3**~~ | getrennte Lade‑ und Entladepriorität | **D‑B17**, 8.3, 8.6, 10.2, 13, 14.2, 15.2 |
| ~~**F‑5**~~ | nein – Speicher deckt keine fremdgesteuerte HEMS‑Last | **D‑B14**, 4.2–4.5, 7.1, 7.3, 9, 14.3, 15 |
| ~~**F‑6**~~ | strikt nach Priorität, kein SoC‑Ausgleich; `capacity_kwh` in der Add‑on‑Config | **D‑B18**, 8.1, 10.1–10.3, 17 |
| ~~**F‑8**~~ | kein Summensensor in HA | 10.3 |
| ~~**F‑9**~~ | Einspeisevergütung vorhanden, Export zulässig | 5.4, 12.3 |
| ~~**F‑10**~~ | ein Netzübergabe‑Messpunkt, gilt für alle Speicher | D‑B03, 10.3 |

**Weiterhin offen – alle drei sind Phase‑0‑Themen:**

| # | Frage | Blockiert | Warum sie den Entwurf ändert |
|---|---|---|---|
| **F‑2** | Welcher Wechselrichter, welche Register/Services? Moduswechsel **vor** dem Leistungswert nötig? Übernahmezeit? | Phase 2 + 3 | `get_write_ops`‑Reihenfolge (D‑B11) und Wahl des `steuerprofil`. Antwort v4: „noch nicht sicher" → Feld bleibt reserviert, **Phase 1 läuft ohne diese Antwort** |
| **F‑11** | Wie wird die Shelly‑Nulleinspeisung an/aus geschaltet (API, MQTT, Schalter im Gerät)? | Phase 3 | Watchdog‑Ebene 3 (12.2) und „im Normalbetrieb aus" (D‑B05). Nicht abschaltbar ⇒ HEMS und Shelly regeln gegeneinander (Merksatz 2) |
| **F‑12** | Aus welcher Quelle kommt `residual_power_entity` – dieselbe wie beim Batterie‑Leistungssensor? | Dimensionierung `hoch_regelzeit_s` | Bestimmt den Sensor‑Versatz (H‑7), das einzige echte Oszillationsrisiko. F‑10 klärt, dass es **ein** Messpunkt ist – nicht **welcher** |

---

## Anhang A · Zusammenfassung der Codeänderungen

| Datei | Art | Umfang |
|---|---|---|
| [app/ems/devices.py](app/ems/devices.py) | +`Device.netz_support_w` (5 Z.), +`Device.gemessene_last_w` + 2 Overrides (12 Z., D‑B14), +`BatteryDevice` | ~395 Zeilen neu |
| [app/ems/controller.py](app/ems/controller.py) | `_build_devices`‑Zweig, `run_cycle` Schritte 3–5/9, `_allocate_discharge`, `_discharge_order` (jetzt 2 Z., D‑B18), Warnung, Logging | ~100 neu, ~15 geändert |
| [app/main.py](app/main.py) | `_ctrl_items_battery` (inkl. `entlade_prioritat`), Schema‑Zweig, Config‑Optionen | ~40 neu |
| [app/ha_client.py](app/ha_client.py) | **keine Änderung** (Subzyklus entfällt, D‑B06) | 0 |
| [app/static/app.js](app/static/app.js) | `renderBattery`, Filter, Kacheln, Fremdlast‑Hinweis | ~85 neu |
| [app/templates/index.html](app/templates/index.html) | Section + CSS | ~20 neu |
| [config.yaml](config.yaml) | `class`‑Liste, 10 Gerätefelder, 1 globale Option | ~18 |
| [README.md](README.md) | Speicher‑Abschnitt, Tabellen, Prüfrezepte, Watchdog, **Hinweis Fremdlast** | ~260 |
| `tests/test_battery_device.py` | neu | ~460 |
| [tests/test_run_cycle.py](tests/test_run_cycle.py) | 17 neue Tests | ~360 |
| [tests/test_allocation_properties.py](tests/test_allocation_properties.py) | 7 Invarianten | ~90 |

**Geänderte Zeilen im Bestandscode: ~30**, plus 12 rein additive Zeilen in
`ControllableDevice`/`BinaryDevice` (`gemessene_last_w`, greift nur, wenn
jemand sie summiert). Der Rest ist additiv. Genau **vier Formeln** in
[controller.py](app/ems/controller.py) tragen das gesamte Risiko –
`residual_bereinigt_w`, `pool_roh_w`, `entlade_basis_w`, `hausdefizit_w`.

Ohne konfigurierten Speicher bleibt das Verhalten bit‑identisch: die ersten
beiden sind dann Identitätsoperationen (`netz_support_w = 0`), und die beiden
neuen haben schlicht keinen Abnehmer – `_allocate_discharge` läuft über eine
leere Liste. Das ist der Inhalt von `test_pool_ohne_speicher_unveraendert`
und P7.

---

## Anhang B · Vier Merksätze

> **1 · Ein Speicher ist kein Verbraucher mit Vorzeichen.**
> Er verfälscht den Messwert, auf dem das gesamte HEMS aufbaut.
> Erst bereinigen, dann regeln – nie umgekehrt.

> **2 · Zwei Regler auf einer Messgröße haben kein Gleichgewicht.**
> `D₁ + D₂ = L` ist eine Gleichung mit zwei Unbekannten.
> Egal ob zwei Speicher, oder HEMS und Shelly gleichzeitig –
> das Ergebnis ist immer ein Grenzzyklus.
> Genau ein Regler, oder zentrale Aufteilung.

> **3 · Der Pool kannte die Antwort schon.**
> `pool_roh_w` positiv = Überschuss zum Verteilen.
> `pool_roh_w` negativ = Hausverbrauch, den der Speicher decken soll.
> Die Überschussverbraucher sind per Konstruktion draußen –
> es braucht keine Sonderlogik, nur das Weglassen der `max(…, 0)`‑Klemme.

> **4 · Wer die Last einschaltet, entscheidet wer sie bezahlt.**
> `current_w` filtert Force‑Modus heraus – richtig für den Pool.
> `gemessene_last_w` filtert nichts – richtig für die Entladung.
> Zwei Summen, weil „was kann ich freigeben?" und
> „was soll der Speicher decken?" zwei verschiedene Fragen sind.
