# D-053: Zwangsbetrieb je Gerät über `ems_<prefix>_force` und `ems_<prefix>_force_leistung_w`

- **Datum:** 15.09.2026
- **Status:** Aktiv
- **Betrifft:** [`app/ems/devices.py`](../../app/ems/devices.py),
  [`app/ems/controller.py`](../../app/ems/controller.py),
  [`app/flow_publisher.py`](../../app/flow_publisher.py), [`app/main.py`](../../app/main.py),
  `web/src/`, die HA-Helfer-Verträge in [device_classes/](../device_classes/) und der
  Statusvertrag in [datenmodell.md](../datenmodell.md)

## Kontext

Das HEMS kannte bis hierher nur Achsen, die ein Gerät **sperren**: Bedienfreigabe, technische
Freigabe, Gerätemodus, globaler Regelmodus, Hard-Lockout, Notabschaltung. Keine Achse konnte ein
Gerät **erzwingen**. Wer den Heizstab an einem trüben Tag trotzdem laufen lassen wollte, musste am
Anforderungshelfer vorbei eine eigene Automation schreiben — und kollidierte im nächsten Zyklus
mit dem HEMS, das den Sollwert wieder auf `0` setzt.

Gewünscht war je Gerät ein Zwangsschalter, der das Gerät unabhängig vom Überschuss einschaltet,
und für regelbare Geräte zusätzlich eine vorgegebene Leistung.

Randbedingungen:

- Bestehende Helfer heißen `<domain>.ems_<prefix>_<suffix>`; das Add-on legt keine Helfer an.
- Der Begriff „Force-Modus" war im Code bereits belegt — für die **Fremdsteuerung** (Schalter
  extern an, ohne HEMS-Anforderung). Er musste frei werden, damit `force` eindeutig ist.
- `eligible` ist Datenvertrag zur Oberfläche, zur Power Flow Card und zum Energy Pilot: die
  Freigabeentscheidung des Zyklus. Sie speist die Pool-Reservierung, die Rückrechnung in den Pool
  und die Prioritätskaskade.
- D-B14 (in D-040): eine HEMS-Last wird nie vom Speicher gedeckt.

## Betrachtete Optionen

### Option A — Vierter Gerätemodus `zwang` im bestehenden `input_select.ems_<prefix>_modus`

- Dafür: kein neuer Helfer; ein Ort für „wie wird dieses Gerät gesteuert".
- Dagegen: Die Modusachse ist Vertrag mit dem Energy Pilot (D-033, D-039) und trägt keine
  Leistung. Ein Modus kann nicht sagen, **wie viel** erzwungen wird. Ein Zwang würde außerdem
  den zuvor gewählten Modus überschreiben — nach dem Zwang wüsste niemand mehr, was vorher galt.

### Option B — Zwei eigene Helfer: `input_boolean.ems_<prefix>_force` und `input_number.ems_<prefix>_force_leistung_w`

- Dafür: additiv, optional, folgt der Namenskonvention; der Schalter lässt die Modusachse in
  Ruhe, die Leistung ist ein eigener Wert mit eigener Diagnose. Nach dem Zwang gilt genau das,
  was vorher galt.
- Dagegen: zwei Helfer mehr je Gerät; die Leistung ist auch im Ampere-Modus Watt und muss
  umgerechnet werden.

### Option C — Zwang setzt `eligible = True` und speist den Sollwert in die Zuteilung ein

- Dafür: minimaler Code, alle bestehenden Pfade laufen mit.
- Dagegen: Ein Zwangsgerät reservierte dann Schutzleistung aus dem Pool, würde in den Pool
  zurückgerechnet und könnte höher-priore Binärgeräte per Kaskade einschalten. Die Oberfläche
  zeigte „Freigabe ja" bei ausgeschalteter Bedienfreigabe — eine Lüge im Datenvertrag.

## Entscheidung

**Option B, umgesetzt als eigene Achse `force_active` neben `eligible`.**

1. **Zwang übersteuert** Bedienfreigabe (auch den EP-Vorschlag), Gerätemodus `aus`, die
   globalen Sperren (`ems_pv_regelung_aktiv`, `ems_regelmodus`, Hard-Lockout) und die
   Notabschaltung. **Zwang übersteuert nie** die technische Freigabe und nie ein kaputtes
   Schreibziel (`runtime_active: false`) — Geräteschutz schlägt Nutzerwunsch. Ein regelbares
   Gerät braucht zusätzlich eine gültige Zwangsleistung `> 0 W`; fehlt sie, ist sie ungültig
   oder `0`, bleibt das Gerät in der Normalregelung (`force_blocked_reason: keine_leistung`).
2. **`eligible` bleibt unangetastet.** Es ist weiterhin die Freigabeentscheidung für den Pool.
   `force_active: true` bei `eligible: false` ist der Normalfall eines Zwangsgeräts mit
   gesperrter Freigabe. Die Auflösung liegt in `Device.resolve_force()`, das der Controller nach
   der Schreibziel-Prüfung aufruft; ein Speicher überschreibt sie mit einem No-Op —
   `netzladen_aktiv` bleibt sein Weg.
3. **Ein Zwangsgerät ist kein Pool-Teilnehmer.** `current_w` und `max_relief_w` liefern `0`,
   `consume_from_pool` reserviert nichts, die Zuteilung setzt statt einer Pool-Menge die
   Zwangsleistung, geklemmt auf `[min_technisch_w, max_technisch_w]`. Binärgeräte werden in
   `binary_total_w` nicht abgezogen: ihre Last steckt im Residual und wird nicht zurückgerechnet
   — der Pool ist bereits um sie reduziert, ein zweiter Abzug wäre Doppelzählung.
4. **Sofort, ohne Regelgüte.** Der Zwangs-Sollwert wird ohne Hoch-/Runter-Regelzeit, ohne
   Schrittlimit und ohne Totband geschrieben und bei Defizit nicht abgeregelt. Ein binäres
   Zwangsgerät schaltet ohne Mindestauszeit ein und zählt weder gegen das One-Change-Limit noch
   in die Prioritätskaskade — auf keiner Seite. Endet der Zwang, greifen Mindestlaufzeit,
   Abschaltverzögerung und Rampe ab dann normal.
5. **Die Zwangslast ist Hausverbrauch.** `gemessene_last_w` liefert unter Zwang `0`; der
   Speicher deckt die Last. Das ist die bewusste, einzige Ausnahme von D-B14: wer ein Gerät
   erzwingt, will es laufen sehen — anders als bei einer Fremdsteuerung, die das HEMS nur
   beobachtet.
6. **Die Zwangsleistung ist immer Watt**, auch bei `output_unit: ampere` (wie `reserve_w`).
   Das HEMS wählt die Phasen zur Zwangsleistung und rundet auf ganze Ampere ab. Die
   Umschaltsperre `min_umschaltzeit_s` gilt auch unter Zwang — sie schützt Hardware.
7. **Sichtbar, nicht nur im Log.** Der Status trägt `force_requested`, `force_active`,
   `force_blocked_reason` und (regelbar) `force_w`; die Karte bekommt additiv `zwang` und für ein
   Zwangsgerät keine `inactive_reasons`. Die technische Freigabe wird bei angefordertem Zwang
   auch unter `source: "aus"` gelesen und steht dann im Status.
8. **Begriff.** Das frühere „Force-Modus" heißt in Code, Doku und Oberfläche jetzt
   **Fremdsteuerung**. `force` bezeichnet ausschließlich den Zwang.

## Folgen

- **Positiv:** Ein Gerät lässt sich ohne Umweg über fremde Automationen erzwingen; die
  Modusachse und der EP-Vertrag bleiben unberührt; die Pool-Rechnung bleibt korrekt, weil das
  Zwangsgerät sie vollständig verlässt. Unwirksamer Zwang hat immer einen benannten Grund.
- **Negativ:** Zwei optionale Helfer mehr je Gerät. Im Steuerung-Tab erscheinen sie ohne
  Anlage als „Helfer nicht gefunden". Im ersten Zyklus nach dem Einschalten ist die Zwangslast
  noch nicht im Residual — andere Geräte können einen Zyklus lang zu viel bekommen und werden
  dann per Defizit abgeregelt; derselbe Transient wie bei jeder neu auftauchenden Fremdlast.
  Ein Zwangs-Heizstab entlädt den Speicher.
- **Aufwand:** `Device.resolve_force`, Zweige in allen Pool-Methoden beider Verbraucherklassen,
  Kaskade/One-Change/`binary_total_w` im Controller, Flow-Publisher, Steuerungs-Schema,
  Statustypen und Karte in der Oberfläche, Doku in `device_classes/`, `datenmodell.md`,
  `architektur.md`, `api-referenz.md`, `test-strategie.md`; Umbenennung des alten Begriffs.

## Rücknahmebedingung

- Nutzer wollen einen Zwang, den der Speicher **nicht** deckt (z. B. Heizstab nur aus Netz,
  Speicher fürs Haus sparen). Dann kommt ein dritter Helfer `ems_<prefix>_force_aus_speicher`
  oder die Deckung wird konfigurierbar — Punkt 5 dieser Entscheidung fällt.
- Der Transient aus „Negativ" stört in der Praxis (sichtbares Pendeln anderer Geräte nach dem
  Einschalten eines Zwangs). Dann muss `binary_total_w` bzw. die Pool-Rechnung die Zwangslast im
  ersten Zyklus vorwegnehmen — Punkt 3 wird um eine Vorhalte-Regel ergänzt.
- Ein Speicher soll doch einen Zwang kennen. Dann ist `netzladen_aktiv` zu vereinheitlichen,
  nicht ein zweiter Zwangspfad zu bauen.
