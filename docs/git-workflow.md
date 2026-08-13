# Git-Workflow

> Die Grundregel — Commit und Push ausschließlich im Branch `claude/main` — steht in
> [`AGENTS.md`](../AGENTS.md). Hier steht der ausführliche Ablauf.

## Branch-Modell

| Branch | Zweck |
|---|---|
| `main` | Stabiler Stand. **Kein direkter Commit.** |
| `claude/main` | Arbeitsbranch für KI-Agenten und laufende Entwicklung |
| `feature/<kurzname>` | Optional für größere, klar abgegrenzte Vorhaben |

Der Merge nach `main` erfolgt **manuell auf Zuruf**, nie automatisch durch einen Agenten.

## Commit-Format

[Conventional Commits](https://www.conventionalcommits.org/), Betreffzeile deutsch, max. 72 Zeichen:

```text
<typ>(<bereich>): <was sich ändert, Imperativ>

<optionaler Rumpf: warum, nicht was>
```

Typen: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `build`, `ci`.

```text
feat(planer): Vorschlagswerte je Gerät berechnen
fix(api): Zeitzone bei Tageswechsel korrigiert
docs(architektur): Datenfluss aktualisiert
```

Der Rumpf ist nur nötig, wenn das „warum" nicht aus der Betreffzeile hervorgeht.

## Ablauf je Arbeitspaket

1. Aktuellen Stand holen: `git pull --rebase`
2. Ändern, Tests (`pytest -q`) und Linting (`ruff check app tests`) grün bekommen
3. Wurde an `web/` gearbeitet: `cd web && npm run build` — das erzeugte Bundle in `app/static/`
   gehört **in denselben Commit** (D-035). Die CI bricht sonst mit einem Drift-Fehler ab.
4. [CHANGELOG.md](../CHANGELOG.md) ergänzen
5. Betroffene `docs/`-Dateien aktualisieren
6. `git add` gezielt — **nie** `git add -A` ohne vorherige Prüfung von `git status`
7. Committen und pushen auf `claude/main`

Ein Commit bildet **eine** abgeschlossene Änderung ab. Sammelcommits über mehrere unabhängige
Themen sind nicht zulässig — sie machen ein späteres `git revert` unmöglich.

## Versionierung

[Semantic Versioning](https://semver.org/lang/de/): `MAJOR.MINOR.PATCH`

| Teil | Wann erhöhen |
|---|---|
| `PATCH` | Fehlerbehebung, keine Schnittstellenänderung |
| `MINOR` | Neue Funktion, abwärtskompatibel |
| `MAJOR` | Bricht bestehende Schnittstellen oder Datenformate |

Versionsstand wird gepflegt in: `config.yaml` (Feld `version`). Home Assistant erkennt ein Update
des Add-ons ausschließlich an diesem Feld.

**Die Patch-Stelle hebt der Workflow [`bump-version.yaml`](../.github/workflows/bump-version.yaml)
bei jedem Push auf `main` automatisch an** — sie wird nicht von Hand gepflegt. Von Hand angehoben
werden nur `MINOR` und `MAJOR`.

## Release

1. Bei neuer Funktion oder brechender Änderung: `MINOR` bzw. `MAJOR` in `config.yaml` anheben
2. `CHANGELOG.md`: Abschnitt `Unreleased` in die neue Versionsnummer mit Datum (`TT.MM.JJJJ`)
   umbenennen
3. Commit `chore(release): Version X.Y.Z`
4. Merge nach `main` — der Bump-Workflow erhöht die Patch-Stelle und pusht sie zurück
5. Tag setzen: `git tag -a vX.Y.Z -m "Version X.Y.Z"` und pushen: `git push --tags`

## Was nie passiert

- Kein `git push --force` auf gemeinsam genutzte Branches
- Kein Commit direkt auf `main`
- Keine Secrets im Commit — vor dem Commit `git diff --staged` prüfen
- Keine generierten Artefakte (`node_modules/`, `.venv/`, Caches) im Repo. **Ausnahme mit
  Begründung:** das SPA-Bundle unter `app/static/` (D-035) — ohne es ließe sich das Add-on auf
  Architekturen ohne Node.js nicht bauen.
