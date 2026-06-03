"""
Skytech HEMS – main entry point.
Runs an async control loop (EMS cycle) and serves the monitoring web UI.
"""

import asyncio
import datetime
import json
import logging
import os
from pathlib import Path

from aiohttp import web

from ha_client import HAClient
from ems import EMSController, StateProxy

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    path = Path("/data/options.json")
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as exc:
            log.warning("Could not read /data/options.json: %s", exc)
    return {"interval_s": 30, "log_level": "info"}


# ---------------------------------------------------------------------------
# Steuerung-Tab: Kontroll-Schema aus Device-Konfiguration erzeugen
# ---------------------------------------------------------------------------

_GLOBAL_CTRL_ITEMS = [
    {"entity": "input_boolean.ems_pv_regelung_aktiv",        "label": "EMS aktiv"},
    {"entity": "input_select.ems_regelmodus",                "label": "Regelmodus"},
    {"entity": "input_number.ems_globaler_puffer_w",         "label": "Globaler Puffer"},
    {"entity": "input_number.ems_einschaltreserve_global_w", "label": "Einschaltreserve global"},
]


def _ctrl_items_controllable(p: str, output_unit: str = 'watt') -> list:
    suf = 'a' if output_unit == 'ampere' else 'w'
    items = [
        {"entity": f"input_boolean.ems_{p}_freigabe",                        "label": "Freigabe"},
        {"entity": f"input_select.ems_{p}_modus",                            "label": "Modus"},
        {"entity": f"input_number.ems_{p}_prioritat",                        "label": "Priorität"},
        {"entity": f"input_number.ems_{p}_geschutzte_mindestleistung_{suf}", "label": "Geschützte Mindestleistung"},
        {"entity": f"input_number.ems_{p}_min_technisch_{suf}",              "label": "Min. Leistung technisch"},
        {"entity": f"input_number.ems_{p}_max_technisch_{suf}",              "label": "Max. Leistung"},
        {"entity": f"input_number.ems_{p}_reserve_w",                        "label": "Reserve"},
        {"entity": f"input_number.ems_{p}_hoch_regelzeit_s",                 "label": "Hoch-Regelzeit"},
        {"entity": f"input_number.ems_{p}_runter_regelzeit_s",               "label": "Runter-Regelzeit"},
        {"entity": f"input_number.ems_{p}_max_anderung_pro_schritt_{suf}",   "label": "Max. Änderung/Schritt"},
        {"entity": f"input_number.ems_{p}_min_anderung_pro_schritt_{suf}",   "label": "Deadband"},
    ]
    if output_unit == 'ampere':
        items.append({"entity": f"input_number.ems_{p}_min_umschaltzeit_s",  "label": "Phasenwechsel-Mindestzeit"})
    return items


def _ctrl_items_binary(p: str) -> list:
    return [
        {"entity": f"input_boolean.ems_{p}_freigabe",             "label": "Freigabe"},
        {"entity": f"input_select.ems_{p}_modus",                 "label": "Modus"},
        {"entity": f"input_number.ems_{p}_prioritat",             "label": "Priorität"},
        {"entity": f"input_number.ems_{p}_leistung_w",            "label": "Leistung"},
        {"entity": f"input_number.ems_{p}_einschaltreserve_w",    "label": "Einschaltreserve"},
        {"entity": f"input_number.ems_{p}_mindestlaufzeit_s",     "label": "Mindestlaufzeit"},
        {"entity": f"input_number.ems_{p}_mindestauszeit_s",      "label": "Mindestauszeit"},
        {"entity": f"input_number.ems_{p}_abschaltverzogerung_s", "label": "Abschaltverzögerung"},
    ]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class HEMSApp:
    def __init__(self):
        cfg = _load_config()
        self.interval_s: int = int(cfg.get("interval_s", 30))
        self.post_cycle_script: str = (cfg.get("post_cycle_script") or "").strip()

        log_level = cfg.get("log_level", "info").upper()
        logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

        self._device_configs: list = cfg.get("devices", [])
        self.ha  = HAClient()
        self.ems = EMSController(self._device_configs)

        # Shared state – written by scheduler, read by web handler
        self._last_status: dict = {}
        self._last_cycle_at: str = ""
        self._last_error: str = ""
        self._cycle_count: int = 0

    # ------------------------------------------------------------------
    # Control cycle
    # ------------------------------------------------------------------

    async def _run_cycle(self) -> None:
        try:
            states = await self.ha.fetch_all_states()
            st     = StateProxy(states)
            result = self.ems.run_cycle(st)
            await self.ha.execute_write_ops(result["write_ops"])
            if self.post_cycle_script:
                try:
                    await self.ha.call_service("script", "turn_on",
                                               {"entity_id": self.post_cycle_script})
                except Exception as exc:
                    log.warning("Post-cycle script '%s' failed: %s", self.post_cycle_script, exc)
            self._last_status   = result["status"]
            self._last_error    = ""
            self._cycle_count  += 1
            self._last_cycle_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log.debug("Cycle %d completed.", self._cycle_count)
        except Exception as exc:
            self._last_error = str(exc)
            log.error("EMS cycle error: %s", exc, exc_info=True)

    async def _scheduler(self) -> None:
        log.info("EMS scheduler started (interval=%ds).", self.interval_s)
        while True:
            await self._run_cycle()
            await asyncio.sleep(self.interval_s)

    # ------------------------------------------------------------------
    # Web handlers
    # ------------------------------------------------------------------

    async def _handle_index(self, request: web.Request) -> web.Response:
        tmpl = Path(__file__).parent / "templates" / "index.html"
        return web.FileResponse(tmpl)

    async def _handle_status(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status":        self._last_status,
            "last_cycle_at": self._last_cycle_at,
            "cycle_count":   self._cycle_count,
            "error":         self._last_error,
            "interval_s":    self.interval_s,
        })

    async def _handle_device_controls_schema(self, request: web.Request) -> web.Response:
        """Return the Steuerung-Tab control schema derived from configured devices."""
        schema = [{"label": "Global", "items": _GLOBAL_CTRL_ITEMS}]
        for cfg in self._device_configs:
            name   = (cfg.get("name")          or "").strip()
            cls    = (cfg.get("class")         or "").strip()
            prefix = (cfg.get("entity_prefix") or "").strip() or name
            label  = (cfg.get("label")         or "").strip() or name.replace("_", " ").title()
            if cls == "controllable":
                output_unit = (cfg.get("output_unit") or "watt").strip()
                schema.append({"label": label, "items": _ctrl_items_controllable(prefix, output_unit)})
            elif cls == "binary":
                schema.append({"label": label, "items": _ctrl_items_binary(prefix)})
        return web.json_response(schema)

    async def _handle_controls(self, request: web.Request) -> web.Response:
        """Return fresh states for all EMS input_* helper entities."""
        try:
            states = await self.ha.fetch_all_states()
            ems = {
                eid: data for eid, data in states.items()
                if eid.startswith((
                    "input_boolean.ems_",
                    "input_select.ems_",
                    "input_number.ems_",
                ))
            }
            return web.json_response(ems)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def _handle_set(self, request: web.Request) -> web.Response:
        """Write a value to an HA input entity."""
        try:
            body       = await request.json()
            entity_id: str = body["entity_id"]
            value      = body["value"]
            domain     = entity_id.split(".")[0]

            if domain == "input_boolean":
                svc = "turn_on" if value in (True, "on", "true", 1, "1") else "turn_off"
                await self.ha.call_service("input_boolean", svc, {"entity_id": entity_id})
            elif domain == "input_number":
                await self.ha.call_service("input_number", "set_value",
                                           {"entity_id": entity_id, "value": float(value)})
            elif domain == "input_select":
                await self.ha.call_service("input_select", "select_option",
                                           {"entity_id": entity_id, "option": str(value)})
            else:
                return web.json_response({"error": f"Unsupported domain: {domain}"}, status=400)

            return web.json_response({"ok": True})
        except Exception as exc:
            log.error("Set entity failed: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self) -> None:
        app = web.Application()
        app.router.add_get("/",              self._handle_index)
        app.router.add_get("/index.html",    self._handle_index)
        app.router.add_get("/api/status",                  self._handle_status)
        app.router.add_get("/api/controls",               self._handle_controls)
        app.router.add_get("/api/device_controls_schema", self._handle_device_controls_schema)
        app.router.add_post("/api/set",                   self._handle_set)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8099)
        await site.start()
        log.info("Web UI available on port 8099.")

        await self._scheduler()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(HEMSApp().run())
