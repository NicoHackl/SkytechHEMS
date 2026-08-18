# Bekannte Lücken und Stolpersteine

**Vor jeder Annahme lesen.** Diese Datei existiert, weil Doku und Code auseinanderlaufen. Steht
etwas in [architektur.md](architektur.md), heißt das nicht, dass es implementiert ist — hier steht,
wo nicht.

Stand: 13.08.2026.

## Abweichungen Spec ↔ Code

| Thema | Doku sagt | Code macht | Folge für die Arbeit |
|---|---|---|---|
| Sprache der Bezeichner | Eiserne Regel 2 verlangt englische Namen | HA-Helfer und die davon abgeleiteten Statusfelder sind deutsch | Bewusst so, D-034. Neuer Code ist englisch; bestehende Felder werden erweitert, nie umbenannt |

## Stolpersteine

Dinge, die schon einmal Zeit gekostet haben:

- **`schutz_w` ist nicht die geschützte Mindestleistung.** `schutz_w` ist der effektive Schutz
  (`Sockel + reserve_w + globaler Puffer`, geklemmt). Der Energy Pilot verglich anfangs dagegen und
  zeigte 900 W statt der eingetragenen 600 W. Der rohe Nutzerwert steht in
  `geschuetzte_mindestleistung_w` bzw. `_a`.
- **Semantik des Überschuss-Sensors.** Der Sensor muss den Netz-Überschuss liefern, in dem die
  EMS-Lasten noch enthalten sind. Liefert er den bereits bereinigten freien Überschuss, kommt es zu
  Doppelzählung und Aufschwingen — siehe [konfiguration.md](konfiguration.md).
- **Verwaiste EP-Vorschläge.** Wird im Energy Pilot ein Quellsensor getauscht, bleibt die alte
  `sensor.ep_*`-Entität mit eingefrorenem Wert in HA stehen. Die Oberfläche filtert doppelt
  (abgelaufen; je Feld nur der frischere) — wer diese Filter entfernt, holt die Altwerte zurück.
- **Interne Timer überleben keinen Neustart.** `_off_since_ts` und die Rampen-Zeitstempel liegen im
  Speicher. Nach einem Add-on-Neustart beginnt der Zeitschutz von vorn.
- **Ampere-Modus rechnet intern in Watt.** Nur beim Schreiben wird abgerundet. Wer Ampere-Werte
  vergleicht, muss `new_a` bzw. `schutz_a` nehmen, nicht die Watt-Felder durch die Spannung teilen.
- **Add-on-Optionen erscheinen als YAML-Editor.** Weil das Schema eine Objektliste enthält, zeigt
  Home Assistant die Feldbeschreibungen aus `translations/` nicht an. Maßgeblich ist
  [konfiguration.md](konfiguration.md).

## Offene Bugs

| ID | Beschreibung | Auswirkung | Umgehung |
|---|---|---|---|
| B-1 | Im Ampere-Modus rechnen Deadband und Schreib-Guard in [`app/ems/devices.py`](../app/ems/devices.py) (`get_write_ops`) in **Watt**, geschrieben werden aber abgerundete Ampere. Eine Watt-Änderung unter 1 A ergibt denselben Ampere-Wert und löst trotzdem einen Schreibvorgang aus | Der identische Wert wird erneut geschrieben, `last_changed` springt und stört das Rampen-Timing. Nur bei `output_unit=ampere`, vor allem bei `min_anderung_pro_schritt_a = 0` | `min_anderung_pro_schritt_a` > 0 setzen. Fix: Ziel- gegen Ist-**Ampere** vergleichen und das Totband ebenfalls in Ampere prüfen |
| B-2 | Fehlgeschlagene Write-Ops werden in [`app/ha_client.py`](../app/ha_client.py) (`execute_write_ops`) nur geloggt, nicht geworfen. Der Zyklus gilt danach als erfolgreich (`error: ""`) | Ein vertippter Helfername schlägt jeden Zyklus still fehl; in der Oberfläche ist nichts zu sehen | Add-on-Log prüfen. Fix: fehlgeschlagene Ops zählen und in `/api/status` sichtbar machen |
| B-3 | `POST /api/set` schränkt die Ziel-Entität innerhalb der erlaubten Domains nicht auf `ems_*` ein | Wer den Endpunkt direkt aufruft, kann jeden `input_*`-Helfer setzen. Hinter dem Ingress authentifiziert, deshalb bewusst belassen | — |

## Offene Fachfragen der AC-Speicher-Erweiterung

Aus [`erweiterungen/erweiterung_ac_speicher_1_antworten.md`](../erweiterungen/erweiterung_ac_speicher_1_antworten.md).
Sie blockieren keine Planung, wohl aber die Inbetriebnahme des Schreibpfads:

| # | Frage | Blockiert |
|---|---|---|
| F-2 | Wechselrichter-Anbindung: Register bzw. Services, Reihenfolge Modus ↔ Leistung, Übernahmezeit | Phase 2 und 3 der Erweiterung |
| F-11 | Wie wird die Shelly-Nulleinspeisung an- und abgeschaltet (API, MQTT, Schalter)? Ist sie nicht abschaltbar, regeln HEMS und Shelly gegeneinander | Phase 3, Watchdog-Ebene 3 |
| F-12 | Quelle von `residual_power_entity` — dieselbe wie beim Batterie-Leistungssensor? Bestimmt den Sensor-Versatz | Dimensionierung von `hoch_regelzeit_s` |

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
