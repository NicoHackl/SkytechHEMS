import logging
import os
from typing import Any, Dict, List, Tuple

import aiohttp

log = logging.getLogger(__name__)

# In add-on context SUPERVISOR_TOKEN is injected automatically.
# For local dev, override with HA_URL / HA_TOKEN env vars.
_HA_URL = os.environ.get("HA_URL", "http://supervisor/core")
_HA_TOKEN = os.environ.get("HA_TOKEN", os.environ.get("SUPERVISOR_TOKEN", ""))


class HAClient:
    def __init__(self):
        self._headers = {
            "Authorization": f"Bearer {_HA_TOKEN}",
            "Content-Type": "application/json",
        }

    async def fetch_all_states(self) -> Dict[str, Dict]:
        """Returns {entity_id: {state, attributes, last_changed}}."""
        url = f"{_HA_URL}/api/states"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
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

    async def call_service(self, domain: str, service: str, data: Dict[str, Any] = None) -> None:
        """Fire a single HA service call."""
        url = f"{_HA_URL}/api/services/{domain}/{service}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    headers=self._headers,
                    json=data or {},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status not in (200, 201):
                        log.warning("Service %s.%s → HTTP %s", domain, service, resp.status)
            except Exception as exc:
                log.error("Service call %s.%s failed: %s", domain, service, exc)

    async def execute_write_ops(self, write_ops: List[Tuple[str, str, Dict[str, Any]]]) -> None:
        """Execute (domain, service, service_data) tuples against the HA REST API."""
        if not write_ops:
            return
        async with aiohttp.ClientSession() as session:
            for domain, service, data in write_ops:
                url = f"{_HA_URL}/api/services/{domain}/{service}"
                try:
                    async with session.post(
                        url,
                        headers=self._headers,
                        json=data,
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status not in (200, 201):
                            log.warning("Service %s.%s → HTTP %s", domain, service, resp.status)
                except Exception as exc:
                    log.error("Service call %s.%s failed: %s", domain, service, exc)
