"""Zugriff auf die EIGENEN Add-on-Optionen über die Supervisor-API.

`/data/options.json` wird ausschließlich gelesen und niemals beschrieben.
Geschrieben wird über `http://supervisor/addons/self/…` – dieselbe Quelle, die
auch die native Add-on-Konfigurationsseite bedient. Eine zweite
Konfigurationsdatei gäbe es sonst, und die beiden liefen auseinander.

Die Informationsaufrufe sind mit der Default-Rolle erlaubt. Änderungen der
eigenen Optionen und der eigene Neustart brauchen die Manager-Rolle; das
Manifest fordert sie ausdrücklich an.

Referenzen:
- https://developers.home-assistant.io/docs/api/supervisor/endpoints/
- https://developers.home-assistant.io/docs/apps/configuration/
"""

import logging
import os
from typing import Any, Dict, Optional, Tuple

import aiohttp

log = logging.getLogger(__name__)

# Im Add-on-Kontext injiziert der Supervisor SUPERVISOR_TOKEN. Fehlt er, läuft
# der Prozess außerhalb des Containers: dann gibt es keine Schreibschnittstelle,
# und die Oberfläche schaltet sichtbar in einen Nur-Lese-Modus.
_SUPERVISOR_URL = os.environ.get("SUPERVISOR_URL", "http://supervisor")
_SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

_TIMEOUT_S = 10
_RESTART_TIMEOUT_S = 30


class SupervisorUnavailable(RuntimeError):
    """Der Supervisor ist nicht erreichbar oder nicht konfiguriert."""


class SupervisorRejected(RuntimeError):
    """Der Supervisor hat die Anfrage fachlich abgelehnt."""


class SupervisorPermissionDenied(SupervisorRejected):
    """Der Supervisor verweigert einen Aufruf wegen der Add-on-Rolle."""


class SupervisorClient:
    """Dünner Client für die vier benötigten `self`-Endpunkte.

    Hält eine einzige, langlebige aiohttp-Session. Token, Header und rohe
    Optionsdaten tauchen niemals in Logs oder Fehlermeldungen auf – eine
    Optionsliste kann Entity-IDs und damit Rückschlüsse auf die Anlage
    enthalten, und der Token ist ein Vollzugriff auf den Supervisor.
    """

    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None) -> None:
        self._token = _SUPERVISOR_TOKEN if token is None else token
        self._base_url = (base_url or _SUPERVISOR_URL).rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def available(self) -> bool:
        """Gibt es überhaupt eine Schreibschnittstelle?"""
        return bool(self._token)

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            })
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Endpunkte
    # ------------------------------------------------------------------

    async def get_self_info(self) -> Dict[str, Any]:
        """Aktuelle Add-on-Informationen einschließlich der gespeicherten Optionen."""
        return await self._request("GET", "/addons/self/info")

    async def validate_self_options(self, options: Dict[str, Any]) -> Tuple[bool, str]:
        """Prüft die Optionen gegen das Manifest-Schema.

        Der Endpunkt erwartet die rohen Optionsdaten, nicht das `options`-Objekt.
        """
        data = await self._request("POST", "/addons/self/options/validate",
                                   payload=options, timeout=_TIMEOUT_S)
        return bool(data.get("valid", False)), str(data.get("message") or "")

    async def save_self_options(self, options: Dict[str, Any]) -> None:
        """Speichert die Optionen. Startet das Add-on ausdrücklich NICHT neu."""
        await self._request("POST", "/addons/self/options", payload={"options": options})

    async def restart_self(self) -> None:
        """Startet das eigene Add-on neu. Der Prozess endet dabei."""
        await self._request("POST", "/addons/self/restart", timeout=_RESTART_TIMEOUT_S)

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    async def _request(self, method: str, path: str, *,
                       payload: Optional[Dict[str, Any]] = None,
                       timeout: int = _TIMEOUT_S) -> Dict[str, Any]:
        if not self.available:
            raise SupervisorUnavailable(
                "Kein Supervisor-Zugang: das Add-on läuft außerhalb von Home Assistant."
            )
        session = self._get_session()
        url = f"{self._base_url}{path}"
        try:
            async with session.request(
                method, url,
                json=payload if payload is not None else None,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                body = await self._read_body(response)
                if response.status >= 400 or body.get("result") == "error":
                    if response.status == 403:
                        message = (
                            "Der Supervisor verweigert den Zugriff (HTTP 403). "
                            "Das installierte Add-on besitzt nicht die erforderliche "
                            "Supervisor-Rolle 'manager'. Bitte das Add-on aktualisieren "
                            "oder neu bauen und danach neu starten."
                        )
                        log.warning("Supervisor %s %s wegen fehlender Berechtigung abgelehnt.",
                                    method, path)
                        raise SupervisorPermissionDenied(message)
                    message = str(body.get("message") or f"HTTP {response.status}")
                    # Bewusst nur die Meldung, niemals der gesendete Rumpf.
                    log.warning("Supervisor %s %s abgelehnt: %s", method, path, message)
                    raise SupervisorRejected(message)
                return body.get("data") or {}
        except aiohttp.ClientError as exc:
            log.error("Supervisor %s %s nicht erreichbar: %s", method, path, exc)
            raise SupervisorUnavailable("Der Supervisor ist nicht erreichbar.") from exc

    @staticmethod
    async def _read_body(response: aiohttp.ClientResponse) -> Dict[str, Any]:
        try:
            body = await response.json(content_type=None)
        except Exception:
            return {}
        return body if isinstance(body, dict) else {}
