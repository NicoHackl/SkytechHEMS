"""Veroeffentlichung der Kartendaten fuer die Skytech Power Flow Card (D-046).

Das Add-on schreibt nach jedem Regelzyklus zwei Anzeige-Sensoren in die
HA-Zustandsmaschine:

* ``sensor.skytech_hems_flow_config`` — Layout, Anlagenwerte und Geraeteliste.
  Er traegt ausschliesslich **Verweise** auf HA-Entitaeten, keine Messwerte:
  die Karte loest sie selbst auf und aktualisiert damit im Takt von Home
  Assistant statt im 30-Sekunden-Takt des HEMS.
* ``sensor.skytech_hems_flow_status`` — die Kennzahlen des letzten Zyklus und
  je Geraet einen Rueckfallwert.

Beide Nutzlasten sind in ``vertrag_powerflow_card_hems/kontrakt.md`` Feld fuer
Feld festgeschrieben; der Vertrag ist autoritativ, diese Datei setzt ihn um.

Grenzen, die dieses Modul einhaelt:

* Es schaltet nichts. Die geschriebenen ``sensor.*``-Entitaeten sind reine
  Anzeigedaten und haben keinen Regelpfad — Invariante 4 bleibt fuer die
  Regelung unangetastet.
* Es wirft nie. Jeder Fehler wird protokolliert und verschluckt: der Aufruf
  liegt im ``try`` des Regelzyklus, und ein misslungener Anzeigeschrieb darf
  keinen Zyklus kosten.
* Es fragt Home Assistant nicht zusaetzlich ab. Gearbeitet wird auf dem
  Zustandsabbild, das der Zyklus ohnehin geholt hat.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

CONFIG_ENTITY_ID = "sensor.skytech_hems_flow_config"
STATUS_ENTITY_ID = "sensor.skytech_hems_flow_status"

SCHEMA_VERSION = 1

# Ingress-Pfad des Panels, aus dem Slug in config.yaml. Die Karte verlinkt
# darauf; sie setzt selbst keine Pfade zusammen.
PANEL_PATH = "/hassio/ingress/skytech_hems"

# Home Assistant zeichnet Attribute jenseits von 16 KiB nicht mehr auf. Bei
# rund zwanzig Geraeten liegt die Nutzlast bei etwa 8 KiB — ab 12 KiB wird
# gewarnt, solange noch Luft ist.
PAYLOAD_WARN_BYTES = 12 * 1024

# Steuer-Helfer je Geraet. Schluessel ist der Vertragsname, Wert der `key` aus
# dem Steuerschema. Die Anforderung steht dort nicht als Item, sondern als
# `request_entity` am Gruppen-Dict — deshalb fehlt sie hier.
CONTROL_KEYS: Tuple[Tuple[str, str], ...] = (
    ("freigabe", "freigabe"),
    ("technische_freigabe", "technische_freigabe"),
    ("modus", "modus"),
    ("prioritat", "prioritat"),
)

# Laufzeitgruende aus `Device.mark_inactive` in Klartext. Der Vertrag verlangt
# deutsche Texte; im Code sind es bewusst stabile Tokens.
INACTIVE_REASON_TEXTS: Dict[str, str] = {
    "schreibziel_fehlt": "Schreibziel fehlt",
    "schreibziel_nicht_verfuegbar": "Schreibziel nicht verfügbar",
    "schreibziel_ungueltig": "Schreibziel ungültig",
    "schreiben_fehlgeschlagen": "Schreiben fehlgeschlagen",
}


# ---------------------------------------------------------------------------
# Konfigurationsnutzlast
# ---------------------------------------------------------------------------

def build_config_payload(options: Dict[str, Any], controls_schema: List[Dict[str, Any]],
                         addon_version: str, erzeugt_am: str) -> Dict[str, Any]:
    """Layout, Anlagenwerte und Geraeteliste nach kontrakt.md, Abschnitt 3.

    `controls_schema` ist die Ausgabe von `_build_device_controls_schema` und
    damit die einzige Quelle der Helfer-Entity-IDs. Sie enthaelt nur gueltige
    Geraete — beim Start uebersprungene fallen dadurch von selbst heraus.
    """
    by_name = {device["name"]: device for device in options.get("devices") or []}

    devices: List[Dict[str, Any]] = []
    for group in controls_schema:
        if group.get("name") == "global":
            continue
        config = by_name.get(group["name"])
        if config is None or not config.get("flow_show", True):
            continue
        devices.append(_device_entry(group, config, len(devices) + 1))

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "addon_version": addon_version,
        "revision": "",
        "erzeugt_am": erzeugt_am,
        "anzeige": {
            "titel": options.get("flow_title", ""),
            "watt_schwelle": options.get("flow_watt_threshold", 1000),
            "animation": bool(options.get("flow_animation")),
            "haus_knoten_anzeigen": bool(options.get("flow_house_node")),
        },
        "standard": {
            "pv_power_entities": [row["entity"] for row
                                  in (options.get("flow_pv_power_entities") or [])
                                  if row.get("entity")],
            "pv_label": options.get("flow_pv_label", ""),
            "grid_power_entity": options.get("flow_grid_power_entity", ""),
            "grid_power_sign": options.get("flow_grid_power_sign", ""),
            "grid_import_entity": options.get("flow_grid_import_entity", ""),
            "grid_export_entity": options.get("flow_grid_export_entity", ""),
            "grid_label": options.get("flow_grid_label", ""),
            "house_power_entity": options.get("flow_house_power_entity", ""),
            "house_label": options.get("flow_house_label", ""),
            "batterie": _battery_entry(options),
        },
        "devices": devices,
        "hems": {
            "ems_enabled_entity": "input_boolean.ems_pv_regelung_aktiv",
            "regelmodus_entity": "input_select.ems_regelmodus",
            "panel_pfad": PANEL_PATH,
        },
    }
    payload["revision"] = revision(payload)
    return payload


def _battery_entry(options: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Der Hausspeicher der Anlage — nicht die vom HEMS geregelten AC-Speicher.

    Ohne Label und ohne SoC-Sensor gibt es keinen Batterieknoten; `None` ist
    laut Vertrag der ausdrueckliche Weg, ihn wegzulassen.
    """
    label = options.get("flow_battery_label", "")
    soc = options.get("flow_battery_soc_entity", "")
    if not label and not soc:
        return None
    return {
        "label": label,
        "soc_entity": soc,
        "capacity_kwh": options.get("flow_battery_capacity_kwh"),
        "power_entity": options.get("flow_battery_power_entity", ""),
        "power_sign": options.get("flow_battery_power_sign", ""),
        "charge_power_entity": options.get("flow_battery_charge_power_entity", ""),
        "discharge_power_entity": options.get("flow_battery_discharge_power_entity", ""),
    }


def power_kind(group: Dict[str, Any]) -> str:
    """Leistungsart eines Geraets, autoritativ aus Klasse und Ausgabeeinheit.

    Die Karte leitet sie ausdruecklich NICHT aus `class` ab: dieselbe Klasse
    kann verschiedene Varianten haben.
    """
    cls = group.get("class")
    if cls == "controllable":
        return "ampere" if group.get("output_unit") == "ampere" else "watt"
    if cls == "binary":
        return "binary_static"
    if cls == "battery":
        if group.get("charge_power_entity") and group.get("discharge_power_entity"):
            return "battery_split"
        return "battery_signed"
    return ""


def _device_entry(group: Dict[str, Any], config: Dict[str, Any],
                  position: int) -> Dict[str, Any]:
    """Ein Eintrag in `devices[]`. Jede Entity-ID steht ausgeschrieben."""
    items = {item.get("key"): item.get("entity", "") for item in group.get("items") or []}
    cls = group["class"]
    kind = power_kind(group)

    voltages = list(group.get("voltage_entities") or []) if cls == "controllable" else []
    voltages = (voltages + ["", "", ""])[:3]

    # phases ist "1", "3" oder "1,3" — der Rueckfallwert ist die groesste
    # zulaessige Phasenzahl, denn ohne Helfer regelt das Geraet dreiphasig.
    phases = [int(value) for value in (config.get("phases") or "3").split(",")]

    entry: Dict[str, Any] = {
        "id": group["name"],
        "label": group.get("label") or group["name"],
        "class": cls,
        "power_kind": kind,
        "icon": config.get("flow_icon", ""),
        "farbe": config.get("flow_color", ""),
        "reihenfolge": position,

        "power_entity": "",
        "power_sign": "",
        "switch_entity": "",
        "power_actual_entity": "",
        "static_power_w": None,
        "voltage_entities": voltages,
        "phases_entity": "",
        "phases_fallback": max(phases) if cls == "controllable" else 3,
        "charge_power_entity": "",
        "discharge_power_entity": "",
        "soc_entity": "",
        "capacity_kwh": None,

        "control": {
            "freigabe": items.get("freigabe", ""),
            "technische_freigabe": items.get("technische_freigabe", ""),
            "modus": items.get("modus", ""),
            "prioritat": items.get("prioritat", ""),
            "anforderung": group.get("request_entity", ""),
        },
    }

    if cls == "controllable":
        entry["power_entity"] = group.get("actual_power_entity", "")
        entry["phases_entity"] = group.get("phase_entity", "")
    elif cls == "binary":
        entry["switch_entity"] = group.get("switch_entity", "")
        entry["power_actual_entity"] = config.get("power_actual_entity", "")
        entry["static_power_w"] = config.get("power_w")
    elif cls == "battery":
        entry["soc_entity"] = group.get("soc_entity", "")
        entry["capacity_kwh"] = group.get("capacity_kwh")
        if kind == "battery_split":
            entry["charge_power_entity"] = group.get("charge_power_entity", "")
            entry["discharge_power_entity"] = group.get("discharge_power_entity", "")
        else:
            entry["power_entity"] = group.get("power_entity", "")
            entry["power_sign"] = group.get("power_sign", "")

    return entry


# ---------------------------------------------------------------------------
# Statusnutzlast
# ---------------------------------------------------------------------------

def build_status_payload(status: Dict[str, Any], cycle_count: int,
                         last_cycle_at: str) -> Dict[str, Any]:
    """Kennzahlen des letzten Zyklus und Rueckfallwerte je Geraet (Abschnitt 4)."""
    devices: Dict[str, Any] = {}
    for device in status.get("devices") or []:
        devices[device.get("id", "")] = {
            "leistung_w": _device_power(device),
            "runtime_active": bool(device.get("eligible")) and bool(device.get("runtime_active")),
            "inactive_reasons": _inactive_reasons(device),
        }

    pool = _as_float(status.get("pool_w"), 0.0)
    return {
        "schema_version": SCHEMA_VERSION,
        "last_cycle_at": last_cycle_at,
        "cycle_count": cycle_count,
        "ems_enabled": bool(status.get("ems_enabled")),
        "global_mode": str(status.get("global_mode") or ""),
        "hard_lockout": bool(status.get("hard_lockout")),
        "residual_w": _as_float(status.get("residual_w"), 0.0),
        "hems_last_w": _as_float(status.get("hems_last_w"), 0.0),
        "hausdefizit_w": _as_float(status.get("hausdefizit_w"), 0.0),
        "pool_w": pool,
        "devices": devices,
    }


def _device_power(device: Dict[str, Any]) -> Optional[float]:
    """Rueckfallleistung je Geraeteklasse.

    Bewusst NICHT der Primaerwert: die Karte liest zuerst den Direktsensor und
    greift nur hierauf zurueck, wenn der ausfaellt.
    """
    kind = device.get("type")
    if kind == "controllable":
        return _as_float(device.get("actual_w"), None)
    if kind == "binary":
        if device.get("power_actual_w") is not None:
            return _as_float(device.get("power_actual_w"), None)
        return _as_float(device.get("power_w"), None) if device.get("final_on") else 0.0
    if kind == "battery":
        return _as_float(device.get("netto_w"), None)
    return None


def _inactive_reasons(device: Dict[str, Any]) -> List[str]:
    """Warum ein Geraet gerade nicht mitregelt — in deutschem Klartext.

    Zwei verschiedene Ursachen laufen hier zusammen: `runtime_active` meldet
    ein kaputtes Schreibziel, `eligible` die Freigabeentscheidung des Zyklus.
    Der Vertrag kennt nur eine Liste, also werden beide uebersetzt.
    """
    reasons: List[str] = []
    if not device.get("runtime_active", True):
        for token in device.get("inactive_reasons") or []:
            reasons.append(INACTIVE_REASON_TEXTS.get(token, str(token)))
        return reasons

    if device.get("eligible"):
        blocked = device.get("blockiert_grund")
        if blocked:
            reasons.append(_BLOCK_TEXTS.get(blocked, str(blocked)))
        return reasons

    diagnostics = device.get("entity_diagnostics") or {}
    roles = {info.get("role"): str(info.get("state") or "")
             for info in diagnostics.values() if isinstance(info, dict)}
    if roles.get("technische_freigabe", "on") != "on":
        reasons.append("Technische Freigabe aus")
    if roles.get("freigabe", "on") != "on":
        reasons.append("Freigabe aus")
    if device.get("source") == "aus":
        reasons.append("Gerätemodus aus")
    if not reasons:
        reasons.append("Nicht freigegeben")
    return reasons


# Blockadegruende eines AC-Speichers, wie sie `BatteryDevice` setzt. Ein
# blockierter Speicher ist freigegeben, regelt aber gerade nicht mit.
_BLOCK_TEXTS: Dict[str, str] = {
    "umschaltsperre": "Richtungswechsel gesperrt",
    "totzone": "Innerhalb der Totzone",
}


# ---------------------------------------------------------------------------
# Revision
# ---------------------------------------------------------------------------

def revision(payload: Dict[str, Any]) -> str:
    """Kurzhash der Konfigurationsnutzlast, 12 Hex-Zeichen.

    Zeitstempel und die Revision selbst bleiben aussen vor — sonst aenderte
    sich der Hash in jedem Zyklus und die Entitaet wuerde staendig neu
    geschrieben.
    """
    relevant = {key: value for key, value in payload.items()
                if key not in ("erzeugt_am", "revision")}
    canonical = json.dumps(relevant, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------

class FlowPublisher:
    """Schreibt die beiden Anzeige-Sensoren, wenn die Veroeffentlichung an ist.

    Haelt genau zwei Dinge im Speicher: die zuletzt geschriebene Revision und
    den Zeitpunkt des letzten Schreibens. Keine Datei, keine Datenbank — das
    HEMS hat bewusst keine eigene Persistenz.
    """

    def __init__(self, ha_client) -> None:
        self._ha = ha_client
        self._last_revision: str = ""
        self._last_written_at: str = ""

    @property
    def last_revision(self) -> str:
        return self._last_revision

    @property
    def last_written_at(self) -> str:
        return self._last_written_at

    async def publish(self, *, options: Dict[str, Any], controls_schema: List[Dict[str, Any]],
                      status: Dict[str, Any], states: Dict[str, Any],
                      cycle_count: int, addon_version: str, now: str) -> None:
        """Ein Veroeffentlichungslauf. Wirft nie."""
        try:
            if not options.get("flow_publish"):
                return

            config_payload = build_config_payload(options, controls_schema, addon_version, now)
            status_payload = build_status_payload(status, cycle_count, now)

            # Per POST /api/states erzeugte Entitaeten ueberleben keinen
            # HA-Neustart. Fehlt die Konfiguration im Zustandsabbild, wird sie
            # neu geschrieben — das kostet nichts, der Abzug liegt ohnehin vor.
            missing = CONFIG_ENTITY_ID not in (states or {})
            if config_payload["revision"] != self._last_revision or missing:
                _warn_if_large(config_payload, CONFIG_ENTITY_ID)
                written = await self._ha.set_state(
                    CONFIG_ENTITY_ID, config_payload["revision"],
                    _config_attributes(config_payload))
                if written:
                    self._last_revision = config_payload["revision"]
                    self._last_written_at = now

            await self._ha.set_state(
                STATUS_ENTITY_ID, f"{round(status_payload['pool_w'])}",
                _status_attributes(status_payload))
        except Exception as exc:
            log.warning("Kartendaten konnten nicht veröffentlicht werden: %s", exc)


def _config_attributes(payload: Dict[str, Any]) -> Dict[str, Any]:
    attributes = dict(payload)
    attributes["friendly_name"] = "Skytech HEMS Flow-Konfiguration"
    attributes["icon"] = "mdi:transit-connection-variant"
    return attributes


def _status_attributes(payload: Dict[str, Any]) -> Dict[str, Any]:
    attributes = dict(payload)
    attributes["friendly_name"] = "Skytech HEMS Flow-Status"
    attributes["icon"] = "mdi:solar-power"
    attributes["unit_of_measurement"] = "W"
    attributes["device_class"] = "power"
    attributes["state_class"] = "measurement"
    return attributes


def payload_size(payload: Dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))


def _warn_if_large(payload: Dict[str, Any], entity_id: str) -> None:
    size = payload_size(payload)
    if size > PAYLOAD_WARN_BYTES:
        log.warning(
            "Kartendaten von %s sind %d Bytes gross - Home Assistant zeichnet "
            "Attribute ueber 16 KiB nicht mehr auf.", entity_id, size)


def _as_float(value: Any, default: Optional[float]) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Diagnose
# ---------------------------------------------------------------------------

def collect_references(config_payload: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Jeder Entity-Verweis der Konfigurationsnutzlast als (Pfad, Entity-ID).

    Grundlage der Vorschau im Panel: sie beantwortet die Frage, welcher Verweis
    gerade trägt und welcher nicht. Leere Felder tauchen nicht auf — sie sind
    ein gültiger Zustand, kein fehlender Wert.
    """
    references: List[Tuple[str, str]] = []
    standard = config_payload.get("standard") or {}

    for index, entity in enumerate(standard.get("pv_power_entities") or []):
        references.append((f"standard.pv_power_entities[{index}]", entity))

    for key in ("grid_power_entity", "grid_import_entity", "grid_export_entity",
                "house_power_entity"):
        if standard.get(key):
            references.append((f"standard.{key}", standard[key]))

    battery = standard.get("batterie")
    if isinstance(battery, dict):
        for key in ("soc_entity", "power_entity",
                    "charge_power_entity", "discharge_power_entity"):
            if battery.get(key):
                references.append((f"standard.batterie.{key}", battery[key]))

    for device in config_payload.get("devices") or []:
        device_id = device.get("id", "")
        for key in ("power_entity", "switch_entity", "power_actual_entity",
                    "phases_entity", "charge_power_entity", "discharge_power_entity",
                    "soc_entity"):
            if device.get(key):
                references.append((f"devices[{device_id}].{key}", device[key]))
        for index, entity in enumerate(device.get("voltage_entities") or []):
            if entity:
                references.append((f"devices[{device_id}].voltage_entities[{index}]", entity))

    return references


def resolve_references(config_payload: Dict[str, Any],
                       states: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Löst jeden Verweis gegen das Zustandsabbild des letzten Zyklus auf.

    Ausdrücklich ohne zusätzliche HA-Abfrage — dieselbe Regel wie bei
    `GET /api/config/entities`. Ein nicht wandelbarer Zustand bleibt `null`,
    niemals `0`.
    """
    resolved: List[Dict[str, Any]] = []
    for path, entity in collect_references(config_payload):
        entry = (states or {}).get(entity)
        state = None if entry is None else entry.get("state")
        value = _as_float(state, None)
        resolved.append({
            "pfad": path,
            "entity": entity,
            "state": "" if state is None else str(state),
            "value": value,
            "valid": value is not None,
        })
    return resolved


def payload_warnings(config_payload: Dict[str, Any]) -> List[str]:
    """Hinweise, die der Benutzer selbst abstellen kann."""
    warnings: List[str] = []
    size = payload_size(config_payload)
    if size > PAYLOAD_WARN_BYTES:
        warnings.append(
            "Die Kartendaten sind größer als 12 KiB – Home Assistant zeichnet "
            "Attribute über 16 KiB nicht mehr auf."
        )
    return warnings
