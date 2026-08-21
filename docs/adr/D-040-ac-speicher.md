# D-040: AC-gekoppelte Speicher als eigene Geräteklasse, mit bereinigtem Pool und getrennter Entladepriorität

- **Datum:** 20.08.2026
- **Status:** Aktiv, Entladequelle teilweise ersetzt durch D-044
- **Betrifft:** [`app/ems/devices.py`](../../app/ems/devices.py),
  [`app/ems/controller.py`](../../app/ems/controller.py),
  [`app/main.py`](../../app/main.py), [`config.yaml`](../../config.yaml),
  `web/src/`, die HA-Helfer-Verträge in [datenmodell.md](../datenmodell.md)

> Diese ADR fasst die Entscheidungen D-B01 bis D-B22 aus
> [`erweiterungen/erweiterung_ac_speicher_1.md`](../../erweiterungen/erweiterung_ac_speicher_1.md)
> zusammen. Die dortigen IDs bleiben als Referenz erhalten; nach außen gilt D-040.

> **Fortschreibung:** [D-044](D-044-hausleistungsbilanz-ac-speicher.md) ersetzt die Quelle für
> `entlade_basis_w` und `hausdefizit_w` durch eine separate Hausleistungsbilanz. Pool-Bereinigung,
> Ladepfad, Prioritäten und der signierte Speicher-Sollwert aus dieser ADR gelten weiter.

## Kontext

Das HEMS verteilte bisher ausschließlich Überschuss an Verbraucher. Ein Speicher ist der erste
Teilnehmer, der Leistung auch **abgeben** kann — und damit der erste, der den Messwert
verfälscht, auf dem das gesamte System aufbaut.

Zwei Gefahren entstehen daraus unmittelbar:

- **Pool-Aufschaukelung.** `pool_w = max(residual_w + Σ current_w, 0)`. Entlädt der Speicher mit
  3 kW, steigt `residual_w` um 3 kW. Das HEMS liest das als Überschuss, schaltet einen Verbraucher
  zu, der Netzbezug steigt, der Speicher entlädt mehr — positive Rückkopplung, Speicher in einem
  Zyklus leer.
- **Defizit-Maskierung.** `current_deficit_w = max(-residual_w, 0)`. Deckt der Speicher die
  Hauslast, ist `residual_w ≈ 0`, es wird kein Defizit erkannt, und der Heizstab läuft faktisch
  aus der Batterie — genau das, was ausgeschlossen sein soll.

Randbedingungen der Anlage: `interval_s = 3`, ein Messpunkt an der Netzübergabe für alle
Speicher, Einspeisevergütung vorhanden, und ein bereits installierter, DC-gekoppelter E3DC, der
sich selbst regelt.

## Betrachtete Optionen

### Option A — Der Speicher regelt selbst, das HEMS setzt nur eine Obergrenze

- Dafür: kein neuer Regelkreis im HEMS; das Gerät ist näher an seinen eigenen Messwerten.
- Dagegen: **skaliert nicht auf n > 1.** Zwei autonome Regler am selben Netzpunkt lösen
  `D₁ + D₂ = L` — eine Gleichung, zwei Unbekannte. Es gibt kein eindeutiges Gleichgewicht,
  das Ergebnis ist ein Grenzzyklus. Kein SoC-Bewusstsein, keine Prioritäten, keine Tariflogik.

### Option B — Das HEMS koordiniert zentral und schreibt Sollwerte

- Dafür: deterministische Aufteilung über beliebig viele Speicher; Prioritäten, SoC-Grenzen und
  spätere Tariflogik sind möglich; nutzt den bestehenden 3-s-Zyklus.
- Dagegen: das HEMS trägt die Regelgüte am Netzpunkt — eine neue Aufgabenklasse. Ein Ausfall des
  Add-ons lässt den letzten Sollwert stehen und braucht deshalb zwingend einen Watchdog.

### Option C — Eigene Klasse neben `Device` statt Erben von `ControllableDevice`

- Dafür: sauber getrennte Verantwortung, kein Erbe von Verbraucher-Semantik.
- Dagegen: rund 60 Zeilen Duplikat (Rampen, Deadband, Grenzen) und manuelles Einhängen in jede
  Controller-Schleife. Der Ladepfad ist funktional deckungsgleich mit einem regelbaren Verbraucher.

## Entscheidung

**Option B, umgesetzt als `BatteryDevice(ControllableDevice)`.**

1. **Erst bereinigen, dann regeln.** Zwei neue Default-Properties auf `Device`:
   `netz_support_w` (gemessene Einspeisung ins Hausnetz) und `gemessene_last_w` (Leistungsaufnahme
   **ohne** Force-Modus-Filter). Daraus im Zyklus:

   ```
   residual_bereinigt_w         = residual_w − Σ netz_support_w
   pool_roh_w                   = residual_bereinigt_w + Σ current_w
   pool_w                       = max(pool_roh_w, 0)

   # Seit D-044 für AC-Speicher:
   battery_residual_bereinigt_w = battery_residual_w − Σ netz_support_w
   entlade_basis_w              = battery_residual_bereinigt_w + Σ gemessene_last_w
   hausdefizit_w                = max(−entlade_basis_w, 0)
   ```

   Die bisherige `max(…, 0)`-Klemme warf die negative Hälfte des **Pool-Sensors** weg. Bis D-044
   war sie der Entladebedarf; seither kommt dieser aus der eigenen Hausleistungsbilanz. Die
   Rückrechnung der Überschussverbraucher über `gemessene_last_w` bleibt erhalten, damit sie nicht
   vom Speicher gedeckt werden.

2. **Zwei Summen statt einer.** `current_w` filtert den Force-Modus heraus — richtig für den Pool,
   falsch für die Entladung: ein von Hand eingeschalteter Heizstab landete sonst im Hausverbrauch
   und würde vom Speicher gedeckt. `gemessene_last_w` filtert nichts. D-044 führt dafür einen
   zweiten Sensorvertrag ein; Pool und Hausdefizit können deshalb diagnostisch gleichzeitig positiv
   sein. Der einzelne signierte Sollwert und die Richtungsauflösung verhindern trotzdem, dass ein
   Speicher gleichzeitig lädt und entlädt.

3. **Getrennte Lade- und Entladepriorität.** Ein Speicher hat zwei Rollen, die nichts miteinander
   zu tun haben. „Lade mich zuletzt, entlade mich zuerst" ist eine sinnvolle Konfiguration
   (kleiner Pufferspeicher neben großem Hausspeicher) und mit einer Zahl nicht ausdrückbar.

4. **Ein signierter Sollwert plus Betriebsart** als Ausgabe. Das HEMS schreibt HA-Helfer; die
   Übersetzung nach Modbus oder MQTT macht eine HA-Automation. Register, Reihenfolge am Gerät und
   Übernahmezeit sind damit ausdrücklich kein HEMS-Thema.

5. **Der sichere Zustand ist immer `standby`,** und er wird **aktiv geschrieben.** „Nichts tun"
   ließe den letzten Sollwert stehen, und der Speicher entlädt bis leer weiter.

6. **Der vorhandene E3DC ist kein HEMS-Gerät.** Er regelt sich selbst und bekommt keine
   `BatteryDevice`-Instanz. Seit D-044 ist seine Leistung bewusst Teil der separaten
   Hausleistungsbilanz; er wird nie als HEMS-Speicher abgezogen oder angesteuert.

Gegen Option A spricht der Skalierungseinwand allein schon zwingend. Option C wird erst
interessant, wenn die Overrides ausufern; heute trägt die Vererbung den kompletten Ladepfad
inklusive 2-Pass-Allokation, Rampe, Deadband und Schutzleistung ohne eine Zeile neuen Code.

## Folgen

- **Positiv:** Ohne konfigurierten Speicher bleibt das Verhalten bit-identisch — `netz_support_w`
  ist 0, die Bereinigung eine Identitätsoperation, und `_allocate_discharge` läuft über eine leere
  Liste. Abgesichert durch `test_pool_ohne_speicher_unveraendert` und die Property P7. Die
  Abgrenzung „nur Hausverbrauch, nicht Überschussverbraucher" fällt aus der bestehenden
  Pool-Definition heraus, statt aus einer Sonderregel.
- **Negativ:** Läuft ein HEMS-Gerät fremdgesteuert, sinkt `hausdefizit_w` und der Restbezug
  erscheint am Netz statt aus dem Speicher. Das ist gewollt, sieht im Energiedashboard aber wie
  ein Regelfehler aus — die Statuskachel benennt es deshalb ausdrücklich. Der Verschleiß verteilt
  sich ungleich, weil strikt nach Priorität entladen wird; einziger Hebel ist
  `entlade_prioritat`. Und ohne autonome Rückfallebene kostet ein Add-on-Ausfall Netzbezug.
- **Aufwand:** Der ursprüngliche Speicherpfad ergänzte die Poolformeln und die Speicherhelfer.
  D-044 erweitert ihn um einen zweiten globalen Sensorvertrag für `entlade_basis_w` und
  `hausdefizit_w`.

## Rücknahmebedingung

Drei konkrete Signale:

1. **Ein Grenzzyklus in der Entladeleistung** ist in der HA-History sichtbar, obwohl
   `hoch_regelzeit_s` über dem gemessenen Sensor-Versatz liegt. Dann trägt die absolute
   Sollwertformulierung nicht und es braucht eine gedämpfte Struktur — **nicht** einen kürzeren
   Takt.
2. **Die Overrides in `BatteryDevice` wachsen so weit,** dass von der geerbten
   `ControllableDevice`-Logik nur noch die Feldnamen übrig sind. Dann ist Option C fällig.
3. **Ein Speicher entlädt messbar in den PV-Überschuss hinein.** Die Plausibilitätswarnung in
   `run_cycle` meldet das; tritt sie bei korrekter Konfiguration auf, ist die Grundannahme über
   den Messpunkt falsch.
