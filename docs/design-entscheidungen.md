# Design-Entscheidungen

**Quelle der Wahrheit fürs „warum".** Wer wissen will, weshalb etwas so gebaut ist, schaut hier —
und ändert es nicht, ohne die Entscheidung hier zu widerrufen.

## Wann ein Eintrag entsteht

Immer, wenn eine Festlegung getroffen wird, die später jemand hinterfragen könnte:
Technologiewahl, Datenformat, Namensschema, Zuständigkeitsgrenze, bewusst nicht Gebautes,
neue Laufzeit-Abhängigkeit.

**Nicht** eingetragen werden reine Umsetzungsdetails, die der Code selbst zeigt.

## Ablauf

1. Nächste freie `D-xxx` vergeben (fortlaufend, nie wiederverwenden).
2. Zeile in die Tabelle unten eintragen.
3. Bei tragweiter Entscheidung zusätzlich ein ADR anlegen:
   `docs/adr/D-xxx-kurzname.md` auf Basis von [adr/0000-vorlage.md](adr/0000-vorlage.md), und aus
   der Tabelle darauf verlinken.
4. Wird eine Entscheidung später gekippt: alte Zeile auf Status **Ersetzt** setzen und auf die neue
   `D-yyy` verweisen. **Zeilen werden nie gelöscht** — sonst geht die Begründung verloren, warum
   der frühere Weg verworfen wurde.

## Status-Werte

| Status | Bedeutung |
|---|---|
| Aktiv | Gilt und ist umgesetzt |
| Geplant | Beschlossen, aber noch nicht im Code — siehe [roadmap.md](roadmap.md) |
| Ersetzt | Durch eine spätere Entscheidung abgelöst, Verweis in der Begründung |
| Verworfen | Bewusst nicht umgesetzt, Begründung bleibt als Warnung stehen |

## Log

Die Nummern **D-001 bis D-003** stammen aus der Projektvorlage und gelten für jedes Projekt. Die
im [CHANGELOG.md](../CHANGELOG.md) referenzierte **D-033** wurde vor dem Anlegen dieses Logs
vergeben; um keine Nummer doppelt zu belegen, führen neue Einträge den Nummernkreis ab **D-034**
fort.

| ID | Datum | Entscheidung | Status | Begründung / Verweis |
|---|---|---|---|---|
| D-001 | 13.08.2026 | Regeln für KI-Agenten liegen in `AGENTS.md`; `CLAUDE.md`, `GEMINI.md`, `copilot-instructions.md` und `.cursor/rules/` sind reine Verweise darauf | Aktiv | Jede Regel existiert genau einmal. Alternative „je Tool eine eigene Datei" wurde verworfen, weil die Kopien erfahrungsgemäß auseinanderlaufen. |
| D-002 | 13.08.2026 | Datum immer `TT.MM.JJJJ`, Uhrzeit immer Berliner Zeit als `hh:mm` bzw. `hh:mm:ss`, ohne Offset oder Zonenkürzel (eiserne Regel 9 in [`AGENTS.md`](../AGENTS.md)) | Aktiv | Einheitliche Lesart in Doku, Changelog, Logs und UI. Alternative „ISO 8601 mit Offset überall" wurde verworfen: technisch korrekt, für die deutschsprachige Zielgruppe aber unlesbar. Maschinenformate bleiben davon ausgenommen. |
| D-003 | 13.08.2026 | Designsprachen über `data-design` (`ha` = Home Assistant mit `#18BCF2`, `fcr` = FC Ruderting), ohne Default und mit grauem Akzent als sichtbarem „nicht entschieden"; Hell/Dunkel über `data-theme` in jeder Sprache Pflicht (eiserne Regeln 10 und 11 in [`../AGENTS.md`](../AGENTS.md)) | Aktiv | Ein Vokabular, mehrere Akzentsätze. Alternative „je Designsprache eine eigene styles.css" wurde verworfen, weil dann jede Klassenänderung doppelt gepflegt werden müsste. Ein stiller Default wurde ebenfalls verworfen: er hätte fremde Projekte in den Farben eines anderen erscheinen lassen, statt die offene Entscheidung zu zeigen. |
| D-033 | 07.07.2026 | Steuermodus-abhängige Übernahme der Energy-Pilot-Vorschläge: `auto` = KI, `manuell` = normale Regeln, `aus` = aus — global und je Gerät | Aktiv | Vor diesem Log vergeben, siehe [CHANGELOG.md](../CHANGELOG.md). Die technische Freigabe bleibt in jedem Modus hartes Gate; fehlt ein Vorschlag, greift der Nutzerwert, damit ein KI-Ausfall die Anlage nie blockiert. Details: [datenmodell.md](datenmodell.md). |
| D-034 | 13.08.2026 | Deutsche Bezeichner in HA-Helfer-Entitäten und in den davon abgeleiteten Feldern von `/api/status` bleiben unverändert (`prioritat`, `anforderung_current_w`, `schutz_w`, `geschuetzte_mindestleistung_w`) | Aktiv | Sie sind Datenvertrag zu jeder bestehenden Anlage und zum Energy Pilot. Die Alternative „englisch umbenennen, wie es Regel 2 verlangt" wurde verworfen: sie hätte jede installierte Anlage stillgelegt, bis der User sämtliche Helfer neu anlegt. Erweitert wird additiv, umbenannt wird nicht. Neuer Code ist englisch. |
| D-035 | 13.08.2026 | Das gebaute SPA-Bundle liegt eingecheckt unter `app/static/`; die CI baut neu und bricht bei Abweichung ab | Aktiv | Ein HA-Add-on wird auf dem HA-Host gebaut, wo für `i386` und `armhf` kein Node.js-Image existiert und ein Build auf einem Raspberry Pi Minuten dauert. Ausführlich: [adr/D-035-spa-bundle-eingecheckt.md](adr/D-035-spa-bundle-eingecheckt.md). |
| D-036 | 13.08.2026 | Unter HA-Ingress: `base: './'`, API-Pfade ohne führenden Slash, `HashRouter` statt `BrowserRouter` | Aktiv | Der Ingress-Pfad entsteht erst zur Laufzeit. Ausführlich: [adr/D-036-ingress-routing.md](adr/D-036-ingress-routing.md). |
| D-037 | 13.08.2026 | Für Menschen lesbare Zeitangaben liefert `/api/status` **zusätzlich** als `last_cycle_at` (`TT.MM.JJJJ hh:mm:ss`, Berliner Zeit); das Maschinenformat bleibt in `last_cycle_at_iso` und `status.timestamp` erhalten | Aktiv | Regel 9 verlangt das deutsche Format in der Anzeige, D-034 verbietet das Brechen bestehender Verbraucher. Die Alternative „Format an Ort und Stelle ändern" wurde verworfen, weil der Energy Pilot `last_cycle_at` spiegelt. Additiv erfüllt beides. |
