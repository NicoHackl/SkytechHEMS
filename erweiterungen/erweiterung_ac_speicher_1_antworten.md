# Antworten zu den offenen Fragen · AC‑Speicher‑Erweiterung

> Bezug: [`erweiterung_ac_speicher_1.md`](erweiterung_ac_speicher_1.md),
> Abschnitt 18. Eingearbeitet in **Entwurf v4**.

## Antworten

- F2: Das ist noch nicht sicher wie ich das einbinde und wie die ansteuerung/werte schreiben für den Speicher machen werde
- F3: Es soll eine (lade)Prio geben (die normale Prio die für HEMS geräte schon existiert) und eine Entlade prio (speziell für speicher)
- F5: Nein
- F6: SOC ausgleich wird es nicht geben wir werden strikt nach prio arbeiten, die Kapazität soll man in der App-Config angeben können (ist auch sinnvoll wenn mal eine Energy-Pilot integration kommt)
- F8: Es wird kein Summensensor von HA-Seiten bereitgestellt
- F9: Einspeisevergütung bekomme ich, also ja ist rechtlich möglich
- F10: Es wird die Netzübergabeleistung angegeben, dieser wert gilt dann für alle speicher

---

## Was daraus im Entwurf geworden ist

### F‑2 · WR‑Anbindung noch offen

Keine Entscheidung erzwungen. Folgen:

* `steuerprofil` (`zwei_entitaeten` | `signiert` | `modus_und_leistung`)
  **bleibt als reserviertes Configfeld** – genau dafür war es gedacht.
* D‑B11 (Betriebsart vor Leistung, beim Abschalten umgekehrt) bleibt die
  konservative Annahme, bis die Register bekannt sind.
* **Neues Reihenfolge‑Gate im Phasenplan:** F‑2 blockiert Phase 2 und 3, weil
  dort zum ersten Mal geschrieben wird. **Phase 1 (read‑only) ist davon
  unabhängig** und kann sofort starten – sie beseitigt H‑1 und H‑2 und braucht
  weder Register noch Sollwerte.

### F‑3 · Getrennte Lade‑ und Entladepriorität → **D‑B17**

| Rolle | Größe | Herkunft |
|---|---|---|
| Laden | `prioritat` | bestehender Helfer, alle Gerätetypen |
| Entladen | `entlade_prioritat` | **neu**, `input_number.ems_<p>_entlade_prioritat`, Default 50, nur Speicher |

* `_discharge_order()` sortiert danach aufsteigend (klein = zuerst),
  Gleichstand → Config‑Reihenfolge über die stabile Sortierung.
* EP‑Vorschlagsfeld `sensor.ep_<p>_entlade_prio_vorschlag` mit der üblichen
  Fallback‑Semantik.
* Bewusst zugelassen: widersprüchliche Reihenfolgen („lade mich zuletzt,
  entlade mich zuerst"). Das ist eine sinnvolle Konfiguration, kein Fehler –
  aber der erstplatzierte Speicher zykelt dann deutlich stärker.

### F‑5 · Fremdgesteuerte Lasten deckt der Speicher **nicht** → **D‑B14**

Die Option `entladung_deckt_fremdgesteuerte_lasten` **entfällt ersatzlos**,
das Verhalten ist fest verdrahtet. Technisch war das die
folgenreichste Antwort – sie kostet eine zweite Summe im Regelzyklus:

```
hems_last_w          = Σ d.current_w          (Force gefiltert)   -> Pool
hems_last_gemessen_w = Σ d.gemessene_last_w   (roher Messwert)    -> Entladung

pool_roh_w      = residual_bereinigt_w + hems_last_w
entlade_basis_w = residual_bereinigt_w + hems_last_gemessen_w

pool_w        = max( pool_roh_w,      0)
hausdefizit_w = max(-entlade_basis_w, 0)
```

Neue Default‑Property `Device.gemessene_last_w` (0.0), überschrieben in
`ControllableDevice` (`_actual_w`), `BinaryDevice`
(`power_w if _actual_on`) und `BatteryDevice` (`_lade_ist_w`, **auch bei
Netzladen**).

Zwei Punkte, die dabei geprüft wurden:

1. **Invariante P2 überlebt.** Wegen `gemessene_last_w ≥ current_w` je Gerät
   gilt `entlade_basis_w ≥ pool_roh_w`, also weiterhin
   „`pool_w > 0` ⇔ `hausdefizit_w = 0`". Der Beweis steht in 4.4.
2. **Kreisstrom‑Schutz fällt gratis ab (v2).** Weil die Battery‑Klasse ihre
   Ladeleistung auch bei Netzladen meldet, kann ein netzladender Speicher
   für einen anderen Speicher nicht wie Hausverbrauch aussehen. D‑B16 sperrt
   nur den *eigenen* Entladepfad.

**Preis, offen benannt:** Läuft der Heizstab von Hand, sinkt `hausdefizit_w`
und der Restbezug erscheint am Netz statt aus dem Speicher. Gewollt – sieht im
Energiedashboard aber wie ein Regelfehler aus. Gehört in README und UI‑Kachel.

### F‑6 · Strikt nach Priorität, kein SoC‑Ausgleich → **D‑B18**

Gestrichen: `speicher_entlade_strategie` (Config‑Option), die Strategien
`soc_ausgleich` / `proportional` / `kapazitaet`, der `proportional`‑Zweig in
`_allocate_discharge` samt Mindestleistungs‑Umverteilung und der zugehörige
Testfall. `_discharge_order` schrumpft auf zwei Zeilen.

`capacity_kwh` bleibt in der **Add‑on‑Config** (nicht als HA‑Helfer): ändert
sich nie im Betrieb, und eine spätere Energy‑Pilot‑Integration liest sie ohne
Helfer‑Roundtrip. Verwendung heute: kapazitätsgewichteter SoC‑Schnitt und
`energie_kwh` in der Statusanzeige.

Ungleicher Verschleiß wird damit bewusst in Kauf genommen; einziger Hebel
dagegen ist `entlade_prioritat` – von Hand oder später per EP‑Vorschlag.

### F‑8 · Kein Summensensor

`netz_support_w` summiert ausschließlich die Einzelsensoren je Speicher. Der
Fehlerfall „doppelte Bereinigung" (10.3) ist damit konstruktiv ausgeschlossen;
die Warnung bleibt für den Fall stehen, dass später doch ein Summensensor
auftaucht.

### F‑9 · Batterieexport zulässig

Die Wirtschaftlichkeitsrechnung aus 5.4 gilt unverändert:
`entlade_abschlag_w` **klein halten (20–30 W)**, kein harter Export‑Stopp.
Begründung: der Abschlag kostet dauerhaft Netzbezug (~30 W ≈ 260 kWh/Jahr),
der Export ist transient (~12 €/Jahr) und wird zusätzlich vergütet.
Die v3‑Ausnahme „bei Einspeiseverbot Abschlag hochziehen" ist entfernt und
müsste bei geänderter Förderlage neu eingeführt werden.

### F‑10 · Ein Messpunkt an der Netzübergabe

* `speicher_in_residual_enthalten = true` ist für diese Anlage bestätigt
  (Prüfrezept D‑B03 trotzdem einmal durchführen – ein Fehler hier *ist* H‑1).
* Es gibt **keinen** speicherlokalen Netzsensor. Damit ist dezentrale
  Nulleinspeisung nicht nur schlechter, sondern gar nicht möglich – D‑B05
  (zentrale Koordination) ist die einzige mögliche Architektur, nicht die
  bevorzugte.
* **Nicht** mitbeantwortet: aus welcher Quelle dieser Sensor kommt → F‑12.

---

## Weiterhin offen

| # | Frage | Blockiert |
|---|---|---|
| **F‑2** | Wechselrichter, Register/Services, Reihenfolge Modus↔Leistung, Übernahmezeit | Phase 2 + 3 |
| **F‑11** | Wie wird die Shelly‑Nulleinspeisung an/aus geschaltet (API, MQTT, Schalter)? Nicht abschaltbar ⇒ HEMS und Shelly regeln gegeneinander | Phase 3, Watchdog‑Ebene 3 |
| **F‑12** | Quelle von `residual_power_entity` – dieselbe wie beim Batterie‑Leistungssensor? Bestimmt den Sensor‑Versatz (H‑7) | Dimensionierung `hoch_regelzeit_s` |

Alle drei sind Phase‑0‑Themen: sie blockieren keine Planung, wohl aber die
Inbetriebnahme des Schreibpfads.
