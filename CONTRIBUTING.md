# Mitwirken

Die verbindlichen Regeln stehen in [AGENTS.md](AGENTS.md) — sie gelten für **Menschen und
KI-Agenten gleichermaßen**. Diese Datei wiederholt sie nicht, sondern nennt nur den Einstieg.

## Einstieg

1. [AGENTS.md](AGENTS.md) lesen — eiserne Regeln und Befehle.
2. [docs/README.md](docs/README.md) — Index der technischen Doku.
3. [docs/git-workflow.md](docs/git-workflow.md) — **bevor** committet wird.
4. [docs/entwicklerrichtlinien.md](docs/entwicklerrichtlinien.md) — Naming, Struktur, Kommentarstil.
5. [docs/test-strategie.md](docs/test-strategie.md) — was getestet werden muss.

## Vor jedem Pull Request

Die Checkliste steht in der PR-Vorlage
([.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)) und wird beim Anlegen
automatisch eingefügt.

## Arbeiten mit KI-Agenten

Alle Agenten ziehen ihre Regeln aus derselben Datei: `AGENTS.md`.
`CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md` und `.cursor/rules/` sind reine
Verweise darauf.

**Regeln werden ausschließlich in `AGENTS.md` geändert** — nie in einer der Verweisdateien.
Sonst gilt für ein Tool etwas anderes als für die übrigen, und genau das soll die Struktur
verhindern.
