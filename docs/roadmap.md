# Roadmap

Meilensteine und **ehrlicher** Umsetzungsstand. Der Status wird gegen den tatsächlichen Code
geprüft, nicht gegen die Absicht. Was hier „fertig" heißt, muss laufen.

## Status-Werte

`offen` · `in Arbeit` · `fertig` · `zurückgestellt`

## Meilensteine

### M1 — Regelbetrieb

**Ziel:** PV-Überschuss wird zyklisch und prioritätsbasiert auf regelbare und binäre Verbraucher
verteilt.

| Punkt | Status | Verweis |
|---|---|---|
| Pool-Verteilung nach Priorität, Kaskade, One-Change-Limit | fertig | [architektur.md](architektur.md) |
| Zeitschutz binärer Geräte (Mindestlauf-/Auszeit, Abschaltverzögerung) | fertig | [datenmodell.md](datenmodell.md) |
| Rampenbegrenzung und Totband regelbarer Geräte | fertig | |
| Ampere-Ausgabe und automatische Phasenumschaltung | fertig | |
| Hard-Lockout bei ungültigem Überschuss-Sensor | fertig | |
| Konfigurationsgetriebene Geräteliste ohne Codeänderung | fertig | [konfiguration.md](konfiguration.md) |

### M2 — Energy-Pilot-Anbindung

**Ziel:** Die KI-Vorschläge des Energy Pilot wirken auf die Regelung, ohne dass ein Ausfall die
Anlage blockiert.

| Punkt | Status | Verweis |
|---|---|---|
| Übernahme von Priorität, Freigabe und geschützter Mindestleistung je Regelmodus | fertig | D-033 |
| Anzeige der Vorschläge und des Plan-Status in der Oberfläche | fertig | [frontend.md](frontend.md) |
| Ausblenden verwaister Vorschläge | fertig | [datenmodell.md](datenmodell.md) |

### M3 — Projektstandards

**Ziel:** Das Repository erfüllt die eisernen Regeln aus [`AGENTS.md`](../AGENTS.md).

| Punkt | Status | Verweis |
|---|---|---|
| Regelwerk, `docs/`, Changelog- und Doku-Pflicht | fertig | [README.md](README.md) |
| Add-on-Optionen aus dem Ingress-Panel pflegbar | fertig | D-042, [api-referenz.md](api-referenz.md) |
| Diagnostizierbare Entitäts-Fallbacks (Ursache und Quelle je Wert) | fertig | [device_classes/global.md](device_classes/global.md) |
| Schreibziel-Prüfung und Write-Fehler je Gerät | fertig | [architektur.md](architektur.md) |
| Oberfläche als React + TypeScript + Vite mit Design-System | fertig | D-035, D-036 |
| Hell/Dunkel-Schalter mit gespeicherter Wahl | fertig | [design-system.md](design-system.md) |
| Frontend-Build und Drift-Check in der CI | fertig | [git-workflow.md](git-workflow.md) |

### M4 — AC-gekoppelte Speicher (1…n)

**Ziel:** Speicher werden vom HEMS geladen und entladen — Laden aus PV-Überschuss, Entladen zur
Deckung des Hausverbrauchs. Entwurf v5:
[`erweiterungen/erweiterung_ac_speicher_1.md`](../erweiterungen/erweiterung_ac_speicher_1.md).

| Punkt | Status | Verweis |
|---|---|---|
| Phase 1 — Pool-Bereinigung, `hausdefizit_w`, Anzeige | fertig | D-040 |
| Phase 2 — Ladepfad mit SoC-Grenzen und konfiguriertem Leistungslimit | fertig | D-040, D-041, D-043 |
| Phase 3 — Entladepfad, Rampe, sicherer Zustand | fertig | D-040, D-041 |
| Phase 4 — Mehrspeicher, getrennte Lade-/Entladepriorität | fertig | D-040 |
| Phase 5 — Energy-Pilot-Vorschlagsfelder für Speicher | offen | Entwurf, Abschnitt 13 |
| Phase 6 — Netzladen mit dynamischen Tarifen | zurückgestellt | Entwurf, Abschnitt 11; B-4 |
| Inbetriebnahme am realen Gerät | offen | F-12, F-13, F-14 |

Der Code läuft gegen Tests und einen synthetischen HA-Zustand. **Erprobt am Gerät ist er nicht** —
es gibt noch keinen AC-Speicher. Seit D-043 sind die physischen Grenzen die direkt konfigurierten
Wattwerte `available_charge_power_w` und `available_discharge_power_w`. Die verbliebenen Fragen stehen in
[bekannte-luecken.md](bekannte-luecken.md).

Der vorhandene E3DC ist bewusst **kein** HEMS-Gerät: er regelt sich selbst und steckt im
Überschuss-Sensor bereits drin (D-040).

## Zurückgestellt

| Thema | Warum zurückgestellt | Bedingung für Wiederaufnahme |
|---|---|---|
| Netzladen mit dynamischen Tarifen | Erst sinnvoll, wenn ein Speicher real läuft. Die reservierten Helfer werden teilweise ausgeführt, aber SoC-Ziel, Preislogik und vollständige Sicherheitsbegrenzung fehlen; bis zur Behebung von B-4 müssen sie `off` beziehungsweise `0 W` bleiben | M4 am Gerät in Betrieb und B-4 behoben |

---

Beschlossen, aber noch nicht gebaut → hier mit Status `offen`.
Gebaut, aber abweichend von der Doku → [bekannte-luecken.md](bekannte-luecken.md).
Warum so entschieden → [design-entscheidungen.md](design-entscheidungen.md).
