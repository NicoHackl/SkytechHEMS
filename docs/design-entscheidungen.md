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
| D-038 | 13.08.2026 | Die Referenz-`styles.css` wird um einen HEMS-Block erweitert (`.device-grid`, `.device-card`, `.kv-row`, `.ctrl-row`, `.pill-row`, `.section-title`), und die Schalter-Checkbox liegt unsichtbar über dem Track statt auf `display: none` | Aktiv | Für Kennzahlzeilen und das Geräteraster gibt es im Katalog keine Entsprechung, und jede neue Klasse wird von mindestens zwei Seiten benutzt. Die Schalter-Änderung ist eine Korrektur: `display: none` nimmt die Checkbox aus der Tab-Reihenfolge, was der Barrierefreiheits-Abschnitt in [design-system.md](design-system.md) ausschließt. |
| D-037 | 13.08.2026 | Für Menschen lesbare Zeitangaben liefert `/api/status` **zusätzlich** als `last_cycle_at` (`TT.MM.JJJJ hh:mm:ss`, Berliner Zeit); das Maschinenformat bleibt in `last_cycle_at_iso` und `status.timestamp` erhalten | Aktiv | Regel 9 verlangt das deutsche Format in der Anzeige, D-034 verbietet das Brechen bestehender Verbraucher. Die Alternative „Format an Ort und Stelle ändern" wurde verworfen, weil der Energy Pilot `last_cycle_at` spiegelt. Additiv erfüllt beides. |
| D-039 | 18.08.2026 | HEMS veröffentlicht einen additiven, semantischen Gerätevertrag und akzeptiert EP-Vorschläge nur über einen passenden, noch gültigen `sensor.ep_plan_commit` | Aktiv | HEMS bleibt autoritative Quelle für Geräte, Userwerte und Grenzen. Stabile Schlüssel/Rollen verhindern Suffix-Raten und das Integrieren technischer Grenzwerte als Verbrauch. Der Commit-Marker verhindert gemischte Teilpläne; bei jedem Fehler greift feldweise der Nutzerwert. Die Modusachse bleibt unverändert. Ausführlich: [adr/D-039-energy-pilot-planvertrag.md](adr/D-039-energy-pilot-planvertrag.md). |
| D-040 | 20.08.2026 | AC-gekoppelte Speicher als eigene Geräteklasse `BatteryDevice`: der Pool wird um die gemessene Entladung bereinigt, die negative Hälfte des Pools wird als `hausdefizit_w` zum Entladeziel, Laden und Entladen haben getrennte Prioritäten, und die Ausgabe ist ein signierter Sollwert plus Betriebsart | Aktiv, in Teilen ersetzt durch D-041 | Ein Speicher ist der erste Teilnehmer, der den Messwert verfälscht, auf dem das HEMS aufbaut. Die Alternative „Speicher regelt selbst" wurde verworfen: zwei autonome Regler am selben Netzpunkt haben kein eindeutiges Gleichgewicht. Ohne konfigurierten Speicher bleibt das Verhalten bit-identisch. Ausführlich: [adr/D-040-ac-speicher.md](adr/D-040-ac-speicher.md). **Geändert durch D-041:** SoC-Taper, Notstromreserve, konfigurierte Maximalleistungen und die Entlade-Sofort-Schwelle sind entfallen; die physische Grenze kommt nur noch aus den beiden `available_*`-Sensoren. Pool-Bereinigung, `hausdefizit_w`, die getrennten Prioritäten und der signierte Sollwert gelten unverändert. |
| D-041 | 21.08.2026 | Die physische Grenze eines AC-Speichers kommt allein aus `available_charge_power_entity` und `available_discharge_power_entity`; beide sind Pflicht und werden getrennt ausgewertet. SoC-Taper, Notstromreserve, konfigurierte Maximalleistungen, Entlade-Sofort-Schwelle und die EP-Maximalvorschläge entfallen ersatzlos | Aktiv | Sieben Mechanismen begrenzten dieselbe Größe, und mehrere regelten gegen den Wechselrichter, der seine CV-Phase und sein Derating selbst fährt. Die Alternative „alles behalten, Vorrang genauer dokumentieren" wurde verworfen: sie hätte die Doppelregelung und sieben Sperrgründe belassen. Ein gültiger Wert `0` ist dabei eine bewusste Sperre, kein Fehler. Ausführlich: [adr/D-041-speichervertrag-vereinfacht.md](adr/D-041-speichervertrag-vereinfacht.md). |
| D-042 | 21.08.2026 | Die Add-on-Optionen werden über die Supervisor-API (`addons/self/options`) verwaltet; `/data/options.json` wird nur gelesen. Schutz gegen Paralleländerung über einen Revisions-Hash der rohen Optionen, Speichern und Neustarten bleiben getrennt | Aktiv | Es gibt keine zweite Konfigurationsquelle und keine eigene Persistenz. Die Alternative „eigene Datei unter /data/" wurde verworfen, weil dann zwei Quellen existierten und die Startreihenfolge entschiede; „options.json direkt beschreiben" wurde verworfen, weil der Supervisor die Datei besitzt und beim nächsten Optionswechsel überschreibt. Ausführlich: [adr/D-042-supervisor-konfigurationsseite.md](adr/D-042-supervisor-konfigurationsseite.md). |
