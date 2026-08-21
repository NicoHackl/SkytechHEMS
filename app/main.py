"""
Skytech HEMS – Haupteinstiegspunkt.
Führt einen asynchronen Regel-Loop (EMS-Zyklus) aus und stellt die Monitoring-Web-UI bereit.
"""

import asyncio
import datetime
import json
import logging
import os
import signal
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

from aiohttp import web

from config_service import ConfigProblem, ConfigService
from configuration import GLOBAL_DEFAULTS, parse_modes, validate_options
from ha_client import HAClient
from ems import EMSController, StateProxy
from supervisor_client import SupervisorClient

# Alle für Menschen lesbaren Zeitangaben laufen über diese Zone und dieses
# Format – Datum TT.MM.JJJJ, Uhrzeit Berliner Zeit ohne Offset oder Kürzel.
BERLIN = ZoneInfo("Europe/Berlin")
DISPLAY_TIME_FORMAT = "%d.%m.%Y %H:%M:%S"

# Gebaute Oberfläche. Die Quellen liegen in web/ und werden mit `npm run build`
# hierher geschrieben; das Ergebnis ist eingecheckt (D-035).
_STATIC_DIR = Path(__file__).parent / "static"

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
# Konfiguration
# ---------------------------------------------------------------------------

# Vom Supervisor erzeugte Laufzeitkonfiguration. Sie wird nur GELESEN – geschrieben
# werden Add-on-Optionen ausschließlich über die Supervisor-API. Der Pfad ist für
# die lokale Entwicklung außerhalb des Containers überschreibbar.
OPTIONS_PATH = Path(os.environ.get("HEMS_OPTIONS_PATH", "/data/options.json"))


def _load_raw_options() -> dict:
    """Liest die rohen Add-on-Optionen. Fehlt die Datei, gilt die leere Konfiguration."""
    if OPTIONS_PATH.exists():
        try:
            with open(OPTIONS_PATH) as f:
                return json.load(f)
        except Exception as exc:
            log.warning("Add-on-Optionen konnten nicht gelesen werden: %s", exc)
    return {}


# ---------------------------------------------------------------------------
# Steuerung-Tab: Kontroll-Schema aus Geräte-Konfiguration erzeugen
# ---------------------------------------------------------------------------

def _control_item(
    entity: str,
    label: str,
    key: str,
    role: str,
    *,
    unit: str = "",
    planning_relevant: bool = True,
) -> dict:
    """Beschreibt einen HEMS-Helfer stabil und ohne Suffix-Raten für API-Konsumenten."""
    domain = entity.split(".", 1)[0]
    kind = {
        "input_boolean": "bool",
        "input_number": "number",
        "input_select": "select",
    }.get(domain, "auto")
    item = {
        "entity": entity,
        "label": label,
        "key": key,
        "kind": kind,
        "role": role,
        "planning_relevant": planning_relevant,
    }
    if unit:
        item["unit"] = unit
    return item


_GLOBAL_CTRL_ITEMS = [
    _control_item(
        "input_boolean.ems_pv_regelung_aktiv", "EMS aktiv", "pv_regelung_aktiv", "user_control"
    ),
    _control_item(
        "input_select.ems_regelmodus", "Regelmodus", "regelmodus", "user_control"
    ),
    _control_item(
        "input_number.ems_globaler_puffer_w", "Globaler Puffer", "globaler_puffer_w",
        "user_preference", unit="W",
    ),
    _control_item(
        "input_number.ems_einschaltreserve_global_w", "Einschaltreserve global",
        "einschaltreserve_global_w", "user_preference", unit="W",
    ),
    _control_item(
        "input_number.ems_ac_speicher_entlade_abschlag_w", "Entlade-Abschlag Speicher",
        "ac_speicher_entlade_abschlag_w", "control_tuning", unit="W",
    ),
    _control_item(
        "input_boolean.ems_pyems_debug_output", "Debug-Ausgabe", "debug_output",
        "diagnostic_control", planning_relevant=False,
    ),
]


def _ctrl_items_controllable(p: str, output_unit: str = 'watt') -> list:
    suf = 'a' if output_unit == 'ampere' else 'w'
    unit = 'A' if output_unit == 'ampere' else 'W'
    items = [
        _control_item(f"input_boolean.ems_{p}_freigabe", "Freigabe", "freigabe", "user_control"),
        _control_item(
            f"input_boolean.ems_{p}_technische_freigabe", "Technische Freigabe",
            "technische_freigabe", "technical_gate",
        ),
        _control_item(f"input_select.ems_{p}_modus", "Modus", "modus", "user_control"),
        _control_item(
            f"input_number.ems_{p}_prioritat", "Priorität", "prioritat", "user_preference"
        ),
        _control_item(
            f"input_number.ems_{p}_geschutzte_mindestleistung_{suf}",
            "Geschützte Mindestleistung", "geschutzte_mindestleistung", "user_preference",
            unit=unit,
        ),
        _control_item(
            f"input_number.ems_{p}_min_technisch_{suf}", "Min. Leistung technisch",
            "min_technisch", "technical_constraint", unit=unit,
        ),
        _control_item(
            f"input_number.ems_{p}_max_technisch_{suf}", "Max. Leistung",
            "max_technisch", "technical_constraint", unit=unit,
        ),
        _control_item(
            f"input_number.ems_{p}_reserve_w", "Reserve", "reserve_w", "user_preference",
            unit="W",
        ),
        _control_item(
            f"input_number.ems_{p}_hoch_regelzeit_s", "Hoch-Regelzeit", "hoch_regelzeit_s",
            "control_tuning", unit="s", planning_relevant=False,
        ),
        _control_item(
            f"input_number.ems_{p}_runter_regelzeit_s", "Runter-Regelzeit",
            "runter_regelzeit_s", "control_tuning", unit="s", planning_relevant=False,
        ),
        _control_item(
            f"input_number.ems_{p}_max_anderung_pro_schritt_{suf}", "Max. Änderung/Schritt",
            "max_anderung_pro_schritt", "control_tuning", unit=unit,
            planning_relevant=False,
        ),
        _control_item(
            f"input_number.ems_{p}_min_anderung_pro_schritt_{suf}", "Totband (Deadband)",
            "min_anderung_pro_schritt", "control_tuning", unit=unit,
            planning_relevant=False,
        ),
    ]
    if output_unit == 'ampere':
        items.append(_control_item(
            f"input_number.ems_{p}_min_umschaltzeit_s", "Phasenwechsel-Mindestzeit",
            "min_umschaltzeit_s", "control_tuning", unit="s", planning_relevant=False,
        ))
    return items


def _ctrl_items_binary(p: str) -> list:
    return [
        _control_item(f"input_boolean.ems_{p}_freigabe", "Freigabe", "freigabe", "user_control"),
        _control_item(
            f"input_boolean.ems_{p}_technische_freigabe", "Technische Freigabe",
            "technische_freigabe", "technical_gate",
        ),
        _control_item(f"input_select.ems_{p}_modus", "Modus", "modus", "user_control"),
        _control_item(
            f"input_number.ems_{p}_prioritat", "Priorität", "prioritat", "user_preference"
        ),
        _control_item(
            f"input_number.ems_{p}_leistung_w", "Leistung", "leistung_w",
            "technical_constraint", unit="W",
        ),
        _control_item(
            f"input_number.ems_{p}_einschaltreserve_w", "Einschaltreserve",
            "einschaltreserve_w", "user_preference", unit="W",
        ),
        _control_item(
            f"input_number.ems_{p}_mindestlaufzeit_s", "Mindestlaufzeit",
            "mindestlaufzeit_s", "timing_guard", unit="s",
        ),
        _control_item(
            f"input_number.ems_{p}_mindestauszeit_s", "Mindestauszeit",
            "mindestauszeit_s", "timing_guard", unit="s",
        ),
        _control_item(
            f"input_number.ems_{p}_abschaltverzogerung_s", "Abschaltverzögerung",
            "abschaltverzogerung_s", "timing_guard", unit="s",
        ),
    ]


def _ctrl_items_battery(p: str) -> list:
    """Helfer eines AC-Speichers. Reihenfolge: Freigaben, Prioritäten,
    Leistungsgrenzen, SoC, Regelverhalten – so wird die Karte lesbar.

    Nicht mehr enthalten: max_lade-/max_entladeleistung_w (ersetzt durch die
    beiden available_*-Sensoren), soc_reserve_prozent und soc_taper_band_prozent
    (Funktion entfällt), soc_max_hysterese_prozent und min_umschaltzeit_s
    (jetzt statische Add-on-Felder) sowie entlade_sofort_schwelle_w."""
    return [
        _control_item(f"input_boolean.ems_{p}_freigabe", "Freigabe", "freigabe", "user_control"),
        _control_item(
            f"input_boolean.ems_{p}_technische_freigabe", "Technische Freigabe",
            "technische_freigabe", "technical_gate",
        ),
        _control_item(f"input_select.ems_{p}_modus", "Modus", "modus", "user_control"),
        _control_item(
            f"input_select.ems_{p}_betriebsart", "Betriebsart", "betriebsart", "user_control"
        ),
        _control_item(
            f"input_boolean.ems_{p}_laden_erlaubt", "Laden erlaubt", "laden_erlaubt",
            "user_control",
        ),
        _control_item(
            f"input_boolean.ems_{p}_entladen_erlaubt", "Entladen erlaubt", "entladen_erlaubt",
            "user_control",
        ),
        _control_item(
            f"input_number.ems_{p}_prioritat", "Priorität Laden", "prioritat", "user_preference"
        ),
        _control_item(
            f"input_number.ems_{p}_entlade_prioritat", "Priorität Entladen",
            "entlade_prioritat", "user_preference",
        ),
        _control_item(
            f"input_number.ems_{p}_min_ladeleistung_w", "Min. Ladeleistung",
            "min_ladeleistung_w", "technical_constraint", unit="W",
        ),
        _control_item(
            f"input_number.ems_{p}_min_entladeleistung_w", "Min. Entladeleistung",
            "min_entladeleistung_w", "technical_constraint", unit="W",
        ),
        _control_item(
            f"input_number.ems_{p}_soc_min_prozent", "SoC Minimum", "soc_min_prozent",
            "user_preference", unit="%",
        ),
        _control_item(
            f"input_number.ems_{p}_soc_max_prozent", "SoC Maximum", "soc_max_prozent",
            "user_preference", unit="%",
        ),
        _control_item(
            f"input_number.ems_{p}_geschutzte_mindestleistung_w",
            "Geschützte Mindestleistung", "geschutzte_mindestleistung", "user_preference",
            unit="W",
        ),
        _control_item(
            f"input_number.ems_{p}_reserve_w", "Reserve", "reserve_w", "user_preference",
            unit="W",
        ),
        _control_item(
            f"input_number.ems_{p}_umschalt_totzone_w", "Totzone um Null",
            "umschalt_totzone_w", "control_tuning", unit="W", planning_relevant=False,
        ),
        _control_item(
            f"input_number.ems_{p}_hoch_regelzeit_s", "Hoch-Regelzeit", "hoch_regelzeit_s",
            "control_tuning", unit="s", planning_relevant=False,
        ),
        _control_item(
            f"input_number.ems_{p}_runter_regelzeit_s", "Runter-Regelzeit",
            "runter_regelzeit_s", "control_tuning", unit="s", planning_relevant=False,
        ),
        _control_item(
            f"input_number.ems_{p}_max_anderung_pro_schritt_w", "Max. Änderung/Schritt",
            "max_anderung_pro_schritt", "control_tuning", unit="W", planning_relevant=False,
        ),
        _control_item(
            f"input_number.ems_{p}_min_anderung_pro_schritt_w", "Totband (Deadband)",
            "min_anderung_pro_schritt", "control_tuning", unit="W", planning_relevant=False,
        ),
    ]


def _build_device_controls_schema(
    device_configs: list,
    *,
    residual_power_entity: str,
    interval_s: int,
) -> list[dict]:
    """Baut den abwärtskompatiblen HEMS-Vertrag für UI und Energy Pilot."""
    schema: list[dict] = [{
        "name": "global",
        "label": "Global",
        "schema_version": 2,
        "control_policy": "pv_surplus_only",
        "residual_power_entity": residual_power_entity,
        "interval_s": interval_s,
        "items": _GLOBAL_CTRL_ITEMS,
    }]
    for cfg in device_configs:
        name = cfg["name"]
        cls = cfg["class"]
        prefix = cfg["entity_prefix"]
        label = cfg["label"] or name.replace("_", " ").title()
        base = {
            "name": name,
            "label": label,
            "class": cls,
            "entity_prefix": prefix,
            "allowed_modes": parse_modes(cfg.get("allowed_modes")),
            "control_policy": "pv_surplus_only",
        }
        if cls == "controllable":
            output_unit = cfg["output_unit"]
            suffix = "a" if output_unit == "ampere" else "w"
            base.update({
                "output_unit": output_unit,
                "actual_power_entity": cfg["actual_power_entity"],
                "request_entity": f"input_number.ems_{prefix}_anforderung_leistung_{suffix}",
                "allowed_phases": [int(value) for value in cfg["phases"].split(",")],
                "voltage_entities": [
                    value for key in ("voltage_l1_entity", "voltage_l2_entity", "voltage_l3_entity")
                    if (value := cfg[key])
                ],
                "items": _ctrl_items_controllable(prefix, output_unit),
            })
            schema.append(base)
        elif cls == "binary":
            base.update({
                "output_unit": "watt",
                "switch_entity": cfg["switch_entity"],
                "request_entity": f"input_boolean.ems_{prefix}_anforderung_an",
                "items": _ctrl_items_binary(prefix),
            })
            schema.append(base)
        elif cls == "battery":
            # request_entity trägt EINEN signierten Wert: + laden, - entladen.
            # Der HA-Helfer braucht deshalb ein negatives Minimum, sonst kommt
            # nie eine Entladeanforderung an.
            base.update({
                "output_unit": "watt",
                "soc_entity": cfg["soc_entity"],
                "charge_power_entity": cfg["charge_power_entity"],
                "discharge_power_entity": cfg["discharge_power_entity"],
                "power_entity": cfg["power_entity"],
                "power_sign": cfg["power_sign"],
                "available_charge_power_entity": cfg["available_charge_power_entity"],
                "available_discharge_power_entity": cfg["available_discharge_power_entity"],
                "capacity_kwh": cfg["capacity_kwh"],
                "request_entity": f"input_number.ems_{prefix}_anforderung_leistung_w",
                "request_sign": "positiv_laden",
                "mode_entity": f"input_select.ems_{prefix}_anforderung_betriebsart",
                "items": _ctrl_items_battery(prefix),
            })
            schema.append(base)
    return schema


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class HEMSApp:
    def __init__(self):
        # Eine je Prozessstart neue Kennung. Die Oberfläche erkennt daran, dass
        # nach einem Neustart wirklich eine NEUE Instanz antwortet – eine sehr
        # kurze Unterbrechung sähe sonst wie ein abgeschlossener Neustart aus.
        self.instance_id: str = uuid.uuid4().hex
        self._raw_options = _load_raw_options()
        validated = validate_options(self._raw_options)
        options = validated.options

        # Ein ungültiger globaler Wert darf den Start nicht verhindern: er fällt
        # auf den dokumentierten Default zurück und bleibt als Feldfehler sichtbar.
        def option(key: str):
            return (GLOBAL_DEFAULTS[key] if key in validated.field_errors
                    else options[key])

        self.interval_s: int = int(option("interval_s"))
        self.post_cycle_script: str = str(option("post_cycle_script"))

        logging.getLogger().setLevel(
            getattr(logging, str(option("log_level")).upper(), logging.INFO))

        # Nur die gültigen Einträge bekommen Helfer-Karten im Steuerung-Tab –
        # dieselbe Menge, die der Controller auch wirklich registriert.
        self._device_configs: list = validated.devices
        self.ha  = HAClient()
        self.supervisor = SupervisorClient()
        self.ems = EMSController(
            validated.devices,
            residual_power_entity=str(option("residual_power_entity")),
            speicher_in_residual_enthalten=bool(options["speicher_in_residual_enthalten"]),
            available_modes=options["available_modes"],
        )

        self.config = ConfigService(
            supervisor=self.supervisor,
            write_ops=self.ha.execute_write_ops,
            local_options=self._raw_options,
            loaded_options=self._raw_options,
            instance_id=self.instance_id,
            entity_snapshot=lambda: self._last_states,
        )

        # Gemeinsamer Zustand – vom Scheduler geschrieben, vom Web-Handler gelesen
        self._last_states: dict = {}
        self._last_status: dict = {}
        self._last_cycle_at: str = ""      # Anzeigeformat: TT.MM.JJJJ hh:mm:ss (Berliner Zeit)
        self._last_cycle_at_iso: str = ""  # Maschinenformat, unverändert für Bestandskonsumenten
        self._last_error: str = ""
        self._cycle_count: int = 0

    # ------------------------------------------------------------------
    # Regelzyklus
    # ------------------------------------------------------------------

    async def _run_cycle(self) -> None:
        try:
            states = await self.ha.fetch_all_states()
            # Für die Entitätsauswahl der Konfigurationsseite vorhalten: sie
            # braucht denselben Schnappschuss, nicht einen eigenen HA-Abruf.
            self._last_states = states
            st     = StateProxy(states)
            result = self.ems.run_cycle(st)
            write_results = await self.ha.execute_write_ops(result["write_ops"])
            # Ergebnis zurückmelden: der Controller ordnet einen Fehlschlag dem
            # verursachenden Gerät zu und macht ihn im Status sichtbar (B-2).
            self.ems.report_write_results(write_results)
            if self.post_cycle_script:
                try:
                    await self.ha.call_service("script", "turn_on",
                                               {"entity_id": self.post_cycle_script})
                except Exception as exc:
                    log.warning("Post-cycle script '%s' failed: %s", self.post_cycle_script, exc)
            now = datetime.datetime.now(BERLIN)
            self._last_status       = result["status"]
            self._last_error        = ""
            self._cycle_count      += 1
            self._last_cycle_at     = now.strftime(DISPLAY_TIME_FORMAT)
            self._last_cycle_at_iso = now.replace(microsecond=0).isoformat()
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
    # Web-Handler
    # ------------------------------------------------------------------

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Liefert die gebaute Oberfläche aus app/static (Quellen: web/, siehe D-035)."""
        return web.FileResponse(_STATIC_DIR / "index.html")

    async def _handle_status(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status":            self._last_status,
            # Anzeigeformat nach eiserner Regel 9; das Maschinenformat bleibt
            # zusätzlich erhalten, damit Bestandskonsumenten weiterlesen können (D-037).
            "last_cycle_at":     self._last_cycle_at,
            "last_cycle_at_iso": self._last_cycle_at_iso,
            "cycle_count":       self._cycle_count,
            "error":             self._last_error,
            "interval_s":        self.interval_s,
            # Wechselt bei jedem Prozessstart – so erkennt die Oberfläche einen
            # abgeschlossenen Neustart zuverlässig.
            "instance_id":       self.instance_id,
        })

    async def _handle_device_controls_schema(self, request: web.Request) -> web.Response:
        """Liefert das Steuerung-Tab-Kontrollschema, abgeleitet aus den konfigurierten Geräten."""
        schema = _build_device_controls_schema(
            self._device_configs,
            residual_power_entity=self.ems.residual_power_entity,
            interval_s=self.interval_s,
        )
        return web.json_response(schema)

    async def _handle_controls(self, request: web.Request) -> web.Response:
        """Liefert frische Zustände aller EMS-input_*-Helfer-Entitäten."""
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

    async def _handle_ep(self, request: web.Request) -> web.Response:
        """Liefert die vom Energy Pilot veröffentlichten `sensor.ep_*`-Entitäten.

        Reine Anzeige: EP schreibt seine KI-Vorschläge (`sensor.ep_<gerät>_*_vorschlag`)
        und Status-Sensoren (`sensor.ep_plan_status`, `sensor.ep_hems_verbindung`) als
        HA-Entitäten; HEMS liest sie – wie den Rest – über die HA-REST-API und spiegelt
        sie in der Weboberfläche. Kein direkter Add-on-zu-Add-on-Aufruf nötig.
        """
        try:
            states = await self.ha.fetch_all_states()
            ep = {
                eid: data for eid, data in states.items()
                if eid.startswith("sensor.ep_")
            }
            return web.json_response(ep)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def _handle_set(self, request: web.Request) -> web.Response:
        """Schreibt einen Wert in eine HA-input-Entität."""
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
    # Konfigurations-Handler – dünn: die Fachlogik liegt in ConfigService
    # ------------------------------------------------------------------

    @staticmethod
    def _problem(exc: ConfigProblem) -> web.Response:
        return web.json_response({"error": exc.message, **exc.payload}, status=exc.status)

    @staticmethod
    async def _draft(request: web.Request) -> tuple:
        """Liest Entwurf und Revision aus dem Rumpf. Wirft bei Unlesbarem."""
        try:
            body = await request.json()
        except Exception as exc:
            raise ConfigProblem("Der Anfragerumpf ist kein gültiges JSON.") from exc
        if not isinstance(body, dict):
            raise ConfigProblem("Erwartet wird ein JSON-Objekt.")
        options = body.get("options")
        if not isinstance(options, dict):
            raise ConfigProblem("Feld 'options' fehlt oder ist kein Objekt.")
        return options, str(body.get("stored_revision") or "")

    async def _handle_config_get(self, request: web.Request) -> web.Response:
        try:
            return web.json_response(await self.config.read())
        except ConfigProblem as exc:
            return self._problem(exc)

    async def _handle_config_entities(self, request: web.Request) -> web.Response:
        raw = request.query.get("domains", "")
        domains = [d.strip() for d in raw.split(",") if d.strip()] or None
        return web.json_response({"entities": self.config.entities(domains)})

    async def _handle_config_validate(self, request: web.Request) -> web.Response:
        try:
            options, _ = await self._draft(request)
        except ConfigProblem as exc:
            return web.json_response({"error": exc.message}, status=400)
        return web.json_response(self.config.validate(options))

    async def _handle_config_put(self, request: web.Request) -> web.Response:
        try:
            options, stored_revision = await self._draft(request)
        except ConfigProblem as exc:
            return web.json_response({"error": exc.message}, status=400)
        try:
            return web.json_response(await self.config.save(options, stored_revision))
        except ConfigProblem as exc:
            return self._problem(exc)

    async def _handle_config_restart(self, request: web.Request) -> web.Response:
        try:
            # 202: angenommen, läuft. Der eigentliche Neustart folgt erst, wenn
            # diese Antwort den Browser erreicht hat.
            return web.json_response(await self.config.restart(), status=202)
        except ConfigProblem as exc:
            return self._problem(exc)

    async def _handle_config_save_and_restart(self, request: web.Request) -> web.Response:
        try:
            options, stored_revision = await self._draft(request)
        except ConfigProblem as exc:
            return web.json_response({"error": exc.message}, status=400)
        try:
            result = await self.config.save_and_restart(options, stored_revision)
        except ConfigProblem as exc:
            return self._problem(exc)
        # Gespeichert, aber ohne Neustart, ist kein Fehler – nur ein anderer
        # Zustand. Er bekommt deshalb 200 statt 202 und benennt sich selbst.
        return web.json_response(result, status=202 if result.get("restarting") else 200)

    # ------------------------------------------------------------------
    # Ausführung
    # ------------------------------------------------------------------

    async def run(self) -> None:
        app = web.Application()
        app.router.add_get("/",              self._handle_index)
        app.router.add_get("/index.html",    self._handle_index)
        app.router.add_get("/api/status",                  self._handle_status)
        app.router.add_get("/api/controls",               self._handle_controls)
        app.router.add_get("/api/ep",                      self._handle_ep)
        app.router.add_get("/api/device_controls_schema", self._handle_device_controls_schema)
        app.router.add_post("/api/set",                   self._handle_set)
        app.router.add_get("/api/config",                 self._handle_config_get)
        app.router.add_get("/api/config/entities",        self._handle_config_entities)
        app.router.add_post("/api/config/validate",       self._handle_config_validate)
        app.router.add_put("/api/config",                 self._handle_config_put)
        app.router.add_post("/api/config/restart",        self._handle_config_restart)
        app.router.add_post("/api/config/save-and-restart",
                            self._handle_config_save_and_restart)

        # Gebündelte Assets der Oberfläche. Vite legt sie unter assets/ ab; die
        # Pfade in index.html sind relativ, damit sie auch unter dem
        # Ingress-Präfix auflösen (D-036).
        app.router.add_static("/assets/", _STATIC_DIR / "assets", name="assets")

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8099)
        await site.start()
        log.info("Web UI available on port 8099.")

        # Scheduler als Task starten und auf ein Stopp-Signal warten
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                # Signal-Handler werden nicht auf allen Plattformen unterstützt
                pass

        scheduler_task = asyncio.create_task(self._scheduler())
        try:
            await stop_event.wait()
        finally:
            log.info("Herunterfahren – Scheduler stoppen und Ressourcen freigeben.")
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
            await self.ha.close()
            await self.supervisor.close()
            await runner.cleanup()


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(HEMSApp().run())
