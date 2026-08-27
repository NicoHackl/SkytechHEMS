import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from ems.ops import WriteOp, WriteResult

log = logging.getLogger(__name__)

# Im Add-on-Kontext wird SUPERVISOR_TOKEN automatisch injiziert.
# Für die lokale Entwicklung kann mit HA_URL / HA_TOKEN überschrieben werden.
_HA_URL = os.environ.get("HA_URL", "http://supervisor/core")
_HA_TOKEN = os.environ.get("HA_TOKEN", os.environ.get("SUPERVISOR_TOKEN", ""))

# Die Dashboard-Liste gibt Home Assistant ausschliesslich ueber WebSocket
# heraus; einen REST-Endpunkt dafuer gibt es nicht (D-049).
_WS_URL = (_HA_URL.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
           + "/api/websocket")
_WS_TIMEOUT_S = 10

# url_path des Standard-Dashboards. In lovelace/dashboards/list taucht es
# nicht auf -- es wird mit url_path None abgefragt und heisst im Adressfeld so.
STANDARD_DASHBOARD = "lovelace"


class HAClient:
    """REST-Client für Home Assistant.

    Hält eine einzige, langlebige aiohttp-Session für alle Anfragen, damit
    Connection-Pooling und Keep-Alive genutzt werden (eine Session pro Anwendung).
    """

    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {_HA_TOKEN}",
            "Content-Type": "application/json",
        }
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        """Liefert die gemeinsam genutzte Session und erstellt sie bei Bedarf neu."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self._headers)
        return self._session

    async def close(self) -> None:
        """Schließt die Session sauber (beim Herunterfahren aufzurufen)."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def fetch_all_states(self) -> Dict[str, Dict]:
        """Liefert {entity_id: {state, attributes, last_changed}}."""
        url = f"{_HA_URL}/api/states"
        session = self._get_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"HA /api/states returned {resp.status}: {text[:200]}")
            states_list = await resp.json()

        return {
            s["entity_id"]: {
                "state": s.get("state"),
                "attributes": s.get("attributes", {}),
                "last_changed": s.get("last_changed"),
            }
            for s in states_list
        }

    async def call_service(self, domain: str, service: str,
                           data: Optional[Dict[str, Any]] = None) -> None:
        """Setzt einen einzelnen HA-Service-Aufruf ab.

        Wirft RuntimeError bei Nicht-2xx-Status oder Netzwerkfehler.
        """
        url = f"{_HA_URL}/api/services/{domain}/{service}"
        session = self._get_session()
        async with session.post(
            url,
            json=data or {},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                raise RuntimeError(
                    f"HA service {domain}.{service} returned {resp.status}: {text[:200]}"
                )

    async def execute_write_ops(self, write_ops: List[WriteOp]) -> List[WriteResult]:
        """Führt die Operationen aus und meldet je Operation Erfolg oder Fehler.

        Ein Nicht-2xx-Status wird NICHT mehr verschluckt: der Aufrufer ordnet den
        Fehler über `WriteOp.owner` dem verursachenden Gerät zu und macht ihn im
        Status sichtbar. Geworfen wird trotzdem nicht – ein kaputtes Schreibziel
        darf die übrigen Geräte nicht mitreißen.
        """
        results: List[WriteResult] = []
        if not write_ops:
            return results
        session = self._get_session()
        for op in write_ops:
            url = f"{_HA_URL}/api/services/{op.domain}/{op.service}"
            try:
                async with session.post(
                    url,
                    json=op.data,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status in (200, 201):
                        results.append(WriteResult(op, True))
                        continue
                    error = f"HTTP {resp.status}"
                    log.warning("Service %s.%s (%s) → %s",
                                op.domain, op.service, op.owner or "global", error)
            except Exception as exc:
                error = str(exc)
                log.error("Service-Aufruf %s.%s (%s) fehlgeschlagen: %s",
                          op.domain, op.service, op.owner or "global", error)
            results.append(WriteResult(op, False, error))
        return results

    async def set_state(self, entity_id: str, state: str,
                        attributes: Optional[Dict[str, Any]] = None) -> bool:
        """Schreibt einen Zustand direkt in die HA-Zustandsmaschine.

        Ausschließlich für die Anzeigedaten der Flow Card (D-046). Der Regelpfad
        schreibt weiterhin nur input_*-Helfer über Service-Aufrufe; die hier
        erzeugten sensor.*-Entitäten schalten kein Gerät.

        Wirft nie: ein fehlgeschlagener Anzeigeschrieb darf den Regelzyklus
        nicht abbrechen. Liefert True bei Erfolg, sonst False.
        """
        url = f"{_HA_URL}/api/states/{entity_id}"
        payload: Dict[str, Any] = {"state": state, "attributes": attributes or {}}
        try:
            session = self._get_session()
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status in (200, 201):
                    return True
                log.warning("Zustand %s konnte nicht geschrieben werden → HTTP %s",
                            entity_id, resp.status)
        except Exception as exc:
            log.warning("Zustand %s konnte nicht geschrieben werden: %s", entity_id, exc)
        return False

    async def list_dashboards(self) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Dashboards samt Ansichten, fuer die Zielauswahl im Panel (D-049).

        Home Assistant gibt die Lovelace-Konfiguration ausschliesslich ueber
        WebSocket heraus; einen REST-Endpunkt dafuer gibt es nicht. Das ist die
        einzige Stelle im Add-on, die WebSocket spricht.

        Wirft nie: die Zielauswahl ist Bequemlichkeit, kein Regelpfad. Faellt
        sie aus, faellt die Oberflaeche auf ein Textfeld zurueck.
        """
        if not _HA_TOKEN:
            return [], ["Ohne Zugangstoken lassen sich die Dashboards nicht lesen."]
        try:
            return forme_dashboards(await self._hole_dashboard_rohdaten())
        except asyncio.TimeoutError:
            log.warning("Dashboards: Zeitueberschreitung beim WebSocket")
            return [], ["Home Assistant hat nicht rechtzeitig geantwortet."]
        except Exception as exc:
            log.warning("Dashboards konnten nicht gelesen werden: %s", exc)
            return [], ["Die Dashboards konnten nicht gelesen werden."]

    async def _hole_dashboard_rohdaten(
        self,
    ) -> List[Tuple[Dict[str, Any], Optional[Dict[str, Any]], str]]:
        """Der reine Protokollteil: verbinden, anmelden, abfragen."""
        session = self._get_session()
        async with session.ws_connect(_WS_URL) as ws:
            await self._anmelden(ws)

            naechste_id = 1

            async def frage(nutzlast: Dict[str, Any]) -> Dict[str, Any]:
                nonlocal naechste_id
                kennung = naechste_id
                naechste_id += 1
                await ws.send_json({"id": kennung, **nutzlast})
                while True:
                    nachricht = await asyncio.wait_for(
                        ws.receive_json(), timeout=_WS_TIMEOUT_S)
                    if nachricht.get("id") == kennung and nachricht.get("type") == "result":
                        return nachricht

            liste = await frage({"type": "lovelace/dashboards/list"})
            # Das Standard-Dashboard steht nicht in der Liste.
            metadaten: List[Dict[str, Any]] = [{"url_path": None, "title": "Übersicht"}]
            if liste.get("success"):
                metadaten += [eintrag for eintrag in (liste.get("result") or [])
                              if isinstance(eintrag, dict)]

            rohdaten: List[Tuple[Dict[str, Any], Optional[Dict[str, Any]], str]] = []
            for meta in metadaten:
                antwort = await frage({
                    "type": "lovelace/config", "url_path": meta.get("url_path"),
                })
                if antwort.get("success"):
                    rohdaten.append((meta, antwort.get("result") or {}, ""))
                else:
                    fehler = (antwort.get("error") or {}).get("message") or "unbekannt"
                    rohdaten.append((meta, None, str(fehler)))
            return rohdaten

    async def _anmelden(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Der Anmeldewechsel von Home Assistant: auth_required, auth, auth_ok."""
        gruss = await asyncio.wait_for(ws.receive_json(), timeout=_WS_TIMEOUT_S)
        if gruss.get("type") != "auth_required":
            raise RuntimeError(f"Unerwartete Begruessung: {gruss.get('type')}")
        await ws.send_json({"type": "auth", "access_token": _HA_TOKEN})
        antwort = await asyncio.wait_for(ws.receive_json(), timeout=_WS_TIMEOUT_S)
        if antwort.get("type") != "auth_ok":
            raise RuntimeError("Anmeldung am WebSocket abgelehnt")


# ---------------------------------------------------------------------------
# Dashboards und Ansichten
# ---------------------------------------------------------------------------

def forme_dashboards(
    rohdaten: List[Tuple[Dict[str, Any], Optional[Dict[str, Any]], str]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Bringt die WebSocket-Antworten in die Form, die das Panel braucht.

    `rohdaten` ist je Dashboard ein Tripel aus Metadaten, Konfiguration und
    Fehlertext. Bewusst eine reine Funktion neben dem Socket: nur so laesst
    sich pruefen, was bei Strategie- und YAML-Dashboards herauskommt.
    """
    dashboards: List[Dict[str, Any]] = []
    warnungen: List[str] = []

    for meta, config, fehler in rohdaten:
        url_path = _text(meta.get("url_path")) or STANDARD_DASHBOARD
        titel = _text(meta.get("title")) or url_path

        if fehler:
            # YAML-Dashboards antworten je nach Konfiguration mit einem Fehler.
            dashboards.append({"url_path": url_path, "title": titel, "views": []})
            warnungen.append(
                f"Die Ansichten von „{titel}“ konnten nicht gelesen werden.")
            continue

        views = (config or {}).get("views")
        if not isinstance(views, list):
            # Strategie-Dashboards bauen ihre Ansichten erst im Browser.
            dashboards.append({"url_path": url_path, "title": titel, "views": []})
            warnungen.append(
                f"„{titel}“ ist ein Strategie-Dashboard und hat keine "
                "einzelnen Ansichten.")
            continue

        dashboards.append({
            "url_path": url_path,
            "title": titel,
            # Eine Ansicht ohne Pfad ist ueber ihre Position erreichbar.
            "views": [
                {
                    "path": _text(view.get("path")) or str(index),
                    "title": _text(view.get("title")) or _text(view.get("path")) or str(index),
                }
                for index, view in enumerate(views) if isinstance(view, dict)
            ],
        })

    return dashboards, warnungen


def _text(wert: Any) -> str:
    return "" if wert is None else str(wert).strip()
