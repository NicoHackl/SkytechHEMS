# Dokumentation — Skytech HEMS

Ausführliche technische Referenz. Die **verbindlichen Regeln** stehen nicht hier, sondern in
[`AGENTS.md`](../AGENTS.md) im Repo-Root. Bei Widerspruch gilt `AGENTS.md`.

Diese Doku beschreibt den **tatsächlichen Stand des Codes**, nicht die Wunschvorstellung.
Weicht die Implementierung ab, gehört das nach [bekannte-luecken.md](bekannte-luecken.md) —
nicht stillschweigend schöngeschrieben.

## Schnellstart für neue Agenten und Entwickler

1. [`AGENTS.md`](../AGENTS.md) lesen — eiserne Regeln und Befehle.
2. [architektur.md](architektur.md) lesen — Projektzweck und Grobstruktur.
3. [git-workflow.md](git-workflow.md) lesen — **bevor** irgendetwas committet wird.
4. Für die konkrete Aufgabe die passende Datei unten nachschlagen, statt zu raten.
5. [bekannte-luecken.md](bekannte-luecken.md) prüfen, bevor angenommen wird, eine hier
   beschriebene Funktion existiere bereits.

## Inhaltsverzeichnis

| Datei | Inhalt |
|---|---|
| [architektur.md](architektur.md) | Komponenten, Verantwortlichkeiten, Datenfluss, Tech-Stack, Grenzen |
| [entwicklerrichtlinien.md](entwicklerrichtlinien.md) | Naming, Projektstruktur, Fehlerbehandlung, Kommentarstil, Abhängigkeiten |
| [frontend.md](frontend.md) | Frontend-Stack, Verzeichnisstruktur, Routing, API-Client, Seitenmuster, Hell/Dunkel, Auslieferung unter Ingress |
| [design-system.md](design-system.md) | Designsprachen, Tokens je Modus, Klassenkatalog, Zustände, Haltepunkte, Icons, Barrierefreiheit |
| [git-workflow.md](git-workflow.md) | Branch-Modell, Commit-Format, Versionierung, Release-Ablauf |
| [test-strategie.md](test-strategie.md) | Testarten, Pflicht-Testfälle, Fixtures, Coverage-Ziel |
| [design-entscheidungen.md](design-entscheidungen.md) | Entscheidungs-Log — Quelle der Wahrheit fürs „warum" |
| [adr/](adr/) | Ausführliche Architecture Decision Records zu einzelnen Entscheidungen |
| [konfiguration.md](konfiguration.md) | Add-on-Optionen, Konfigurationsseite und Supervisor-Anbindung, Umgebungsvariablen, Secrets-Handhabung |
| [datenmodell.md](datenmodell.md) | HA-Helfer-Namenskonvention, Statusvertrag zum Energy Pilot |
| [device_classes/global.md](device_classes/global.md) | Globale HA-Entitäten, Add-on-Optionen, gemeinsame Gerätefelder und Fallback-Regeln |
| [device_classes/controllable.md](device_classes/controllable.md) | HA- und Add-on-Vertrag für stufenlos regelbare Geräte |
| [device_classes/binary.md](device_classes/binary.md) | HA- und Add-on-Vertrag für binäre Geräte |
| [device_classes/battery.md](device_classes/battery.md) | HA- und Add-on-Vertrag für AC-Speicher |
| [api-referenz.md](api-referenz.md) | REST-Endpunkte des Add-ons und genutzte HA-Endpunkte |
| [sicherheit-datenschutz.md](sicherheit-datenschutz.md) | Token, personenbezogene Daten, externe Dienste |
| [bekannte-luecken.md](bekannte-luecken.md) | Abweichungen Spec ↔ Code, Stolpersteine, offene Bugs |
| [roadmap.md](roadmap.md) | Meilensteine und realistischer Umsetzungsstand |

## Pflegeregeln dieser Doku

- **Jede Information genau einmal.** Steht etwas in `AGENTS.md`, wird es hier nicht wiederholt,
  sondern verlinkt. Steht etwas in `architektur.md`, wird es in `api-referenz.md` verlinkt statt
  kopiert.
- Nicht zutreffende Dateien werden **gelöscht**, nicht mit Platzhaltertext stehengelassen.
  Ein leeres Gerüst ist schlimmer als eine fehlende Datei, weil ein Agent es für vollständig hält.
- Änderungen an Verhalten und Doku gehören ins **selbe** Arbeitspaket.
