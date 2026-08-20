# Design-System

> Verbindlich für **jede** Web-Oberfläche des Projekts. Architektur und Code-Muster stehen in
> [frontend.md](frontend.md) und werden hier nicht wiederholt — hier steht nur das Aussehen:
> Tokens, Klassen, Zustände.

Das System ist aus den Admin-Oberflächen von `FCR_CMS` und `FCR-Digitale-Stadion-Zeitung`
übernommen. Wer eine Oberfläche neu baut, kopiert die Referenz-`styles.css` und **erweitert** sie —
er erfindet kein zweites System daneben.

## Designsprachen

Das Vokabular ist eines. Was sich unterscheidet, sind ausschließlich die fünf Akzent-Tokens:

| Designsprache | Attribut | Akzent | Wofür |
|---|---|---|---|
| **Home Assistant** | `data-design="ha"` | `#18BCF2` | Projekte mit Bezug zu **Home Assistant**. Weiße bzw. schwarze Basis je nach Modus |
| **FCR** | `data-design="fcr"` | `#8a1f33` (hell) / `#c2334c` (dunkel) | Projekte mit Bezug zum **FC Ruderting** |
| *keine gesetzt* | fehlt oder unbekannt | Grau aus der Textskala | Sichtbares „noch nicht entschieden" — kein Zustand zum Ausliefern |

Das Attribut steht am `<html>`-Element und wird zur Bauzeit gesetzt (`init-projekt.sh --design`),
nicht zur Laufzeit umgeschaltet — eine Anwendung hat eine Designsprache, nicht zwei.

**Einen Default gibt es nicht, und die Wahl wird nie geraten.** Gehört das Projekt zu keiner der
beiden Welten oder ist die Zuordnung nicht zweifelsfrei, wird die Farbwahl **erfragt**, bevor die
erste Zeile Oberfläche entsteht — eiserne Regel 10 in [`../AGENTS.md`](../AGENTS.md). Hat der User
die Designsprache bereits genannt, gilt genau diese, ohne Rückfrage.

Fläche, Abstände, Klassen, Zustände und Icons sind in allen Sprachen identisch; wer die
Designsprache wechselt, tauscht Tokens, nie Markup. Eine **dritte** Designsprache ist eine
Design-Entscheidung: neuer `data-design`-Wert, fünf Akzent-Tokens je Modus, Eintrag in
[design-entscheidungen.md](design-entscheidungen.md) — nichts davon entsteht nebenbei im Code.

## Hell und Dunkel

Beide Modi sind Pflicht, in beiden Designsprachen, und beide sind vollständig ausgestaltet — ein
dunkler Modus ist keine invertierte Kopie des hellen.

| Aspekt | Festlegung |
|---|---|
| Umschaltung | Attribut `data-theme="light" \| "dark"` am `<html>` |
| Schalter | Sichtbar in der Kopfzeile jeder Seite (`PageHeader`), nie in einem Untermenü |
| Voreinstellung | Systemvorgabe (`prefers-color-scheme`) |
| Speicherung | Getroffene Wahl in `localStorage`, überlebt das Neuladen |
| Vor dem ersten Frame | Inline-Skript in `index.html` setzt `data-theme`, sonst blitzt Hell auf |
| Ohne JavaScript | `@media (prefers-color-scheme: dark)` greift für `:root:not([data-theme])` |
| Browser-Oberfläche | `color-scheme` je Modus, damit Scrollbalken und Autofill mitgehen |

Umsetzung im Code: [frontend.md](frontend.md).

## Grundsatz

**Eine Datei, ein Vokabular.** Alles Gestalterische steht in `src/styles.css`: erst die Tokens in
`:root`, dann die Klassen, gruppiert nach Bereich. Kein zweites Stylesheet, keine CSS-Module, kein
CSS-in-JS.

Daraus folgen vier Verbote, die nicht verhandelbar sind:

1. **Kein CSS-Framework und keine UI-Bibliothek.** Kein Tailwind, kein Bootstrap, kein MUI, kein
   shadcn. Die Oberflächen dieser Größenordnung tragen die Abhängigkeit nicht, und jede Library
   bringt ihr eigenes, konkurrierendes Token-System mit.
2. **Keine Inline-Styles für Gestaltung.** `style={{ color: '#8a1f33' }}` ist ein Fehler — es
   umgeht die Tokens und ist beim nächsten Theme-Wechsel unauffindbar. Zulässig sind Inline-Styles
   nur für dynamisch berechnete Werte (Fortschrittsbreite, Positionen, vom Server gelieferte
   Farbwerte).
3. **Keine Literalfarbe außerhalb von `:root`.** Jeder Farbwert im Regelwerk ist ein `var(--…)`.
4. **Keine neue Klasse für einen Einzelfall.** Erst prüfen, ob eine bestehende Klasse plus
   Modifier reicht (`.slide-card.off`, `.pill.warn`). Eine neue Klasse rechtfertigt sich ab der
   zweiten Verwendung.

## Tokens

Nur diese Werte existieren. Zwischenwerte werden nicht ad hoc erfunden, sondern als Token ergänzt.

### Farben — Flächen und Text

Beide Designsprachen teilen sich diese Skala; nur der Modus ändert die Werte.

| Token | Hell | Dunkel | Wofür |
|---|---|---|---|
| `--bg` | `#f4f5f7` | `#0c0d0f` | Seitenhintergrund, Fläche hinter den Karten |
| `--surface` | `#ffffff` | `#15171a` | Karten, Sidebar, Eingabefelder, Modal |
| `--surface-2` | `#f7f8fa` | `#1c1f23` | Abgesetzte Fläche: Hover-Zeile, Subformular, Thumbnail-Platzhalter |
| `--surface-blur` | `rgba(255,255,255,.88)` | `rgba(21,23,26,.88)` | Klebrige Kopfzeile hinter dem `backdrop-filter` |
| `--border` | `#e3e6ea` | `#262a30` | Trennlinien, Kartenrand |
| `--border-strong` | `#cdd2d9` | `#363b43` | Rand interaktiver Elemente (Input, Ghost-Button, Icon-Button) |
| `--text` | `#1b1d21` | `#f1f3f5` | Fließtext, Überschriften |
| `--text-2` | `#565d68` | `#a9aeb6` | Sekundärtext, inaktives Nav-Element |
| `--text-3` | `#8b919b` | `#7d838b` | Hilfetexte, Tabellenköpfe, Metadaten, Leerzustände |
| `--backdrop` | `rgba(16,24,40,.45)` | `rgba(0,0,0,.62)` | Verdunkelung hinter Modal und Off-Canvas-Sidebar |
| `--switch-knob` | `#ffffff` | `#ffffff` | Der Knopf im Schalter — bleibt in beiden Modi hell |

Die Schatten-Tokens werden im Dunkeln kräftiger und schwarz statt blaugrau: eine im Hellen
austarierte Schattenfarbe verschwindet auf dunklem Grund vollständig.

### Farben — Akzent

Die Akzentfarbe ist die **einzige** Stelle, an der eine Designsprache das System einfärbt. Fünf
Tokens, immer gemeinsam getauscht:

| Token | HA hell | HA dunkel | FCR hell | FCR dunkel | ohne Designsprache |
|---|---|---|---|---|---|
| `--primary` | `#18bcf2` | `#18bcf2` | `#8a1f33` | `#c2334c` | `var(--text-2)` |
| `--primary-hover` | `#0fa3d4` | `#4accf7` | `#731a2a` | `#d64a62` | `var(--text)` |
| `--primary-soft` | `#e6f7fe` | `rgba(24,188,242,.16)` | `#f6e9ec` | `rgba(194,51,76,.18)` | `var(--surface-2)` |
| `--primary-ring` | `rgba(24,188,242,.28)` | `rgba(24,188,242,.38)` | `rgba(138,31,51,.28)` | `rgba(194,51,76,.38)` | `var(--border-strong)` |
| `--on-primary` | `#06222c` | `#06222c` | `#ffffff` | `#ffffff` | `var(--surface)` |

Die letzte Spalte greift, wenn `data-design` fehlt oder einen unbekannten Wert trägt. Sie führt
bewusst **keinen eigenen Farbwert** ein, sondern borgt sich Grau aus der Textskala — ein dritter
Farbton wäre sonst schnell als drittes Schema missverstanden.

Herleitung, wenn eine Akzentfarbe neu gesetzt wird:

- `--primary-hover`: im Hellen ca. 10 % dunkler, im Dunkeln ca. 15 % **heller**. Ein dunklerer
  Hover verschwindet auf schwarzem Grund.
- `--primary-soft`: im Hellen der Ton mit ca. 8 % Deckkraft auf Weiß, im Dunkeln derselbe Ton als
  `rgba(…, .16–.18)` — ein aufgehellter Festwert wirkt auf dunklem Grund milchig.
- `--primary-ring`: derselbe Ton mit 28 % (hell) bzw. 38 % (dunkel) Deckkraft, nur für Fokusringe.
- `--on-primary`: die Schrift **auf** der Akzentfläche, gewählt nach Kontrast, nicht nach Gefühl.
  Auf `#18BCF2` trägt Weiß nur 2,2:1 und ist damit unbrauchbar — dunkle Tinte trägt 8,7:1. Auf dem
  Vereinsrot ist es umgekehrt.

`--primary` trägt: Primärbutton, aktives Nav-Element, Fokusrand, Kachel-Icon, Switch-Zustand
„an", Wappen/Avatar. Nirgends sonst — großflächige Akzentfarbe macht die Oberfläche laut und die
Statusfarben unlesbar.

### Farben — Status

Immer paarweise: kräftiger Ton für Text/Icon, weicher Ton für die Fläche dahinter.

| Bedeutung | Ton hell | Fläche hell | Ton dunkel | Fläche dunkel |
|---|---|---|---|---|
| Erfolg / aktiv | `--ok` `#1f7a4d` | `--ok-soft` `#e7f4ed` | `#45c07f` | `rgba(69,192,127,.15)` |
| Warnung / veraltet | `--warn` `#9a6700` | `--warn-soft` `#fbf3df` | `#d4a13c` | `rgba(212,161,60,.15)` |
| Fehler / zerstörend | `--danger` `#b42318` | `--danger-soft` `#fbeae8` | `#f2695f` | `rgba(242,105,95,.15)` |

Verwendung unverändert: Pill „Aktuell"/„Veraltet", Toasts, Status-Punkt, Feldfehler, `.alert`.
`--on-status` (`#ffffff` hell, `#0c0d0f` dunkel) ist die Schrift auf einer vollflächigen
Statusfarbe — betrifft nur die gefüllten Toasts.

Grau (`--text-3` auf `--surface-2`) heißt „inaktiv/leer", nicht „Fehler".

### Form

| Token | Wert | Wofür |
|---|---|---|
| `--radius-sm` | `8px` | Buttons, Inputs, Icon-Buttons, Nav-Einträge |
| `--radius` | `12px` | Karten, Kacheln, Toasts, Dropzone |
| `--radius-lg` | `16px` | Modal, Login-Karte |
| — | `999px` | Pills, Switch-Track, Avatar (bewusst kein Token: „maximal rund") |
| `--shadow-sm` | zweistufig, weich | Ruhezustand von Karten und Kacheln |
| `--shadow-md` | zweistufig, mittel | Hover von Kacheln und Karten |
| `--shadow-lg` | `0 18px 40px …` | Modal, Toast, ausgefahrene Mobile-Sidebar |
| `--sidebar-w` | `248px` | Sidebar-Breite |

### Typografie

Systemschrift, keine Webfont-Einbindung — das spart einen Netzwerkabruf und sieht auf jedem
Betriebssystem nativ aus.

```css
--font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
--mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
```

| Rolle | Größe | Gewicht |
|---|---|---|
| Basistext (`body`) | 15px / 1.55 | 400 |
| Seitentitel (`.topbar h1`) | 18px | 700 |
| Kartentitel (`.card-head h2`) | 15px | 700 |
| Feldlabel | 13.5px | 600 |
| Button | 14px | 600 |
| Tabellenkopf, Nav-Gruppe | 11–12px, `uppercase`, `letter-spacing: .04–.05em` | 700 |
| Hilfetext, Metadaten | 12.5–13px | 400, `--text-3` |
| Kachelzahl (`.num`) | 28px, `letter-spacing: -.02em` | 800 |

`--mono` nur für technische Werte: IDs, JSON, Dateinamen, Farbcodes.

## Klassenkatalog

Das ist das vollständige Vokabular. Ein Agent, der eine Oberfläche baut, benutzt diese Namen und
erfindet keine Synonyme (`.button`, `.panel`, `.chip` gibt es nicht).

### Gerüst

| Klasse | Bedeutung |
|---|---|
| `.shell` | Flex-Container: Sidebar + Hauptbereich, `min-height: 100vh` |
| `.sidebar` | Feste Navigationsspalte, `position: sticky` |
| `.sidebar-brand` / `.crest` | Kopf der Sidebar mit quadratischem Logo-Kürzel |
| `.nav` / `.nav-label` / `.nav-item` / `.nav-item.active` / `.count` | Navigation, Gruppenüberschrift, Eintrag, aktiver Eintrag, Zähler-Badge rechts |
| `.sidebar-foot` / `.avatar` / `.who` | Fuß der Sidebar: Benutzer bzw. Systemzustand |
| `.main` | Hauptspalte |
| `.topbar` | Klebriger Seitenkopf: `h1`, `.sub`, `.spacer`, danach Aktionsbuttons |
| `.content` | Inhaltsbreite (`max-width` 1080–1180px, `padding: 28px`, zentriert) |
| `.form-content` | Schmalere Variante für Formularseiten (`max-width: 900px`) |

### Container

| Klasse | Bedeutung |
|---|---|
| `.card` / `.card-head` / `.card-body` | Standardcontainer. `.card-head` enthält `h2` plus optional `.sub` |
| `.tiles` / `.tile` / `.tile-icon` / `.num` | Kachelraster (`auto-fill, minmax(210px, 1fr)`), meist als `<Link>` |
| `.table-wrap` + `table.data` | Datentabelle; `.table-wrap` liefert horizontales Scrollen |
| `.cell-title` / `.cell-sub` | Erste Spalte: Titel fett, Nebenzeile grau |
| `.empty` | Leerzustand: Icon, Satz, Primäraktion |
| `.center` + `.spinner` | Ladezustand |
| `.alert` | Blockierende Fehlermeldung im Seitenkopf |
| `.info-strip` | Einzeiliger Erklärhinweis über einer Liste |
| `.modal-backdrop` / `.modal` / `.modal-head` / `.modal-body` / `.modal-foot` | Dialog |

### Bedienelemente

| Klasse | Bedeutung |
|---|---|
| `.btn` | Basis. Nie allein, immer mit Variante |
| `.btn-primary` | Genau **eine** pro Bildschirmbereich: die Hauptaktion |
| `.btn-ghost` | Sekundär: Abbrechen, Zurück, Nebenaktionen |
| `.btn-danger` | Zerstörend. Weiße Fläche, roter Text — rot füllt sich erst beim Hover |
| `.btn-sm` | Kompakte Variante für Listenzeilen |
| `.icon-btn` | 34×34 quadratisch, nur Icon — **braucht immer `aria-label`** |
| `.danger-icon` | Modifier für `.icon-btn`: Hover wird rot |
| `.row-actions` | Aktionsgruppe am rechten Rand einer Zeile |
| `.pill` + `.ok` / `.warn` / `.err` / `.muted` / `.primary` | Statusanzeige, nie klickbar |
| `.switch` / `.track` / `.switch-label` | Schalter für boolesche Werte statt Checkbox |
| `.device-card` + `.active` / `.idle` / `.off` / `.charge` / `.discharge` | Gerätekarte; der linke Rand trägt den Zustand. `charge` und `discharge` gibt es nur beim Speicher — er ist das einzige Gerät, das Leistung auch abgeben kann, und die Richtung ist beim Debuggen die erste Frage |
| `.soc-bar` + `.fill` / `.mark` / `.mark.limit` | Ladezustandsbalken mit Markern für Minimum, Notstromreserve und Ladeschluss. Breite und Positionen sind dynamisch und deshalb Inline-Styles (siehe Regel 2) |
| `.dropzone` / `.dropzone.drag` | Datei-Upload-Fläche |
| `.toasts` / `.toast` / `.toast.ok` / `.toast.err` | Kurzrückmeldung unten rechts |

### Formular

| Klasse | Bedeutung |
|---|---|
| `.field` | Ein Feld: Label, Eingabe, optional `small` als Hilfetext |
| `.field.invalid` + `.field-error` | Fehlerzustand: roter Rand, roter Hinweistext darunter |
| `.form-grid` (bzw. `.grid-2`) | Zweispaltiges Formular; `.wide` überspannt beide Spalten |
| `.form-footer` | Klebrige Fußzeile mit Abbrechen + Speichern |
| `.hint-box` | Gestrichelter Kasten: fehlende Voraussetzung plus Weg dorthin |
| `.advanced-card` | `<details>`-Karte für selten gebrauchte Felder |

Pflichtfelder werden am Label markiert (`*` in `--primary`), nicht durch Farbe des Eingabefelds.

## Zustände

Jedes interaktive Element beantwortet vier Fragen sichtbar:

| Zustand | Umsetzung |
|---|---|
| Hover | Fläche wechselt eine Stufe (`--surface` → `--surface-2`), Kacheln zusätzlich `translateY(-2px)` + `--shadow-md` |
| Aktiv/Klick | `transform: translateY(1px)` — taktile Rückmeldung ohne Farbwechsel |
| Fokus | `border-color: var(--primary)` **und** `box-shadow: 0 0 0 3px var(--primary-ring)`. Der Ring wird nie entfernt |
| Deaktiviert | `opacity: .45–.55` + `cursor: not-allowed`. Nie ausblenden — ein verschwundener Button ist unerklärlich |

Übergänge: 0.12 s für Farbwechsel, 0.15–0.18 s für Rahmen/Schatten/Switch, 0.05 s für den
Klick-Versatz. Nichts animiert länger als 0.2 s.

## Responsiv

Drei Haltepunkte, mobil zuletzt gedacht, aber nie weggelassen:

| Breite | Was passiert |
|---|---|
| ≤ 1050px | Mehrspaltige Kachelraster gehen auf zwei Spalten; breite Listenzeilen brechen um |
| ≤ 820px | Sidebar wird zum Off-Canvas-Panel: `position: fixed`, `translateX(-102%)`, `.sidebar.open` fährt aus, `.sidebar-backdrop` verdunkelt, `.mobile-menu` erscheint oben links, `.topbar` bekommt links Platz für den Knopf |
| ≤ 620px | Alle Raster einspaltig, Kopfzeilen-Buttons volle Breite, Toasts über die ganze Breite, Padding von 28px auf 16px |

`.table-wrap` scrollt horizontal, statt die Tabelle umzubrechen — eine umgebrochene Datentabelle
ist unlesbar.

## Icons

Ein eigenes, kleines Set als React-Komponente, **keine** Icon-Bibliothek als Abhängigkeit.

- `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="1.8"`,
  `stroke-linecap`/`stroke-linejoin` auf `round`, `aria-hidden="true"`.
- Größe über eine `size`-Prop, Standard 18px; 16px in Buttons, 40px im Leerzustand.
- Farbe kommt immer über `currentColor` vom Elternelement — nie hart im SVG.
- Unbekannter Name liefert ein neutrales Fallback statt eines Absturzes.
- Neue Icons werden dem Set hinzugefügt, nicht als Einzel-SVG in eine Seite kopiert.

## Barrierefreiheit

Nicht verhandelbar, weil billig beim Bauen und teuer beim Nachrüsten:

- Jeder Button ohne sichtbaren Text bekommt `aria-label`.
- Der Toast-Container trägt `aria-live="polite"`.
- Der Fokusring bleibt sichtbar; `outline: none` nur zusammen mit einem Ersatz-`box-shadow`.
- Schalter sind echte `<input type="checkbox">` in einem `<label>` — nicht anklickbare `<div>`.
- Zustand wird nie allein über Farbe transportiert: Die Pill trägt zusätzlich Text.
- Interaktive Zeilen sind `<button>` oder `<a>`, damit Tastatur und Screenreader sie finden.
- Kontrast gilt in **beiden** Modi: Fließtext ≥ 4,5:1, große Schrift und Ränder ≥ 3:1. Geprüft
  wird hell und dunkel, nicht nur der Modus, in dem gerade entwickelt wird.
- Der Theme-Schalter ist ein `<button>` mit `aria-pressed` und `aria-label` — ein Icon allein sagt
  einem Screenreader nichts.

## Beim Erweitern

1. Passt es in eine bestehende Klasse plus Modifier? Dann so.
2. Sonst: neue Klasse **im passenden Abschnitt** von `styles.css`, Name nach Bereich benannt
   (`.sponsor-card`, nicht `.card2`), ausschließlich mit Tokens formuliert.
3. Neuer Token nur, wenn der Wert an mindestens zwei Stellen gebraucht wird. Ein Farbtoken wird
   für **beide** Modi gesetzt — ein nur im Hellen definierter Wert ist im Dunkeln ein Fehler, der
   erst beim Nutzer auffällt.
4. Nach jeder Änderung an Farben: einmal umschalten und beide Modi ansehen.
5. Ein neues Muster, das andere Seiten übernehmen sollen, ist eine Design-Entscheidung →
   [design-entscheidungen.md](design-entscheidungen.md).
