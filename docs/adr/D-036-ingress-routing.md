# D-036: Relative Pfade und Hash-Routing wegen des HA-Ingress

- **Datum:** 13.08.2026
- **Status:** Aktiv
- **Betrifft:** `web/vite.config.ts`, `web/src/api.ts`, `web/src/main.tsx`, `app/main.py`

## Kontext

Home Assistant liefert die Oberfläche des Add-ons nicht unter `/` aus, sondern unter einem
Pfad, den der Supervisor je Sitzung erzeugt:

```text
/api/hassio_ingress/<token>/
```

Der `<token>`-Teil steht zur Bauzeit nicht fest und ändert sich. Die bisherige Vanilla-JS-Variante
hat das gelöst, indem sie ausschließlich relative Pfade ohne führenden Slash benutzt hat
(`fetch('api/status')`). Die Vorlage in [frontend.md](../frontend.md) beschreibt dagegen den
Normalfall: `base` fest gesetzt, API unter `/api/…`, `BrowserRouter` mit `basename`.

Ein absoluter Pfad wäre hier doppelt falsch: `/assets/index.js` zeigt am Ingress-Präfix vorbei
(404), und `/api/status` landet bei der REST-API von Home Assistant selbst statt beim Add-on.

## Betrachtete Optionen

### Option A — `<base href>` setzen und ansonsten bei der Vorlage bleiben

- Dafür: Näher an der Vorlage, `BrowserRouter` bliebe möglich.
- Dagegen: `<base>` wirkt gleichzeitig auf Links, relative Fetches und den Router. Fehler daraus
  sind schwer zuzuordnen, und für den Router bräuchte es zusätzlich einen zur Laufzeit
  ermittelten `basename` sowie einen SPA-Fallback im aiohttp-Router.

### Option B — Relative Pfade plus `HashRouter`

- Dafür: Keine Annahme über den Auslieferungspfad an irgendeiner Stelle; der Server braucht keinen
  Fallback, weil der Pfad nie über `/` hinausgeht. Entspricht dem, was heute schon funktioniert.
- Dagegen: Adressen enthalten ein `#`, und die Abweichung von der Vorlage muss dokumentiert sein —
  sonst „korrigiert" sie beim nächsten Mal jemand zurück.

## Entscheidung

**Option B.** Konkret:

| Thema | Festlegung |
|---|---|
| Assets | `base: './'` in `vite.config.ts` |
| API | `fetch(\`api${path}\`)` — relativ, **ohne** führenden Slash, ausschließlich in `api.ts` |
| Routing | `HashRouter` in `main.tsx` |
| Server | `GET /` liefert `app/static/index.html`, `/assets/` das Bundle — kein SPA-Fallback |

## Folgen

- **Positiv:** Die Oberfläche funktioniert unter Ingress, unter `http://localhost:8099` und hinter
  dem Vite-Dev-Proxy, ohne Konfiguration je Umgebung.
- **Negativ:** Adressen sind weniger schön (`…/#/steuerung`), und Deep-Links sind nur innerhalb der
  Ingress-Sitzung sinnvoll.
- **Aufwand:** Drei Zeilen Abweichung von der Referenz-SPA, jede mit Kommentar im Code und einem
  Abschnitt in [frontend.md](../frontend.md).

## Rücknahmebedingung

Wird die Oberfläche einmal außerhalb des Ingress unter einem festen Pfad ausgeliefert, entfällt der
Grund für das Hash-Routing und die Entscheidung wird ersetzt.
