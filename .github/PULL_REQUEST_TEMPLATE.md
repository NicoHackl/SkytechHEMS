## Was ändert sich

<Kurz aus Nutzersicht: was kann man danach, was vorher nicht ging.>

## Warum

<Problem oder Anlass. Bei einer Grundsatzentscheidung zusätzlich D-xxx verlinken.>

## Checkliste

- [ ] `ruff check app tests` läuft fehlerfrei
- [ ] `pytest -q` läuft fehlerfrei
- [ ] Bei Änderungen an `web/`: `cd web && npm run build` ausgeführt und das
      erzeugte Bündel in `app/static/` mitcommittet (D-035)
- [ ] Bei Änderungen an der Oberfläche: beide Modi (hell und dunkel) angesehen
      und bei 375 px Breite bedienbar
- [ ] [CHANGELOG.md](../CHANGELOG.md) ergänzt
- [ ] Betroffene Dateien in [docs/](../docs/) aktualisiert
- [ ] Keine Secrets im Diff (`git diff --staged` geprüft)
- [ ] Neue Grundsatzentscheidung? → Eintrag in
      [docs/design-entscheidungen.md](../docs/design-entscheidungen.md)
