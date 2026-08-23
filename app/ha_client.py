import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp

from ems.ops import WriteOp, WriteResult

log = logging.getLogger(__name__)

# Im Add-on-Kontext wird SUPERVISOR_TOKEN automatisch injiziert.
# Für die lokale Entwicklung kann mit HA_URL / HA_TOKEN überschrieben werden.
_HA_URL = os.environ.get("HA_URL", "http://supervisor/core")
_HA_TOKEN = os.environ.get("HA_TOKEN", os.environ.get("SUPERVISOR_TOKEN", ""))


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
