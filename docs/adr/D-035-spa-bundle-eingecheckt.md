# D-035: Das gebaute SPA-Bundle wird eingecheckt statt im Add-on-Image gebaut

- **Datum:** 13.08.2026
- **Status:** Aktiv
- **Betrifft:** `web/`, `app/static/`, `Dockerfile`, `.github/workflows/ci.yaml`, `.gitignore`

## Kontext

Eiserne Regel 8 verlangt eine Oberfläche aus React + TypeScript + Vite. Damit gibt es erstmals
einen Build-Schritt zwischen Quellcode und ausgeliefertem Artefakt.

Ein Home-Assistant-Add-on wird nicht zentral gebaut, sondern **auf dem HA-Host des Nutzers** aus
dem Repository. Randbedingungen daraus:

- `config.yaml` nennt die Architekturen `aarch64`, `amd64`, `armhf`, `armv7` und `i386`. Für
  `i386` und `armhf` veröffentlicht das Node.js-Projekt keine offiziellen Images.
- Auf einem Raspberry Pi dauert `npm ci` plus `vite build` mehrere Minuten und lädt über hundert
  Megabyte nach — bei jeder Add-on-Aktualisierung.
- Die Vorlage verbietet generierte Artefakte im Repo ([git-workflow.md](../git-workflow.md)),
  gedacht gegen `dist/`-Ordner, die niemand pflegt und die still veralten.

## Betrachtete Optionen

### Option A — Mehrstufiges Dockerfile mit Node-Build-Stage

- Dafür: Regelkonform, das Repo bleibt frei von Build-Output, keine Drift möglich.
- Dagegen: `i386` und `armhf` müssten aus der Architekturliste entfernt werden — bestehende
  Installationen auf diesen Plattformen ließen sich nicht mehr aktualisieren. Jede Installation
  würde deutlich langsamer.

### Option B — Bundle einchecken, CI prüft auf Drift

- Dafür: Der Add-on-Build bleibt exakt so schlank wie heute (`COPY app/ .`), alle Architekturen
  bleiben erhalten, die Installation dauert unverändert Sekunden.
- Dagegen: Generiertes liegt im Repo, Diffs werden größer, und ohne Absicherung könnte jemand
  Quellen ändern, ohne neu zu bauen.

### Option C — Bundle in der CI bauen und als Release-Artefakt anhängen

- Dafür: Repo bleibt sauber.
- Dagegen: Die Add-on-Installation hinge an einem Release-Prozess, den es heute nicht gibt; der
  Supervisor lädt aus dem Repository, nicht aus GitHub-Releases.

## Entscheidung

**Option B.** Das Bundle liegt unter `app/static/` im Repo. Der Nachteil „Generiertes im Repo"
wird durch einen Drift-Check in der CI entschärft: Sie baut neu und bricht ab, wenn sich das
Ergebnis vom eingecheckten Stand unterscheidet. Damit kann das Bundle nicht unbemerkt veralten —
genau die Gefahr, gegen die die ursprüngliche Regel gerichtet war.

Gegen Option A entschieden, weil sie Nutzer auf `i386` und `armhf` von Updates abschneidet; das
ist eine Funktionseinschränkung, keine Aufräumarbeit.

## Folgen

- **Positiv:** Der Add-on-Build und die Architekturliste bleiben unverändert; das Risiko des
  Frontend-Umbaus für den Betrieb ist minimal.
- **Negativ:** Commits, die die Oberfläche ändern, enthalten auch minifizierte Dateien. Reviews
  betrachten `web/`, nicht `app/static/`.
- **Aufwand:** Ein zusätzlicher CI-Job (`npm ci`, `npm run build`, `git diff --exit-code
  app/static`) und die Pflicht, nach Frontend-Änderungen zu bauen — vermerkt in
  [git-workflow.md](../git-workflow.md) und in [`AGENTS.md`](../../AGENTS.md).

## Rücknahmebedingung

Sobald der Add-on-Build nicht mehr auf dem HA-Host stattfindet (etwa über vorgebaute Images aus
einer Registry) oder die Architekturen `i386` und `armhf` ohnehin entfallen, ist Option A die
bessere Wahl und diese Entscheidung wird ersetzt.
