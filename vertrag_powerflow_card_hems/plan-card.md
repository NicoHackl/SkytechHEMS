# Umsetzungsplan: Skytech Power Flow Card

> **Repository:** `Skytech-Power-Flow-Card` (neu, eigenständig).
> **Mitgeliefert und autoritativ:** [`kontrakt.md`](kontrakt.md) — der Datenvertrag. Jedes
> Feld, jeder Vorzeichenbegriff und jede Rückfallregel steht dort. Bei Widerspruch zwischen dieser
> Datei und `kontrakt.md` gilt `kontrakt.md`.
>
> **Stand:** 23.08.2026. Entwurf v1 — Grundlage der Umsetzung.

## Zweck und Arbeitsauftrag

Gebaut wird eine Home-Assistant-Lovelace-Karte, die den Leistungsfluss im Haus zeichnet —
Erzeugung, Netz, Speicher, Haus und die einzelnen Verbraucher.

Der Unterschied zum Vorbild
[`power-flow-card-plus`](https://github.com/flixlix/power-flow-card-plus) ist der Kern des
Auftrags: **Die Karte wird nicht im Dashboard-Editor mit Entitäten verdrahtet.** Sie liest ihre
gesamte Konfiguration aus einer Sensor-Entität, die das Skytech HEMS (ein Home-Assistant-Add-on)
veröffentlicht. Wird im HEMS ein Gerät angelegt, umbenannt oder entfernt, zieht die Karte ohne
jede Dashboard-Änderung nach.

Die minimale und im Regelfall vollständige Dashboard-Konfiguration lautet:

```yaml
type: custom:skytech-power-flow-card
```

Vor der ersten Zeile Code vollständig lesen: [`kontrakt.md`](kontrakt.md).

---

## Verbindliche Entscheidungen

1. **Stack:** TypeScript im `strict`-Modus, [Lit](https://lit.dev), Bündelung mit Vite/Rollup zu
   **einer** Datei `dist/skytech-power-flow-card.js`. Lit ist der Standard des HA-Frontends. Keine
   weitere UI-Bibliothek, keine Diagrammbibliothek, kein CSS-Framework.

2. **Keine externen Laufzeitabhängigkeiten und keine externen Assets.** Keine Schriftart, kein
   Bild, kein CDN-Aufruf. Icons kommen über das HA-eigene `<ha-icon>`.

3. **Kein HTTP-Aufruf.** Die Karte liest ausschließlich `hass.states`. Es gibt keinen Zugriff auf
   das Add-on, keine Ingress-Session, kein Polling. Aktualisierungen liefert Home Assistant
   ereignisgesteuert über den `hass`-Setter.

4. **Nur lesend.** Die Karte schaltet nichts. Interaktion beschränkt sich auf das Öffnen des
   HA-More-Info-Dialogs.

5. **Optik:** Grundlage sind die Theme-Variablen von Home Assistant
   (`--card-background-color`, `--primary-text-color`, `--secondary-text-color`,
   `--divider-color`, `--ha-card-border-radius`). Damit passt sich die Karte jedem Theme und
   beiden Modi an, ohne eine eigene Hell/Dunkel-Umschaltung zu brauchen. Eigene Farbtoken gibt es
   nur für die Flussarten und den Skytech-Akzent.

6. **Skytech-Akzent `#18BCF2`** markiert HEMS-**gesteuerte** Geräte als Ring um den Knoten. Er
   trennt sie sichtbar von der übrigen Hauslast. Der Akzent wird nirgends großflächig eingesetzt.

7. **Sprache:** Alle sichtbaren Texte, Fehlermeldungen, Hinweise und Codekommentare sind
   **deutsch**. Bezeichner im Code — Variablen, Funktionen, Klassen, Dateinamen — sind
   **englisch**. Ausnahme sind die Feldnamen aus dem Datenvertrag; sie werden wortgleich
   übernommen, auch wo sie deutsch sind (`anzeige`, `farbe`, `reihenfolge`, `leistung_w`).

8. **Datum und Uhrzeit:** Datumsangaben `TT.MM.JJJJ`, Uhrzeiten in Berliner Zeit als `hh:mm`
   beziehungsweise `hh:mm:ss`. **Nie** ein Zeitzonenkürzel oder einen Offset anhängen. Der
   Erzeuger liefert bereits fertig formatierte Zeitstempel — sie werden unverändert angezeigt.

9. **Keine Literalfarbe außerhalb der Token-Definition.** Farben werden einmal als CSS-Variable
   definiert und danach nur noch über `var(--…)` verwendet.

10. **Zustand nie allein über Farbe.** Jeder Zustand, den eine Farbe transportiert, hat zusätzlich
    Text, Form oder Symbol.

---

## Repository-Gerüst

```
Skytech-Power-Flow-Card/
├── src/
│   ├── skytech-power-flow-card.ts   Kartenelement (LitElement), Registrierung, Render
│   ├── editor.ts                    schlanker Lovelace-Editor (drei Felder)
│   ├── types.ts                     Datenvertrag als TypeScript-Typen
│   ├── contract.ts                  Lesen und Prüfen der beiden Entitäten
│   ├── power.ts                     Auflösung je power_kind, Vorzeichen, Zustände
│   ├── balance.ts                   Bilanzregeln, Knoten- und Kantenwerte
│   ├── layout.ts                    Geometrie: Knotenpositionen, Kantenpfade
│   ├── flow-svg.ts                  SVG-Erzeugung, Linienstärke, Punktanimation
│   ├── format.ts                    W/kW-Formatierung, Prozent, „—" für unbekannt
│   └── styles.ts                    css`` mit Token-Definition und Klassen
├── test/
│   ├── power.test.ts
│   ├── balance.test.ts
│   └── layout.test.ts
├── kontrakt.md                      der mitgelieferte Datenvertrag
├── plan-card.md                     diese Datei
├── hacs.json
├── info.md                          HACS-Beschreibung
├── README.md
├── package.json
├── tsconfig.json                    strict, noUnusedLocals, noUnusedParameters
├── vite.config.ts
└── .github/workflows/
    ├── ci.yaml                      typecheck + Tests + Build
    └── release.yaml                 hängt dist/ an das GitHub-Release
```

`package.json`-Skripte: `dev`, `build` (`tsc --noEmit && vite build`), `typecheck`, `test`
(Vitest). Laufzeitabhängigkeit: ausschließlich `lit`.

Build-Ziel: **ein** ES-Modul, kein Code-Splitting, keine externen Chunks — HACS liefert eine
einzelne Datei aus.

---

## Registrierung in Home Assistant

```ts
customElements.define('skytech-power-flow-card', SkytechPowerFlowCard)

// Damit die Karte im Karten-Auswahldialog erscheint.
;(window as any).customCards = (window as any).customCards || []
;(window as any).customCards.push({
  type: 'skytech-power-flow-card',
  name: 'Skytech Power Flow Card',
  description: 'Leistungsfluss, der sich seine Geräte selbst aus dem Skytech HEMS holt.',
  preview: true,
  documentationURL: 'https://github.com/…',
})
```

Pflichtschnittstelle einer Lovelace-Karte, vollständig umzusetzen:

| Element | Verhalten |
|---|---|
| `set hass(hass)` | Zustand übernehmen. **Nur neu rendern, wenn sich eine der abonnierten Entitäten tatsächlich geändert hat** — sonst rendert die Karte bei jeder HA-Zustandsänderung im ganzen Haus. |
| `setConfig(config)` | Konfiguration prüfen, Defaults setzen. Wirft bei unbrauchbarer Konfiguration mit deutscher Meldung. |
| `getCardSize()` | Höhe in Rasterreihen, abhängig von der Geräteanzahl. |
| `static getConfigElement()` | Liefert `<skytech-power-flow-card-editor>`. |
| `static getStubConfig()` | Liefert `{ type: 'custom:skytech-power-flow-card' }`. |

### Die Menge der abonnierten Entitäten

Nach dem Lesen der Konfigurationsentität steht fest, welche Entity-IDs die Karte braucht. Diese
Menge wird gehalten und im `hass`-Setter gegen den vorherigen Zustand verglichen. Nur bei einer
echten Änderung wird gerendert. Die Menge wird neu gebildet, sobald sich `revision` der
Konfigurationsentität ändert.

### Lovelace-Konfiguration

Alle Felder sind optional:

```yaml
type: custom:skytech-power-flow-card
config_entity: sensor.skytech_hems_flow_config   # Default
status_entity: sensor.skytech_hems_flow_status   # Default
title: "Leistungsfluss"                          # überschreibt anzeige.titel aus dem Vertrag
```

Der Editor (`editor.ts`) bietet genau diese drei Felder über `<ha-entity-picker>` und
`<ha-textfield>` und darüber einen Hinweis: *„Erzeugung, Netz, Speicher und die Geräteliste werden
im Skytech-HEMS-Panel unter ‚Flow Card' gepflegt — nicht hier."*

---

## Datenfluss innerhalb der Karte

```
 hass.states
     │
     ▼
 contract.ts   liest config_entity + status_entity
     │         prüft schema_version, meldet Vertragsfehler
     ▼
 power.ts      löst jeden Verweis auf → { wert: number|null, quelle: 'direkt'|'status'|'unbekannt' }
     │
     ▼
 balance.ts    bildet Knotenwerte und Kantenflüsse, deckelt gegen die Hausleistung
     │
     ▼
 layout.ts     setzt Knotenpositionen, berechnet Kantenpfade
     │
     ▼
 flow-svg.ts   zeichnet Pfade, Linienstärken, Punktanimation
     │
     ▼
 Render        <ha-card> mit SVG, Knotenbeschriftungen und Kopfabzeichen
```

Jede Stufe ist rein: gleiche Eingabe, gleiche Ausgabe, kein Zugriff auf `hass` außerhalb von
`contract.ts` und `power.ts`. Nur so sind `power.ts`, `balance.ts` und `layout.ts` ohne
HA-Attrappe testbar.

---

## Auflösung der Messwerte — `power.ts`

Umsetzung von [`kontrakt.md`](kontrakt.md) Abschnitt 5 und 6. Ergebnistyp:

```ts
type Aufloesung = {
  wert: number | null            // Watt, positiv = Verbrauch bzw. Laden
  quelle: 'direkt' | 'status' | 'unbekannt'
}
```

Regeln, verbindlich:

- Ein Zustand gilt als gültig, wenn er sich in eine **endliche** Zahl wandeln lässt.
  `unavailable`, `unknown`, `''`, `NaN` und `Infinity` sind ungültig.
- **Ungültig wird niemals zu `0`.** Die Reihenfolge ist: Direktwert → `status.devices[id].leistung_w`
  → `quelle: 'unbekannt'`.
- Die fünf `power_kind`-Varianten werden genau nach der Tabelle in [`kontrakt.md`](kontrakt.md)
  Abschnitt 5 umgesetzt, einschließlich der 230-Volt-Annahme und der Phasenzahl-Rückfallregel.
- `power_kind`-Werte, die die Karte nicht kennt, führen zu `quelle: 'unbekannt'` — nicht zu einem
  Fehler. Der Vertrag erlaubt additive Erweiterungen.

Netz und Batterie werden nach denselben Regeln aufgelöst und anschließend in Richtungen zerlegt:

```
netzbezug     = grid > 0 ? grid : 0        // nach Anwendung von grid_power_sign
netzeinspeisung = grid < 0 ? -grid : 0
laden         = batterie > 0 ? batterie : 0   // nach Anwendung von power_sign
entladen      = batterie < 0 ? -batterie : 0
```

Bei getrennten Sensoren (`grid_import_entity`/`grid_export_entity`, `charge_power_entity`/
`discharge_power_entity`) entfällt die Zerlegung; die Beträge werden direkt gelesen.

---

## Bilanzregeln — `balance.ts`

Das ist der fachlich heikelste Teil. Ziel: eine Grafik, die sich nicht widerspricht, auch wenn die
Sensoren es tun.

**1. Hausleistung.** Ist `house_power_entity` belegt und gültig, gilt dieser Wert. Sonst wird
gerechnet:

```
haus = pv + netzbezug + entladen − netzeinspeisung − laden
```

Ergibt das einen negativen Wert, wird auf `0` geklemmt und der Kopf bekommt das Abzeichen
„Bilanz unplausibel".

**2. Geräte gegen das Haus deckeln.** Die HEMS-Geräte sind Teil der Hauslast. Werden sie zusätzlich
gezeichnet, erscheint mehr Verbrauch als vorhanden:

```
geraete_summe = Σ max(0, geraet.wert)          // unbekannte Geräte zählen mit 0 mit
geraete_summe = min(geraete_summe, haus)       // nie mehr als das Haus verbraucht
uebriges_haus = haus − geraete_summe
```

Muss gedeckelt werden, werden die Geräteflüsse **proportional** gekürzt und der Kopf bekennt das
Abzeichen „Geräteleistung übersteigt Hausleistung". Ohne diesen Hinweis sähe die Karte richtig
aus, obwohl sie es nicht ist.

**3. Herkunft der Hausleistung aufteilen.** Wie viel des Hausverbrauchs kommt woher:

```
pv_ins_haus       = min(pv, haus)
rest              = haus − pv_ins_haus
batterie_ins_haus = min(entladen, rest)
netz_ins_haus     = max(0, rest − batterie_ins_haus)
```

**4. Verbleib der PV-Leistung.**

```
pv_in_batterie = min(max(0, pv − pv_ins_haus), laden)
pv_ins_netz    = max(0, pv − pv_ins_haus − pv_in_batterie)
netz_in_batterie = max(0, laden − pv_in_batterie)     // Netzladen, falls vorhanden
```

**5. Kanten mit dem Wert `0` oder `null` werden nicht gezeichnet.** Kein Strich, kein Punkt, keine
Beschriftung. Eine Karte voller Nulllinien ist unlesbar.

**6. Unbekannte Werte** erscheinen am Knoten als `—` in gedämpfter Farbe. Ihre Kanten entfallen.
Ein unbekanntes Gerät wird als Knoten trotzdem gezeichnet — sonst verschwände es scheinbar aus der
Anlage.

---

## Geometrie — `layout.ts`

Feste Grundanordnung, an der sich das Auge orientiert:

```
                    ┌────────┐
                    │   PV   │
                    └────┬───┘
                         │
   ┌────────┐       ┌────┴───┐        ┌──────────────┐
   │  Netz  ├───────┤  Haus  ├────────┤ Heizstab     │
   └────┬───┘       └────┬───┘        ├──────────────┤
        │                │            │ Wallbox      │
   ┌────┴────────────────┴───┐        ├──────────────┤
   │        Batterie         │        │ Heizlüfter 1 │
   └─────────────────────────┘        └──────────────┘
                                       HEMS-Geräte
```

- **PV** oben Mitte, **Netz** links, **Haus** Mitte, **Batterie** unten Mitte. Fehlt ein Knoten
  (kein PV konfiguriert, keine Batterie), rücken die verbleibenden zusammen; es entsteht kein Loch.
- **HEMS-Geräte** hängen rechts am Hausknoten, in der Reihenfolge des Vertrags, plus ein Knoten
  „Übriges Haus", wenn `uebriges_haus > 0`.
- **`anzeige.haus_knoten_anzeigen: false`** lässt den Hausknoten entfallen. Die Geräte hängen dann
  direkt am Verteilpunkt zwischen PV, Netz und Batterie, „Übriges Haus" wird zu einem eigenen
  Knoten. Die Bilanzregeln bleiben unverändert — nur die Geometrie ändert sich.
- **Umbruch:** bis 6 Geräte eine Spalte; darüber zwei Spalten; ab 13 Geräten wird die Schriftgröße
  reduziert und der Knotendurchmesser verkleinert. Es wird nie gescrollt und nie abgeschnitten.
- Der SVG-`viewBox` wird aus der tatsächlichen Knotenzahl berechnet, `preserveAspectRatio` sorgt
  für Skalierung; die Karte ist damit ohne Medienabfragen responsiv.

Kanten sind **quadratische Bézierkurven** zwischen den Knotenrändern, Kontrollpunkt auf halber
Strecke senkrecht zur Verbindung, damit sich Linien nicht überlagern.

---

## Zeichnung — `flow-svg.ts`

- **Linienstärke** proportional zur Leistung, mit Deckelung nach oben und unten:
  `strichbreite = min(BREITE_MAX, max(BREITE_MIN, leistung / maximalfluss × BREITE_MAX))`.
  `maximalfluss` ist der größte Kantenwert der aktuellen Zeichnung, nie kleiner als 100 W —
  sonst wird bei einer 5-Watt-Anlage jede Linie maximal dick.
- **Punktanimation:** ein `<circle>` je Kante, bewegt über `<animateMotion>` entlang desselben
  Pfades. Geschwindigkeit steigt mit der Leistung, gedeckelt auf einen Bereich, der ruhig bleibt.
  Kein Fluss = kein Punkt. Bei `anzeige.animation: false` entfallen alle Punkte.
- **`prefers-reduced-motion: reduce`** schaltet die Punktanimation ab — unabhängig von der
  Vertragseinstellung. Die Flussrichtung muss dann aus Pfeilspitzen ablesbar sein.
- **Knoten** sind Kreise mit `<ha-icon>` in der Mitte und Beschriftung darunter: Name, Wert,
  bei der Batterie zusätzlich der SoC als Ring um den Kreis.
- **HEMS-gesteuerte Geräte** bekommen einen zusätzlichen Ring in `--spfc-accent`. Maßgeblich ist
  `status.devices[id].runtime_active`: `true` heißt, das Gerät regelt gerade mit. Fehlt die
  Statusentität, gilt jedes Gerät aus `devices[]` als gesteuert — es steht ja nur dort, weil das
  HEMS es kennt. Bei `runtime_active: false` bleibt der Ring gestrichelt und der erste Eintrag aus
  `inactive_reasons` erscheint als Untertitel am Knoten (z. B. „Freigabe aus").
  Weil Zustand nie allein über Farbe transportiert wird, tragen Tooltip und
  Bildschirmleserbeschreibung den Zusatz „vom HEMS geregelt" beziehungsweise den Grund.

---

## Formatierung — `format.ts`

- Beträge unterhalb von `anzeige.watt_schwelle` in `W` ohne Nachkommastelle, darüber in `kW` mit
  einer Nachkommastelle. Dezimaltrennzeichen ist das Komma (`de-DE`).
- Unbekannte Werte erscheinen als `—`, niemals als `0 W`.
- Prozentwerte (SoC) ganzzahlig mit `%`.
- Zeitstempel aus dem Vertrag werden **unverändert** übernommen; sie sind bereits in Berliner Zeit
  als `TT.MM.JJJJ hh:mm:ss` formatiert. Die Karte formatiert Zeit nicht selbst um und hängt nie
  einen Zeitzonenzusatz an.

---

## Gestaltung — `styles.ts`

Token-Definition genau einmal, am Wurzelelement:

```css
:host {
  /* Aus dem HA-Theme, mit Rückfallwert für Themes, die sie nicht setzen */
  --spfc-surface: var(--card-background-color, #fff);
  --spfc-text:    var(--primary-text-color, #212121);
  --spfc-text-2:  var(--secondary-text-color, #727272);
  --spfc-border:  var(--divider-color, #e0e0e0);

  /* Eigene Flussfarben */
  --spfc-pv:      var(--energy-solar-color, #ff9800);
  --spfc-grid:    var(--energy-grid-consumption-color, #488fc2);
  --spfc-export:  var(--energy-grid-return-color, #8353d1);
  --spfc-battery: var(--energy-battery-out-color, #4db6ac);
  --spfc-house:   var(--energy-non-fossil-color, #0f9d58);

  /* Skytech-Akzent */
  --spfc-accent:  #18bcf2;
  --spfc-unknown: var(--disabled-text-color, #bdbdbd);
}
```

Die `--energy-*`-Variablen sind die Farben, die Home Assistant für seine eigenen Energiekarten
setzt — sie zu verwenden lässt die Karte im Dashboard zu Hause wirken und respektiert Themes, die
sie umdefinieren. Der Rückfallwert greift, wenn das Theme sie nicht kennt.

Weitere Regeln:

- Keine Literalfarbe außerhalb dieses Blocks.
- Keine gestaltenden Inline-Styles. Zulässig sind Inline-Werte nur für berechnete Geometrie —
  Pfadangaben, Strichbreiten, Positionen.
- Kontrast in hellen wie dunklen Themes mindestens 4,5:1 für Text, 3:1 für Linien und Ränder.
- Nichts animiert länger als nötig; Zustandswechsel (Ein-/Ausblenden einer Kante) in höchstens
  0,2 s.

---

## Fehlerzustände

Alle Meldungen deutsch, im Kartenrahmen, nie als leere Fläche und nie als Konsolenfehler allein.

| Fall | Anzeige |
|---|---|
| `config_entity` fehlt oder ist `unavailable` | *„Das Skytech HEMS veröffentlicht noch keine Kartendaten. Im HEMS-Panel unter ‚Flow Card' die Veröffentlichung einschalten."* |
| Attribute fehlen oder sind nicht lesbar | *„Die Kartendaten des Skytech HEMS sind unvollständig."* plus Name der betroffenen Entität |
| `schema_version` höher als unterstützt | *„Diese Karte ist älter als die Daten des Skytech HEMS. Bitte die Karte aktualisieren."* |
| `status_entity` fehlt | Kein Fehler. Kopfabzeichen und Rückfallebene entfallen still. |
| `hard_lockout: true` | Kopfabzeichen „HEMS gesperrt" |
| `ems_enabled: false` | Kopfabzeichen „HEMS aus" |
| `last_cycle_at` älter als das Fünffache des Regelintervalls | Kopfabzeichen „HEMS-Daten veraltet" mit Zeitpunkt |
| `devices` leer | Grafik ohne Geräteknoten. Kein Fehler — ein Haus ohne HEMS-Geräte ist gültig. |

---

## Interaktion und Barrierefreiheit

- **Tippen auf einen Knoten** öffnet den HA-More-Info-Dialog der Leitentität:
  ```ts
  const event = new Event('hass-more-info', { bubbles: true, composed: true })
  ;(event as any).detail = { entityId }
  this.dispatchEvent(event)
  ```
  Leitentität ist bei Geräten `power_entity` bzw. `switch_entity`, bei der Batterie `soc_entity`,
  bei PV der erste Eintrag aus `pv_power_entities`, beim Netz der Netzsensor. Knoten ohne
  Leitentität sind nicht anklickbar und dürfen keinen Klickzeiger zeigen.
- Jeder anklickbare Knoten ist über die Tastatur erreichbar (`tabindex="0"`, Auslösen mit Enter
  und Leertaste) und trägt ein `aria-label` in der Form
  *„Heizstab, 1,4 Kilowatt, vom HEMS geregelt"*.
- Das SVG trägt `role="img"` und eine `aria-label`-Zusammenfassung der aktuellen Bilanz, damit ein
  Bildschirmleser die Karte ohne die Einzelknoten erfassen kann.
- Rein dekorative Elemente (Animationspunkte, Verbindungslinien) sind `aria-hidden="true"`.

---

## Tests

Vitest, ohne DOM und ohne HA-Attrappe. Getestet werden die reinen Stufen; die Renderstufe wird
durch `tsc --noEmit` und Sichtprüfung abgesichert.

**`power.test.ts`** — je `power_kind` Normalfall, Fehlerfall und Leerfall:

- `test('watt liest den Sensor direkt')`
- `test('ampere rechnet mit drei Phasen und Spannungssensoren')`
- `test('ampere nimmt 230 V an, wenn kein Spannungssensor gesetzt ist')`
- `test('ampere fällt auf phases_fallback zurück, wenn phases_entity ungültig ist')`
- `test('binary_static liefert 0, wenn der Schalter aus ist')`
- `test('binary_static bevorzugt power_actual_entity vor static_power_w')`
- `test('battery_split bildet laden minus entladen')`
- `test('battery_signed dreht das Vorzeichen bei positiv_entladen')`
- `test('unavailable wird nicht zu 0, sondern zu unbekannt')`
- `test('Rückfallwert aus der Statusentität greift, wenn der Direktwert fehlt')`
- `test('unbekannter power_kind ergibt unbekannt statt Fehler')`

**`balance.test.ts`**:

- `test('Hausleistung wird gerechnet, wenn kein Hausensor gesetzt ist')`
- `test('negative Hausbilanz wird auf 0 geklemmt und gemeldet')`
- `test('Gerätesumme wird proportional auf die Hausleistung gedeckelt')`
- `test('PV deckt zuerst das Haus, dann die Batterie, dann das Netz')`
- `test('Kanten mit Wert 0 entstehen nicht')`
- `test('unbekannte Geräte zählen in der Summe mit 0, bleiben aber Knoten')`

**`layout.test.ts`**:

- `test('0 Geräte ergeben eine gültige Geometrie')`
- `test('1, 5 und 12 Geräte erzeugen jeweils überschneidungsfreie Knoten')`
- `test('ab 7 Geräten entstehen zwei Spalten')`
- `test('fehlender PV-Knoten hinterlässt kein Loch')`
- `test('haus_knoten_anzeigen false hängt die Geräte an den Verteilpunkt')`

Grundregeln: keine Netzzugriffe, keine Zeitabhängigkeit ohne übergebenen Zeitpunkt, ein Test prüft
eine Aussage, der Testname beschreibt sie.

---

## Auslieferung

- `hacs.json` mit `"name": "Skytech Power Flow Card"`, `"filename": "skytech-power-flow-card.js"`,
  `"render_readme": true`.
- `README.md` deutsch: Was die Karte tut, warum sie fast keine Konfiguration braucht, welche
  HEMS-Version vorausgesetzt wird (die erste mit veröffentlichten Kartendaten), Installation über
  HACS und von Hand, die drei optionalen YAML-Felder, ein Abschnitt „Wenn nichts angezeigt wird"
  mit den Fehlerzuständen von oben, und die Empfehlung, beide HEMS-Entitäten vom `recorder`
  auszuschließen.
- `release.yaml`: bei einem Tag `v*` `npm ci && npm run build` ausführen und
  `dist/skytech-power-flow-card.js` an das GitHub-Release hängen.
- Semantic Versioning. Der Datenvertrag koppelt die Repositories, nicht die Versionsnummer.

---

## Abnahmekriterien

1. Eine Karte, die mit **nur** `type: custom:skytech-power-flow-card` angelegt wurde, zeichnet die
   vollständige Anlage.
2. Ein im HEMS neu angelegtes Gerät erscheint auf der Karte, ohne dass das Dashboard angefasst
   wird. Ein auf „nicht anzeigen" gesetztes verschwindet.
3. Ein umbenanntes Gerät ändert seine Beschriftung, behält aber seine Position — die Identität
   hängt an `id`, nicht an `label`.
4. Ein auf `unavailable` gesetzter Sensor führt zu `—` und einer fehlenden Kante, **nicht** zu
   `0 W`.
5. Gestopptes Add-on: Die Karte zeichnet weiter aus den HA-Entitäten und zeigt das Abzeichen
   „HEMS-Daten veraltet".
6. Nach einem Home-Assistant-Neustart zeigt die Karte kurz den Klartexthinweis und kommt von
   selbst zurück, sobald das HEMS die Konfigurationsentität neu geschrieben hat.
7. Helles und dunkles Theme geprüft, dazu mindestens ein Theme mit abweichenden `--energy-*`-Farben.
8. Bei `prefers-reduced-motion: reduce` bewegt sich nichts, und die Flussrichtung bleibt trotzdem
   ablesbar.
9. Tastaturbedienung und Bildschirmleserausgabe geprüft.
10. `npm run typecheck`, `npm test` und `npm run build` sind grün; `dist/` enthält genau eine Datei.

---

## Nicht Bestandteil dieses Auftrags

- Schreibende Aktionen: Freigabe schalten, Priorität ändern, Modus umstellen. Die Karte öffnet den
  More-Info-Dialog, mehr nicht.
- Energie- statt Leistungsanzeige (kWh je Tag, Autarkiegrad, Eigenverbrauchsquote). Der Vertrag
  trägt heute reine Leistungswerte; Energiefelder wären eine additive Vertragserweiterung.
- Eine Konfigurationsoberfläche für Erzeugung, Netz, Speicher oder Geräte. Das ist ausdrücklich
  Aufgabe des HEMS-Panels — eine zweite Pflegestelle wäre eine zweite Wahrheit.
- Rückwärtskompatibilität zu `power-flow-card-plus`. Deren YAML-Konfiguration wird **nicht**
  gelesen.
- Unterstützung von Anlagen ohne Skytech HEMS. Ohne die Konfigurationsentität zeigt die Karte
  ihren Hinweis und sonst nichts.
