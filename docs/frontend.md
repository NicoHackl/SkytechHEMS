# Frontend — Architektur und Muster

> Gilt für jede Web-Oberfläche des Projekts. Das **Aussehen** (Tokens, Klassen, Zustände) steht in
> [design-system.md](design-system.md) und wird hier nicht wiederholt. Hier steht, wie der Code
> aufgebaut ist.

Vorbild und Referenz sind die Admin-Oberflächen von `FCR_CMS` und
`FCR-Digitale-Stadion-Zeitung`. Wer hier abweicht, begründet es in
[design-entscheidungen.md](design-entscheidungen.md) — nicht im Code.

## Stack — festgelegt

| Baustein | Wahl | Warum |
|---|---|---|
| Bibliothek | React 18 | Bekannt, stabil, kein Framework-Overhead |
| Sprache | TypeScript, `strict: true` | Fehler zur Bauzeit statt im Betrieb |
| Bündler | Vite | Schneller Dev-Server, eingebauter Proxy |
| Routing | `react-router-dom` | Einzige Laufzeit-Abhängigkeit neben React |
| Styling | eine `styles.css` | siehe [design-system.md](design-system.md) |
| Zustand | React-Bordmittel (`useState`, Context) | Oberflächen dieser Größe brauchen keinen Store |
| Datenabruf | `fetch` in einem eigenen Modul | Ein typisierter Client ist kürzer als die Konfiguration einer Library |

**Nicht** verwendet und ohne ausdrückliche Entscheidung auch nicht einzuführen: Redux, Zustand,
MobX, React Query, SWR, Axios, Formik, React Hook Form, Tailwind, MUI, shadcn, Icon-Pakete.
Jede dieser Abhängigkeiten kostet mehr Wartung, als sie in einer Oberfläche mit 5–15 Seiten spart.

Neue Laufzeit-Abhängigkeit = Design-Entscheidung, siehe
[entwicklerrichtlinien.md](entwicklerrichtlinien.md).

## Verzeichnisstruktur

```text
web/
├── index.html              # nur die Hülle: #root + Modul-Script
├── package.json
├── tsconfig.json
├── vite.config.ts
└── src/
    ├── main.tsx            # Einstieg: Router + Provider + styles.css
    ├── App.tsx             # ausschliesslich die Routentabelle
    ├── styles.css          # das gesamte Design-System
    ├── api.ts              # typisierter API-Client (einziger fetch-Ort)
    ├── types.ts            # Datenverträge zum Backend
    ├── format.ts           # Anzeigeformate (Leistung, Dauer, Modus-Labels)
    ├── components/         # wiederverwendbar: Layout, Theme, Toast, Icon, DeviceCard, …
    └── pages/              # eine Datei je Route
```

Der Build schreibt nach `../app/static/` — dorthin, wo aiohttp ausliefert. Das erzeugte Bundle ist
eingecheckt (D-035); `web/` enthält ausschließlich Quellen.

Regel: `pages/` kennt `components/`, nie umgekehrt. Wächst eine Seite über ~150 Zeilen, wandert
der wiederverwendbare Teil nach `components/`.

Wird der Client in mehreren Anwendungen gebraucht (Frontend **und** Server), liegt das Datenmodell
in einem gemeinsamen Ordner (`shared/`) und wird per Pfad-Alias eingebunden — siehe
[architektur.md](architektur.md).

## Einstieg und Provider

`main.tsx` verdrahtet nur; es enthält keine Logik. Reihenfolge der Provider ist verbindlich:
Router außen, dann Theme, dann Toast, dann Auth — Theme hängt an nichts und alles darunter darf es
lesen, Auth meldet Fehler über Toasts und kann deshalb nicht über dem Toast-Provider liegen.

```tsx
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>             {/* HashRouter statt BrowserRouter — siehe „Ingress" */}
      <ThemeProvider>        {/* Pflicht — siehe „Hell und Dunkel" */}
        <ToastProvider>
          <App />            {/* kein AuthProvider: die Anmeldung macht der Ingress */}
        </ToastProvider>
      </ThemeProvider>
    </HashRouter>
  </StrictMode>,
)
```

## Hell und Dunkel

Der Schalter ist Pflicht — eiserne Regel 11 in [`../AGENTS.md`](../AGENTS.md). Die Farbwerte dazu
stehen in [design-system.md](design-system.md), hier steht nur die Mechanik.

`components/Theme.tsx` liefert drei Dinge und **keine einzige Farbe**:

| Export | Aufgabe |
|---|---|
| `ThemeProvider` | Setzt `data-theme` am `<html>`, speichert die Wahl in `localStorage`, folgt der Systemvorgabe nur so lange, wie der Nutzer nicht selbst gewählt hat |
| `useTheme()` | `{ theme, setTheme, toggleTheme }`; wirft außerhalb des Providers einen verständlichen Fehler |
| `ThemeSwitch` | Der Knopf selbst, `.icon-btn` mit `aria-pressed` und `aria-label` |

Verbindlich daran:

- `ThemeSwitch` sitzt in `PageHeader`, nicht in der Sidebar — die fährt unter 820px aus dem Bild,
  der Schalter muss aber auf jeder Seite erreichbar bleiben.
- `index.html` trägt ein kurzes Inline-Skript im `<head>`, das `data-theme` **vor** dem ersten
  Frame setzt. Ohne das blitzt die helle Oberfläche auf, bevor React geladen ist.
- Der Provider schreibt ausschließlich das Attribut. Wer im TSX auf `theme === 'dark'` verzweigt,
  um eine Farbe zu wählen, hat das System umgangen — die Verzweigung gehört in `styles.css`.
- Ein Icon oder Bild, das nur in einem Modus lesbar ist, wird über `currentColor` gelöst, nicht
  über zwei Dateien.

## Routing

`App.tsx` enthält **nur** die Routentabelle, keinen Zustand und kein Markup außer der
Fallback-Route. Das Layout ist eine Elternroute mit `<Outlet />`, damit Sidebar und Kopfzeile beim
Seitenwechsel nicht neu montiert werden.

```tsx
<Routes>
  <Route element={<Layout />}>
    <Route path="/" element={<Status />} />
    <Route path="/steuerung" element={<Steuerung />} />
    <Route path="/energy-pilot" element={<EnergyPilot />} />
    <Route path="/konfiguration/global" element={<KonfigurationGlobal />} />
    <Route path="/konfiguration/geraete" element={<KonfigurationGeraete />} />
    <Route path="/konfiguration/geraete/neu" element={<KonfigurationGeraet mode="create" />} />
    <Route path="/konfiguration/geraete/:index" element={<KonfigurationGeraet mode="edit" />} />
    <Route path="*" element={<div className="content"><div className="empty">Seite nicht gefunden.</div></div>} />
  </Route>
</Routes>
```

Die Geräteliste ist der einzige Datentyp der Anwendung und folgt dem Muster der Vorlage:
**Liste** (`/konfiguration/geraete`), **Anlegen** (`.../neu`), **Bearbeiten** (`.../:index`), wobei
Anlegen und Bearbeiten sich eine Komponente mit `mode: 'create' | 'edit'` teilen. Der Index ist
dabei ausdrücklich nur die **Entwurfsposition** — die fachliche Identität bleibt `name`.

Zugriffsschutz gibt es im Frontend nicht: Die Anmeldung erledigt der HA-Ingress, bevor die Seite
überhaupt ausgeliefert wird — siehe [sicherheit-datenschutz.md](sicherheit-datenschutz.md).

## Konfigurationsentwurf

Der Entwurf der Add-on-Optionen ist der einzige Zustand, den sich mehrere Seiten teilen. Er liegt
in `components/ConfigDraft.tsx` als React-Context — kein State-Paket, dafür ist ein Objekt zu
wenig. Verbindlich daran:

- Der Provider steht in `main.tsx` **über** dem Layout. Sonst verwürfe ein Seitenwechsel den
  Entwurf, und die Navigation könnte nicht vor ungespeicherten Änderungen warnen.
- Geladen wird erst, wenn eine Konfigurationsseite `ensureLoaded()` ruft. Wer nur den Status
  ansieht, löst keinen zusätzlichen Abruf aus.
- `dirty` speist drei Dinge: einen Punkt am Navigationseintrag, den `beforeunload`-Hinweis des
  Browsers und die Rückfrage vor „Neu starten".
- Ein `409` verwirft den Entwurf **nicht**. `conflict` schaltet eine `.alert` frei, die erklärt,
  was passiert ist, und gezieltes Neuladen anbietet.
- Nach einem ausgelösten Neustart pollt der Provider `/api/status`, bis eine **andere**
  `instance_id` antwortet. Solange liegt ein nicht interaktiver Neustartzustand über der Seite.

Die Formularbausteine (`Field`, `NumberField`, `TextField`, `SelectField`, `EntityField`,
`ModeChecks`) stehen in `components/ConfigFields.tsx`, die klassenspezifischen Abschnitte in
`components/DeviceFields.tsx`, die Aktionsleiste in `components/ConfigActions.tsx` und die
Zustandsliste der abgeleiteten Helfer in `components/HelferStatus.tsx`. Ohne diese Aufteilung
wüchse allein das Geräteformular weit über 150 Zeilen.

Zwei Muster, die dabei nicht verhandelbar sind:

- **Die Entitätsauswahl ist ein `datalist`, kein eigenes Widget.** Die Eingabe bleibt frei, damit
  eine noch nicht angelegte Entität eintragbar ist; Tastatur und Screenreader funktionieren ohne
  Zutun. Ein gespeicherter Wert, den es aktuell nicht gibt, wird **mit Warnung angezeigt** und
  niemals stillschweigend gelöscht.
- **Abgeleitete Entity-IDs kommen vom Server.** `HelferStatus` liest sie aus
  `/api/device_controls_schema`, nicht aus einer im Frontend nachgebauten Namenskonvention — zwei
  Quellen dafür liefen auseinander.

## API-Client

Genau **ein** Modul ruft `fetch` auf. Keine Seite und keine Komponente ruft direkt `fetch` — sonst
liegen Basis-Pfad, Header, Token und Fehlerbehandlung verstreut im Code.

Aufbau:

```ts
export class ApiError extends Error {
  constructor(message: string, public status: number, public details?: unknown) { super(message) }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  // Token, falls vorhanden: headers.set('Authorization', `Bearer ${token}`)
  // Ohne führenden Slash — der Ingress-Pfad ist erst zur Laufzeit bekannt (D-036).
  const response = await fetch(`api${path}`, { ...options, headers })
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = isJson ? (body as { detail?: unknown }).detail : body
    const message = typeof detail === 'string' ? detail : `Anfrage fehlgeschlagen (${response.status}).`
    throw new ApiError(message, response.status, detail)
  }
  return body as T
}

export const api = {
  slides: () => request<Slide[]>('/slides'),
  createSlide: (data: SlideInput) => request<{ id: number }>('/slides', { method: 'POST', body: JSON.stringify(data) }),
  deleteSlide: (id: number) => request<{ success: boolean }>(`/slides/${id}`, { method: 'DELETE' }),
}
```

Verbindlich daran:

- `Content-Type` wird bei `FormData` **nicht** gesetzt — sonst fehlt die Multipart-Boundary und der
  Upload schlägt fehl.
- Jeder Aufruf ist ein benannter Eintrag im `api`-Objekt, kein roher Pfad in der Seite.
- Rückgabetypen kommen aus `types.ts` und spiegeln den Vertrag aus
  [api-referenz.md](api-referenz.md).
- Fehlertexte sind deutsch und benennen die Ursache; `ApiError` trägt zusätzlich `status` und
  `details`, damit Feldfehler des Servers dem richtigen Feld zugeordnet werden können.
- Es gibt keine Token-Behandlung: die Anmeldung liegt beim Ingress. Ein `401` kann hier nur
  auftreten, wenn die Ingress-Sitzung abgelaufen ist — dann hilft nur Neuladen, und genau das sagt
  die Fehlermeldung.

## Seitenmuster: Liste

Ladezustand wird über `null` unterschieden, nicht über ein zweites `loading`-Flag — `null` heißt
„noch nicht geladen", `[]` heißt „leer".

```tsx
const [rows, setRows] = useState<Slide[] | null>(null)
const [busy, setBusy] = useState<number | null>(null)
const { toast } = useToast()
const load = useCallback(() => api.slides().then(setRows).catch((err: Error) => toast(err.message, 'err')), [toast])
useEffect(() => { void load() }, [load])
```

Für Aktionen auf einer Zeile eine gemeinsame Hilfsfunktion: Zeile sperren, ausführen, Rückmeldung,
neu laden, entsperren — auch im Fehlerfall (`finally`).

Drei Zustände, immer alle drei umgesetzt:

| Zustand | Darstellung |
|---|---|
| Laden | `<div className="center"><div className="spinner" /></div>` |
| Leer | `.empty` in einer Karte: Icon, ein erklärender Satz, Primäraktion („Erste Folie anlegen") |
| Gefüllt | Tabelle (`table.data`) bei gleichförmigen Daten, Kartenliste bei Datensätzen mit Vorschau oder Sortierung |

Ein Leerzustand ohne Weg zur ersten Aktion ist eine Sackgasse und gilt als Fehler.

## Seitenmuster: Gerätekarte

`components/DeviceCard.tsx` liefert die gemeinsame Form: Titel, optionale Badges, darunter
Kennzahlzeilen (`KeyValue`). Die Seiten Status und Energy Pilot benutzen dieselbe Karte — welche
Zeilen darin stehen, entscheidet die aufrufende Seite.

Drei Gerätetypen, drei Karten in `pages/Status.tsx`, unterschieden über das diskriminierende Feld
`type` aus `types.ts`:

| Typ | Karte | Kartenzustand |
|---|---|---|
| `controllable` | `ControllableCard` | `off` / `active` / `idle` |
| `binary` | `BinaryCard` | `off` / `active` / `idle` |
| `battery` | `BatteryCard` | `off` / `charge` / `discharge` / `idle` |

**Drei verschiedene „inaktiv" auseinanderhalten.** `eligible: false` ist die Freigabeentscheidung
dieses Zyklus und darf nicht wie ein Fehler aussehen. `runtime_active: false` heißt „technisch
nicht regelbar" — Schreibziel fehlt oder Schreiben schlug fehl — und bekommt den Grund aus
`inactive_reasons` als Klartext. Ein Eintrag aus `inactive_devices` wurde beim Start gar nicht
erst registriert; für ihn werden **keine** Leistungs-, SoC- oder Schaltwerte erfunden.

Der Abschnitt „Speicher" steht **vor** „Regelbare Verbraucher": der Speicher beeinflusst die
Pool-Rechnung, beim Debuggen will man ihn zuerst sehen.

Zwei Muster, die die Speicherkarte zusätzlich braucht:

- **Signierte Werte als Betrag plus Richtung anzeigen.** `netto_w` ist positiv beim Laden und
  negativ beim Entladen. In der Karte steht `1.760 W (Entladen)`, nicht `-1760 W` — das Vorzeichen
  ist Datenvertrag, keine Anzeigeform.
- **Technische Sperrgründe übersetzen.** `blockiert_grund` und die beiden Pfad-Felder liefern
  Schlüssel wie `wr_derating`. Die Karte bildet sie über eine Map auf deutschen Klartext ab;
  ein unbekannter Schlüssel wird unverändert gezeigt, statt zu verschwinden. Dasselbe gilt für
  `inactive_reasons` — dort ist der Unterschied zwischen einem fehlenden Schreibziel und einem
  fehlgeschlagenen Schreibversuch die ganze Information.
- **Der SoC-Balken trägt zwei Marker**, Minimum und Ladeschluss. Eine Notstromreserve gibt es
  nicht mehr; ein dritter Marker behauptete eine Grenze, die keine Wirkung hat.

## Seitenmuster: Formular

- Ein Zustandsobjekt für den Datensatz, geändert über eine `patch(partial)`-Funktion.
- `saving`-Flag sperrt den Speichern-Button und wechselt seine Beschriftung auf „Speichern…".
- Feldfehler kommen als `Record<string, string>` vom Server, landen in `fieldErrors` und färben
  gezielt das betroffene Feld (`.field.invalid` + `.field-error`). Ein globaler Toast ersetzt keine
  Feldmarkierung.
- Der API-Client bewahrt bei einer Fehlerantwort den vollständigen JSON-Rumpf als `ApiError.details`
  auf. Bei `422` gingen `field_errors` sonst verloren. Geänderte Entwürfe werden verzögert über
  `/api/config/validate` erneut geprüft; eine langsamere alte Antwort darf keine neuere ersetzen.
- Ein im Geräteformular lokal korrigiertes Feld zeigt seinen alten Serverfehler sofort nicht mehr.
  Nach **Übernehmen** prüft der Server den gesamten Entwurf erneut und zeigt verbleibende Fehler.
- Die Geräteliste bewertet zuerst den aktuellen Entwurf. Ein gegenüber dem geladenen Stand
  korrigiertes, fehlerfreies Gerät trägt „Gültiger Entwurf" und nicht den veralteten Laufzeitstatus
  „Beim Start übersprungen". Nach erfolgreichem Speichern werden die alten
  `inactive_devices`-Einträge aus dem UI-Zustand entfernt.
- Nach dem Speichern: Toast **und** Rücknavigation zur Liste.
- Formularaufbau folgt dem Server-Schema, wo eines existiert: Feldtyp → Widget. Zwei Quellen für
  „welche Felder hat dieser Datensatz" laufen sonst auseinander.
- Zerstörende Aktionen bestätigen mit dem Namen des Objekts:
  `window.confirm('„' + titel + '" wirklich löschen?')`.

## Rückmeldung an den Nutzer

| Mittel | Wofür |
|---|---|
| Toast (`ok` / `err`) | Ergebnis einer Aktion: gespeichert, gelöscht, fehlgeschlagen. Verschwindet nach ~4 s |
| `.alert` | Fehler, der die ganze Seite betrifft und stehen bleiben muss |
| `.field-error` | Fehler an genau einem Eingabefeld |
| `.pill.warn` an einer Helfer-Zeile | Der HA-Helfer wirkt gerade nicht — Add-on-Wert oder interner Default greift |
| `.hint-box` | Fehlende Voraussetzung plus Knopf, der sie herstellt |
| `.info-strip` | Erklärung zur Bedienung einer Liste, kein Fehler |

Der Toast-Provider stellt einen `useToast()`-Hook bereit und wirft außerhalb des Providers einen
verständlichen Fehler statt `undefined` zurückzugeben.

## Layout

`components/Layout.tsx` liefert zwei Dinge:

1. `Layout` — Sidebar (Marke, Navigationsgruppen mit Zählern, Fußbereich) plus `<main>` mit
   `<Outlet />`. Unter 820px als Off-Canvas-Panel mit Hintergrund-Backdrop.
2. `PageHeader` — die klebrige Kopfzeile jeder Seite: `title`, optional `subtitle`, den
   `ThemeSwitch` und optional `actions` (die Primäraktion der Seite).

Jede Seite rendert `<PageHeader …/>` gefolgt von `<div className="content">`. Keine Seite baut sich
eine eigene Kopfzeile.

Zähler in der Navigation kommen aus einem Sammelaufruf beim Montieren des Layouts; schlägt er fehl,
verschwindet nur der Zähler, nicht die Navigation.

## Besonderheiten unter HA-Ingress

Die Oberfläche wird nicht unter `/` ausgeliefert, sondern unter einem Pfad, den Home Assistant je
Sitzung erzeugt: `/api/hassio_ingress/<token>/`. Dieser Pfad ist zur **Bauzeit unbekannt**. Daraus
folgen drei Festlegungen (D-036), die von der Vorlage abweichen und deshalb nicht „aufgeräumt"
werden dürfen:

| Thema | Festlegung | Warum |
|---|---|---|
| Assets | `base: './'` in `vite.config.ts` | Ein absoluter Pfad (`/assets/…`) zeigt am Ingress-Präfix vorbei und liefert 404 |
| API-Aufrufe | relativ **ohne** führenden Slash: `fetch('api/status')` | `/api/status` landet bei Home Assistant selbst, nicht beim Add-on |
| Routing | `HashRouter` | Bei `BrowserRouter` müsste aiohttp für jeden Unterpfad die `index.html` ausliefern, obwohl es das Ingress-Präfix nicht kennt |

Ein `<base href>`-Tag wäre die Alternative zum Hash-Routing gewesen; es wurde verworfen, weil es
relative Fetches und Router zugleich beeinflusst und Fehler dann schwer zuzuordnen sind.

## Konfiguration und Auslieferung

```ts
// vite.config.ts
export default defineConfig({
  base: './',                            // Pflicht unter Ingress — siehe oben
  plugins: [react()],
  build: {
    outDir: '../app/static',             // aiohttp liefert von dort aus
    emptyOutDir: true,
  },
  server: {
    port: 5174,                          // Port je Anwendung festlegen, nicht raten
    proxy: {                             // Dev: gleiche Origin wie in Produktion, kein CORS
      '/api': { target: 'http://127.0.0.1:8099', changeOrigin: true },
    },
  },
})
```

- Der Build prüft erst Typen, dann bündelt er: `"build": "tsc --noEmit && vite build"`. Ein Build,
  der Typfehler durchlässt, ist wertlos.
- Keine absolute Basis-URL im Code, keine `VITE_API_URL`-Variable — Dev-Proxy und Ingress
  erledigen das.
- Ausgeliefert wird direkt vom Anwendungsserver: `GET /` liefert `app/static/index.html`, die
  Assets kommen unter `/assets/`. Kein zweiter Webserver, kein SPA-Fallback nötig.
- Das gebaute Bundle wird eingecheckt (D-035) — der Add-on-Build auf dem HA-Host hat kein Node.js.
- `index.html` enthält `lang="de"`, `data-design="ha"` am `<html>`, das Theme-Inline-Skript,
  `viewport`, einen sprechenden `<title>`, `<meta name="theme-color">` und
  `<meta name="robots" content="noindex, nofollow">`.

## Was ein Agent vor dem ersten Commit prüft

1. `tsc --noEmit` läuft fehlerfrei — `any` ist keine Lösung, sondern eine verschobene Fehlermeldung.
2. Kein direkter `fetch` außerhalb von `api.ts`.
3. Keine Literalfarbe und kein gestaltender Inline-Style im TSX.
4. Lade-, Leer- und Fehlerzustand jeder neuen Seite sind umgesetzt.
5. Jeder Button ohne sichtbaren Text hat ein `aria-label`.
6. Die Ansicht ist bei 375px Breite bedienbar.
7. Die Designsprache war geklärt, bevor gebaut wurde — nicht geraten (eiserne Regel 10).
8. Der Theme-Schalter ist erreichbar, und **jede neue Seite wurde in beiden Modi angesehen**.
   Ein Kontrastfehler fällt nur auf, wer hinschaut.
