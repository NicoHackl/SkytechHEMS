# Bekannte Lücken und Stolpersteine

**Vor jeder Annahme lesen.** Diese Datei existiert, weil Doku und Code auseinanderlaufen. Steht
etwas in [architektur.md](architektur.md), heißt das nicht, dass es implementiert ist — hier steht,
wo nicht.

Stand: 21.08.2026.

## Abweichungen Spec ↔ Code

| Thema | Doku sagt | Code macht | Folge für die Arbeit |
|---|---|---|---|
| Sprache der Bezeichner | Eiserne Regel 2 verlangt englische Namen | HA-Helfer und die davon abgeleiteten Statusfelder sind deutsch | Bewusst so, D-034. Neuer Code ist englisch; bestehende Felder werden erweitert, nie umbenannt |

## Stolpersteine

Dinge, die schon einmal Zeit gekostet haben:

- **`entity_diagnostics[…]["state"]` ist der Auflösungszustand, nicht der HA-State.** Dort steht
  `valid`, `missing`, `invalid` oder `unavailable` — nie `on`/`off` und nie der Zahlenwert
  (`app/ems/devices.py`, `_note()`). Wer ihn mit einem HA-State vergleicht, bekommt eine Bedingung,
  die immer zutrifft. Genau daran sind die Freigabegründe der Power Flow Card gescheitert: sie
  meldeten jedem gesperrten Gerät „Technische Freigabe aus", gleich wie die Schalter standen. Wird
  ein *Wert* gebraucht, muss ihn das Gerät ausdrücklich in `to_status_dict()` legen — siehe
  `freigabe_status()`.
- **Von Hand gebaute Statuseinträge in Tests prüfen nichts.** Derselbe Fehler stand in
  `tests/test_flow_publisher.py` als bestätigende Vorlage (`"state": "on"`), eine Form, die
  `to_status_dict()` nie erzeugt. Für alles, was am Statuswörterbuch hängt, gehört mindestens ein
  Test über einen echten `EMSController.run_cycle()` dazu.
- **`schutz_w` ist nicht die geschützte Mindestleistung.** `schutz_w` ist der effektive Schutz
  (`Sockel + reserve_w + globaler Puffer`, geklemmt). Der Energy Pilot verglich anfangs dagegen und
  zeigte 900 W statt der eingetragenen 600 W. Der rohe Nutzerwert steht in
  `geschuetzte_mindestleistung_w` bzw. `_a`.
- **Semantik des Überschuss-Sensors.** Der Sensor muss den Netz-Überschuss liefern, in dem die
  EMS-Lasten noch enthalten sind. Liefert er den bereits bereinigten freien Überschuss, kommt es zu
  Doppelzählung und Aufschwingen — siehe [konfiguration.md](konfiguration.md).
- **Hausleistungsbilanz ist ein zweiter Vertrag.** `battery_residual_power_entity` ersetzt den
  Überschuss-Sensor nicht: negativ bedeutet Unterdeckung, positiv Einspeisung und die Bilanz
  enthält Netz- plus E3DC-Batterieleistung. Sie steuert nur die AC-Entladung. Fehlt ihr Wert,
  gehen die AC-Speicher auf `standby`; Verbraucher laufen über `residual_power_entity` weiter.
  Formel und die drei `700-W`-Kontrollfälle stehen in
  [konfiguration.md](konfiguration.md#hausleistungsbilanz-für-ac-speicher).
- **Verwaiste EP-Vorschläge.** Wird im Energy Pilot ein Quellsensor getauscht, bleibt die alte
  `sensor.ep_*`-Entität mit eingefrorenem Wert in HA stehen. Die Oberfläche filtert doppelt
  (abgelaufen; je Feld nur der frischere) — wer diese Filter entfernt, holt die Altwerte zurück.
- **Interne Timer überleben keinen Neustart.** `_off_since_ts` und die Rampen-Zeitstempel liegen im
  Speicher. Nach einem Add-on-Neustart beginnt der Zeitschutz von vorn.
- **Ampere-Modus rechnet intern in Watt.** Nur beim Schreiben wird abgerundet. Wer Ampere-Werte
  vergleicht, muss `new_a` bzw. `schutz_a` nehmen, nicht die Watt-Felder durch die Spannung teilen.
- **Der Namensraum `ems_speicher_*` gehört nicht dem HEMS.** In dieser Anlage regelt eine eigene
  HA-Automation den vorhandenen E3DC über `input_number.ems_speicher_mindesladeleistung_1/2`,
  `ems_speicher_soc_mindestwert_1/2` und `input_boolean.ems_speicher_regelung_stufe_1_aktiv`. Der
  AC-Speicher des HEMS benutzt deshalb `acspeicher1` als Präfix, sein globaler Helfer heißt
  `input_number.ems_ac_speicher_entlade_abschlag_w`. Der E3DC ist **kein** HEMS-Gerät: er regelt
  sich selbst, ist aber bewusst in der Hausleistungsbilanz für die AC-Entladung enthalten.
- **Der Sollwert des Speichers ist signiert.** `input_number.ems_<prefix>_anforderung_leistung_w`
  trägt „+ laden / − entladen" in einer Entität. Der HA-Helfer braucht ein **negatives Minimum** —
  steht dort `min: 0`, klemmt Home Assistant jede Entladeanforderung serverseitig auf 0 und der
  Speicher entlädt nie.
- **Add-on-Optionen erscheinen als YAML-Editor.** Weil das Schema eine Objektliste enthält, zeigt
  Home Assistant die Feldbeschreibungen aus `translations/` nicht an. Bequemer ist der Bereich
  **Konfiguration** im Ingress-Panel; er schreibt dieselbe Quelle (D-042). Maßgeblich bleibt
  [konfiguration.md](konfiguration.md).
- **Das Manifest-Schema kann Pflichtfelder je Geräteklasse nicht ausdrücken.** Eine gemischte
  Objektliste kennt keine bedingten Pflichtfelder, und eine Pflichtmarkierung für `switch_entity`
  machte jedes `controllable`-Gerät ungültig. Alle klassenspezifischen Felder stehen deshalb als
  `?` im Schema — autoritativ validiert [`app/configuration.py`](../app/configuration.py). Wer die
  Pflichtangaben sucht, findet sie in [device_classes/](device_classes/global.md), nicht in
  `config.yaml`.
- **Neue Pflichtfelder machen Bestandsgeräte inaktiv.** Nach dem Update auf den Entitäts-Fallback-
  Vertrag laufen `controllable`- und `binary`-Geräte ohne ihre neuen Add-on-Felder nicht mehr an,
  ebenso ein Speicher ohne die beiden `available_*_w`-Werte. Sie verschwinden nicht, sondern
  stehen mit ihren Feldfehlern unter `inactive_devices`. Die Migrationsschritte stehen im
  [CHANGELOG.md](../CHANGELOG.md).
- **Ein Schreibziel hat keinen Fallback.** Fehlt der `anforderung_*`-Helfer, hat er die falsche
  Domain, fehlen dem Betriebsart-Helfer Optionen oder erlaubt der Speicher-Sollwert keinen
  negativen Wert, ist **nur dieses** Gerät `runtime_active: false`. Es schreibt weiter seinen
  sicheren Zustand — der Grund steht in `inactive_reasons`, nicht nur im Log.

## Offene Bugs

| ID | Beschreibung | Auswirkung | Umgehung |
|---|---|---|---|
| B-1 | Im Ampere-Modus rechnen Deadband und Schreib-Guard in [`app/ems/devices.py`](../app/ems/devices.py) (`get_write_ops`) in **Watt**, geschrieben werden aber abgerundete Ampere. Eine Watt-Änderung unter 1 A ergibt denselben Ampere-Wert und löst trotzdem einen Schreibvorgang aus | Der identische Wert wird erneut geschrieben, `last_changed` springt und stört das Rampen-Timing. Nur bei `output_unit=ampere`, vor allem bei `min_anderung_pro_schritt_a = 0` | `min_anderung_pro_schritt_a` > 0 setzen. Fix: Ziel- gegen Ist-**Ampere** vergleichen und das Totband ebenfalls in Ampere prüfen |
| B-3 | `POST /api/set` schränkt die Ziel-Entität innerhalb der erlaubten Domains nicht auf `ems_*` ein | Wer den Endpunkt direkt aufruft, kann jeden `input_*`-Helfer setzen. Hinter dem Ingress authentifiziert, deshalb bewusst belassen | — |
| B-4 | Die reservierten Helfer `input_boolean.ems_<prefix>_netzladen_aktiv` und `input_number.ems_<prefix>_netzlade_leistung_w` werden bereits ausgeführt, obwohl Netzladen zurückgestellt ist. `netzlade_soc_ziel_prozent` wird dagegen nicht gelesen; SoC-Ziel, Preislogik und vollständige Sicherheitsbegrenzung fehlen | Ein versehentliches `netzladen_aktiv: on` kann einen AC-Speicher unkontrolliert aus dem Netz laden | Beide Helfer nicht anlegen oder auf `off` und `0 W` halten. Vor Freigabe des Netzladens den Pfad hart sperren oder Phase 6 vollständig implementieren und testen |

## Offene Fachfragen der AC-Speicher-Erweiterung

Aus [`erweiterungen/erweiterung_ac_speicher_1_antworten_2.md`](../erweiterungen/erweiterung_ac_speicher_1_antworten_2.md).
Der Code ist gebaut und getestet; diese Fragen betreffen die **Inbetriebnahme am realen Gerät**:

| # | Frage | Blockiert |
|---|---|---|
| F-13 | Welches Gerät wird der AC-Speicher? Liefert `soc_entity`, die Ist-Leistungssensoren und `capacity_kwh`; welche festen Lade-/Entladegrenzen werden als `available_*_w` eingetragen? | Inbetriebnahme, nicht den Code |
| F-14 | Bringt das Gerät eine eigene Nulleinspeisung mit, und lässt sie sich abschalten? Nicht abschaltbar heißt: HEMS und Gerät regeln gegeneinander | Inbetriebnahme |

## Bewusst nicht umgesetzt

| Thema | Warum nicht | Verweis |
|---|---|---|
| Englische Umbenennung der HA-Helfer und Statusfelder | Bräche jede bestehende Anlage und den Energy Pilot | D-034 |
| Node-Build im Add-on-Image | Schneidet `i386` und `armhf` von Updates ab und macht die Installation auf schwacher Hardware minutenlang | D-035 |
| `BrowserRouter` und absolute API-Pfade | Der Ingress-Pfad steht zur Bauzeit nicht fest | D-036 |
| Automatisierte Frontend-Tests | Die Seiten enthalten keine Fachlogik; abgesichert über `tsc --noEmit` und die Sichtprüfung | [test-strategie.md](test-strategie.md) |
| Zeitschutz bei Notabschaltung aushebeln | Geräteschutz schlägt Regelgüte — Mindestlaufzeit und Abschaltverzögerung gelten immer | [architektur.md](architektur.md), Invarianten |

---

Wird ein Punkt behoben, wird er hier **gelöscht** und im [CHANGELOG.md](../CHANGELOG.md) vermerkt.
Eine Liste voller erledigter Einträge liest niemand mehr.
