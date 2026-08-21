"""Add-on-Optionen: Normalisierung, Validierung, Revision und Diff.

Einziger Ort, an dem entschieden wird, ob eine gespeicherte Konfiguration gültig
ist. Der Controller instanziiert nur, was hier durchgekommen ist; die Oberfläche
zeigt genau dieselben Feldfehler an. Zwei Quellen für „welche Felder hat ein
Gerät" würden sonst auseinanderlaufen.

Das Supervisor-Schema kann das nicht übernehmen: eine gemischte Objektliste
kennt keine bedingten Pflichtfelder, und eine Pflichtmarkierung für ein
klassenspezifisches Feld machte alle anderen Klassen ungültig. Die Anwendung ist
deshalb die autoritative Validierung.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Feste Wertebereiche
# ---------------------------------------------------------------------------

# Normale Regelmodi, für die es Regellogik gibt. Frei erfundene Namen sind
# unzulässig – ohne Fachlogik wäre ein Modus nur ein Etikett.
NORMAL_MODES: Tuple[str, ...] = ("manuell", "nur_heizen", "nur_laden")
# Sondermodi von input_select.ems_regelmodus. Sie gehören weder in
# available_modes noch in allowed_modes und sind immer unterstützt.
SPECIAL_MODES: Tuple[str, ...] = ("auto", "aus")
# Alt-Wert aus Konfigurationen vor der Modus-Trennung.
LEGACY_MODE = "auto"

DEVICE_CLASSES: Tuple[str, ...] = ("controllable", "binary", "battery")
LOG_LEVELS: Tuple[str, ...] = ("debug", "info", "warning", "error")
OUTPUT_UNITS: Tuple[str, ...] = ("watt", "ampere")
PHASE_VALUES: Tuple[str, ...] = ("1", "3", "1,3")
POWER_SIGNS: Tuple[str, ...] = ("positiv_laden", "positiv_entladen")
# Optionen, die der Betriebsart-Helfer eines Speichers tragen muss.
BATTERY_MODE_OPTIONS: Tuple[str, ...] = ("laden", "entladen", "standby")

# Home Assistant slugifiziert Umlaute (ü→u, ö→o, ä→a, ß→ss), daher dieser ASCII-Name.
DEFAULT_RESIDUAL_ENTITY = "sensor.verfugbare_leistung_fur_uberschussverbraucher"

INTERVAL_MIN_S = 1
INTERVAL_MAX_S = 300

_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_ENTITY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")

# ---------------------------------------------------------------------------
# Formular-Startwerte der verpflichtenden Add-on-Fallbacks
# ---------------------------------------------------------------------------

# `technical_maximum: 0` ist absichtlich ungültig: ein neu angelegtes Gerät ist
# damit noch nicht speicherfähig, die reale Obergrenze muss eingetragen werden.
CONTROLLABLE_FALLBACK_DEFAULTS: Dict[str, float] = {
    "technical_minimum":   0.0,
    "technical_maximum":   0.0,
    "increase_delay_s":   60.0,
    "decrease_delay_s":   60.0,
    "maximum_step_change": 1000.0,
    "minimum_step_change": 0.0,
}

BINARY_FALLBACK_DEFAULTS: Dict[str, float] = {
    "power_w":       0.0,
    "on_reserve_w":  0.0,
    "min_runtime_s": 0.0,
    "min_offtime_s": 0.0,
    "off_delay_s":   0.0,
}

# Ersetzen die entfallenen HA-Helfer soc_max_hysterese_prozent und
# min_umschaltzeit_s des Speichers. Fehlen sie in einer Bestandskonfiguration,
# greift der Default – anders als bei den Feldern oben wird der Speicher davon
# nicht inaktiv.
BATTERY_STATIC_DEFAULTS: Dict[str, float] = {
    "soc_max_hysteresis_percent": 2.0,
    "direction_switch_delay_s":   5.0,
}

GLOBAL_DEFAULTS: Dict[str, Any] = {
    "interval_s": 30,
    "log_level": "info",
    "post_cycle_script": "",
    "residual_power_entity": DEFAULT_RESIDUAL_ENTITY,
    "speicher_in_residual_enthalten": True,
}

# Ändert sich einer dieser globalen Werte, werden vor einem Neustart vorsorglich
# ALLE alten Geräte sicher deaktiviert – ihre Zuteilung hing daran.
GLOBAL_KEYS_FORCING_SHUTDOWN: Tuple[str, ...] = (
    "residual_power_entity",
    "speicher_in_residual_enthalten",
    "available_modes",
)


# ---------------------------------------------------------------------------
# Ergebnistypen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DeviceIssue:
    """Ein Geräteeintrag, der nicht instanziiert werden konnte."""

    index: int
    name: str
    device_class: str
    label: str
    errors: Dict[str, str]


@dataclass
class ValidationResult:
    """Ergebnis einer vollständigen Prüfung der Add-on-Optionen.

    `devices` enthält nur die gültigen Einträge in unveränderter Reihenfolge –
    die Reihenfolge entscheidet bei gleicher Priorität. `inactive_devices`
    behält die ungültigen mit konkreten Feldfehlern, statt sie im Log
    verschwinden zu lassen.
    """

    options: Dict[str, Any]
    devices: List[Dict[str, Any]] = field(default_factory=list)
    inactive_devices: List[DeviceIssue] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    field_errors: Dict[str, str] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return not self.errors and not self.field_errors


# ---------------------------------------------------------------------------
# Modus-Listen
# ---------------------------------------------------------------------------

def parse_modes(raw: Any) -> List[str]:
    """Kommagetrennte Modusliste in eine stabile, doppelfreie Liste wandeln.

    Der Alt-Wert `auto` wird auf `manuell` abgebildet. Unbekannte Tokens bleiben
    erhalten, damit die Validierung sie benennen kann – stillschweigendes
    Wegwerfen versteckt einen Tippfehler.
    """
    tokens = [token.strip() for token in str(raw or "").split(",")]
    result: List[str] = []
    for token in tokens:
        if not token:
            continue
        mode = "manuell" if token == LEGACY_MODE else token
        if mode not in result:
            result.append(mode)
    return result


def serialize_modes(modes: List[str]) -> str:
    """Stabile Reihenfolge, keine Duplikate – damit der Revisions-Hash ruhig bleibt."""
    known = [mode for mode in NORMAL_MODES if mode in modes]
    unknown = [mode for mode in modes if mode not in NORMAL_MODES and mode not in known]
    return ",".join(known + unknown)


# ---------------------------------------------------------------------------
# Normalisierung
# ---------------------------------------------------------------------------

def normalize_options(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Abwärtskompatibles Lesen: Defaults setzen, Alt-Werte migrieren.

    Bewusst ohne Prüfung – Normalisieren und Validieren sind zwei Schritte.
    Bestandsoptionen ohne `available_modes` verhalten sich unverändert, weil
    sie auf alle drei normalen Modi abgebildet werden.
    """
    raw = raw or {}
    options: Dict[str, Any] = dict(GLOBAL_DEFAULTS)
    for key, default in GLOBAL_DEFAULTS.items():
        if key in raw:
            options[key] = raw[key]
        else:
            options[key] = default

    options["available_modes"] = serialize_modes(
        parse_modes(raw["available_modes"]) if "available_modes" in raw else list(NORMAL_MODES)
    )
    options["devices"] = [
        _normalize_device(entry) for entry in (raw.get("devices") or [])
        if isinstance(entry, dict)
    ]
    return options


def _normalize_device(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ein Geräteeintrag mit aufgelösten Defaults, ohne Prüfung."""
    name = _as_text(raw.get("name"))
    device: Dict[str, Any] = {
        "name": name,
        "class": _as_text(raw.get("class")),
        "label": _as_text(raw.get("label")) or name,
        "entity_prefix": _as_text(raw.get("entity_prefix")) or name,
    }

    # Fehlendes Feld heißt „Bestandskonfiguration" und wird auf `manuell`
    # migriert. Ein ausdrücklich gespeicherter leerer String bleibt leer: das
    # ist ein gültiges Nur-Energy-Pilot-Gerät und darf nicht überschrieben werden.
    if "allowed_modes" in raw:
        device["allowed_modes"] = serialize_modes(parse_modes(raw["allowed_modes"]))
    else:
        device["allowed_modes"] = "manuell"

    cls = device["class"]
    if cls == "controllable":
        device.update({
            "actual_power_entity": _as_text(raw.get("actual_power_entity")),
            "output_unit": _as_text(raw.get("output_unit")) or "watt",
            "phases": _as_text(raw.get("phases")) or "1",
            "phase_switch_delay_s": _as_float(raw.get("phase_switch_delay_s"), 300.0),
            "voltage_l1_entity": _as_text(raw.get("voltage_l1_entity")),
            "voltage_l2_entity": _as_text(raw.get("voltage_l2_entity")),
            "voltage_l3_entity": _as_text(raw.get("voltage_l3_entity")),
        })
        for key in CONTROLLABLE_FALLBACK_DEFAULTS:
            device[key] = _as_float(raw.get(key), None) if key in raw else None
    elif cls == "binary":
        device["switch_entity"] = _as_text(raw.get("switch_entity"))
        for key in BINARY_FALLBACK_DEFAULTS:
            device[key] = _as_float(raw.get(key), None) if key in raw else None
    elif cls == "battery":
        device.update({
            "soc_entity": _as_text(raw.get("soc_entity")),
            "charge_power_entity": _as_text(raw.get("charge_power_entity")),
            "discharge_power_entity": _as_text(raw.get("discharge_power_entity")),
            "power_entity": _as_text(raw.get("power_entity")),
            "power_sign": _as_text(raw.get("power_sign")) or "positiv_laden",
            "available_charge_power_entity": _as_text(raw.get("available_charge_power_entity")),
            "available_discharge_power_entity": _as_text(raw.get("available_discharge_power_entity")),
            "capacity_kwh": _as_float(raw.get("capacity_kwh"), 0.0),
        })
        for key, default in BATTERY_STATIC_DEFAULTS.items():
            value = _as_float(raw.get(key), None) if key in raw else None
            device[key] = default if value is None else value

    return device


# ---------------------------------------------------------------------------
# Validierung
# ---------------------------------------------------------------------------

def validate_options(raw: Optional[Dict[str, Any]]) -> ValidationResult:
    """Prüft globale Felder und jeden Geräteeintrag einzeln.

    Ein ungültiges Gerät macht die übrigen nicht ungültig: es landet in
    `inactive_devices` und wird beim Start nicht instanziiert.
    """
    options = normalize_options(raw)
    result = ValidationResult(options=options)

    _validate_global(options, result)

    available = parse_modes(options["available_modes"])
    seen_names: Dict[str, int] = {}
    seen_prefixes: Dict[str, int] = {}

    for index, device in enumerate(options["devices"]):
        errors = _validate_device(device, index, available, seen_names, seen_prefixes)
        if errors:
            result.field_errors.update(errors)
            result.inactive_devices.append(DeviceIssue(
                index=index,
                name=device["name"],
                device_class=device["class"],
                label=device["label"] or device["name"],
                errors={_short_path(path): text for path, text in errors.items()},
            ))
        else:
            result.devices.append(device)

    return result


def _validate_global(options: Dict[str, Any], result: ValidationResult) -> None:
    interval = _as_float(options.get("interval_s"), None)
    if interval is None or interval != int(interval):
        result.field_errors["interval_s"] = "Ganze Zahl von 1 bis 300 erwartet."
    elif not INTERVAL_MIN_S <= int(interval) <= INTERVAL_MAX_S:
        result.field_errors["interval_s"] = "Zulässig ist ein Wert von 1 bis 300 Sekunden."
    else:
        options["interval_s"] = int(interval)

    if options.get("log_level") not in LOG_LEVELS:
        result.field_errors["log_level"] = (
            "Zulässig sind debug, info, warning oder error."
        )

    script = _as_text(options.get("post_cycle_script"))
    if script and not (script.startswith("script.") and _ENTITY_RE.match(script)):
        result.field_errors["post_cycle_script"] = (
            "Leer lassen oder eine Entity-ID der Form script.<name> eintragen."
        )
    options["post_cycle_script"] = script

    residual = _as_text(options.get("residual_power_entity"))
    if not residual:
        result.field_errors["residual_power_entity"] = "Überschuss-Sensor ist ein Pflichtfeld."
    elif not _ENTITY_RE.match(residual):
        result.field_errors["residual_power_entity"] = "Vollständige Entity-ID erwartet, z. B. sensor.ueberschuss."
    options["residual_power_entity"] = residual

    options["speicher_in_residual_enthalten"] = bool(options.get("speicher_in_residual_enthalten"))

    unknown = [mode for mode in parse_modes(options["available_modes"])
               if mode not in NORMAL_MODES]
    if unknown:
        result.field_errors["available_modes"] = (
            f"Unbekannte Regelmodi: {', '.join(unknown)}. "
            f"Zulässig sind {', '.join(NORMAL_MODES)}."
        )


def _validate_device(device: Dict[str, Any], index: int, available: List[str],
                     seen_names: Dict[str, int],
                     seen_prefixes: Dict[str, int]) -> Dict[str, str]:
    """Feldfehler eines Geräts als {„devices[i].feld": deutsche Meldung}."""
    errors: Dict[str, str] = {}

    def fail(field_name: str, text: str) -> None:
        errors[f"devices[{index}].{field_name}"] = text

    name = device["name"]
    if not name:
        fail("name", "Name ist ein Pflichtfeld.")
    elif not _NAME_RE.match(name):
        fail("name", "Nur Kleinbuchstaben, Ziffern und Unterstriche erlaubt.")
    elif name in seen_names:
        fail("name", f"Name ist bereits an Position {seen_names[name] + 1} vergeben.")
    else:
        seen_names[name] = index

    prefix = device["entity_prefix"]
    if prefix and not _NAME_RE.match(prefix):
        fail("entity_prefix", "Nur Kleinbuchstaben, Ziffern und Unterstriche erlaubt.")
    elif prefix and prefix in seen_prefixes:
        fail("entity_prefix",
             f"Präfix ist bereits an Position {seen_prefixes[prefix] + 1} vergeben.")
    elif prefix:
        seen_prefixes[prefix] = index

    cls = device["class"]
    if cls not in DEVICE_CLASSES:
        fail("class", f"Zulässig sind {', '.join(DEVICE_CLASSES)}.")
        return errors

    # Leere Auswahl ist gültig: Nur-Energy-Pilot-Gerät.
    for mode in parse_modes(device["allowed_modes"]):
        if mode not in NORMAL_MODES:
            fail("allowed_modes", f"Unbekannter Regelmodus '{mode}'.")
            break
        if mode not in available:
            fail("allowed_modes",
                 f"Regelmodus '{mode}' ist global nicht aktiviert.")
            break

    if cls == "controllable":
        _validate_controllable(device, fail)
    elif cls == "binary":
        _validate_binary(device, fail)
    else:
        _validate_battery(device, fail)

    return errors


def _validate_controllable(device: Dict[str, Any], fail) -> None:
    _require_entity(device, "actual_power_entity", fail)

    if device["output_unit"] not in OUTPUT_UNITS:
        fail("output_unit", "Zulässig sind watt oder ampere.")
    if device["phases"] not in PHASE_VALUES:
        fail("phases", "Zulässig sind \"1\", \"3\" oder \"1,3\".")
    _optional_entity(device, "voltage_l1_entity", fail)
    _optional_entity(device, "voltage_l2_entity", fail)
    _optional_entity(device, "voltage_l3_entity", fail)

    unit = "A" if device["output_unit"] == "ampere" else "W"
    minimum = _number(device, "technical_minimum", fail, minimum=0.0,
                      text=f"Pflichtfeld: endliche Zahl ab 0 {unit}.")
    maximum = _number(device, "technical_maximum", fail, exclusive_minimum=0.0,
                      text=f"Pflichtfeld: endliche Zahl über 0 {unit}.")
    if minimum is not None and maximum is not None and maximum < minimum:
        fail("technical_maximum", "Muss mindestens so groß sein wie das technische Minimum.")

    _number(device, "increase_delay_s", fail, minimum=0.0,
            text="Pflichtfeld: endliche Zahl ab 0 Sekunden.")
    _number(device, "decrease_delay_s", fail, minimum=0.0,
            text="Pflichtfeld: endliche Zahl ab 0 Sekunden.")
    step_max = _number(device, "maximum_step_change", fail, exclusive_minimum=0.0,
                       text=f"Pflichtfeld: endliche Zahl über 0 {unit}.")
    step_min = _number(device, "minimum_step_change", fail, minimum=0.0,
                       text=f"Pflichtfeld: endliche Zahl ab 0 {unit}.")
    if step_min is not None and step_max is not None and step_min > step_max:
        fail("minimum_step_change", "Darf die maximale Änderung pro Schritt nicht übersteigen.")


def _validate_binary(device: Dict[str, Any], fail) -> None:
    _require_entity(device, "switch_entity", fail)
    _number(device, "power_w", fail, exclusive_minimum=0.0,
            text="Pflichtfeld: endliche Zahl über 0 W.")
    for key in ("on_reserve_w", "min_runtime_s", "min_offtime_s", "off_delay_s"):
        unit = "W" if key.endswith("_w") else "Sekunden"
        _number(device, key, fail, minimum=0.0,
                text=f"Pflichtfeld: endliche Zahl ab 0 {unit}.")


def _validate_battery(device: Dict[str, Any], fail) -> None:
    _require_entity(device, "soc_entity", fail)
    _require_entity(device, "available_charge_power_entity", fail)
    _require_entity(device, "available_discharge_power_entity", fail)

    signed = device["power_entity"]
    pair = (device["charge_power_entity"], device["discharge_power_entity"])
    if signed and any(pair):
        fail("power_entity",
             "Entweder ein signierter Sensor oder das Paar aus Lade- und "
             "Entladeleistung – nicht beides.")
    elif signed:
        _optional_entity(device, "power_entity", fail)
        if device["power_sign"] not in POWER_SIGNS:
            fail("power_sign", "Zulässig sind positiv_laden oder positiv_entladen.")
    elif all(pair):
        _optional_entity(device, "charge_power_entity", fail)
        _optional_entity(device, "discharge_power_entity", fail)
    else:
        fail("power_entity",
             "Pflicht: entweder power_entity oder charge_power_entity zusammen "
             "mit discharge_power_entity.")

    capacity = _as_float(device.get("capacity_kwh"), None)
    if capacity is None or not math.isfinite(capacity) or capacity < 0:
        fail("capacity_kwh", "Endliche Zahl ab 0 kWh erwartet.")

    _number(device, "soc_max_hysteresis_percent", fail, minimum=0.0, maximum=100.0,
            text="Endliche Zahl von 0 bis 100 Prozent erwartet.")
    _number(device, "direction_switch_delay_s", fail, minimum=0.0,
            text="Endliche Zahl ab 0 Sekunden erwartet.")


# ---------------------------------------------------------------------------
# Revision und Diff
# ---------------------------------------------------------------------------

def revision(raw_options: Optional[Dict[str, Any]]) -> str:
    """Kanonischer Hash über die ROHEN gespeicherten Optionen.

    Roh und nicht normalisiert: nur so fällt auch eine Änderung auf, die über
    die native Add-on-Seite an einem Feld vorgenommen wurde, das diese
    Oberfläche gar nicht anzeigt.
    """
    canonical = json.dumps(raw_options or {}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def devices_needing_shutdown(old_raw: Optional[Dict[str, Any]],
                             new_raw: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Alte Geräte, deren Ausgänge vor einem Neustart sicher zu setzen sind.

    Maßgeblich ist die ALTE, laufende Konfiguration: nur deren Schreibziele
    existieren gerade. Reine Änderungen an Log-Level, Intervall oder
    Post-Cycle-Skript brauchen keine Ausgangsänderung.
    """
    old = normalize_options(old_raw)
    new = normalize_options(new_raw)

    if any(old.get(key) != new.get(key) for key in GLOBAL_KEYS_FORCING_SHUTDOWN):
        return list(old["devices"])

    new_by_name = {device["name"]: device for device in new["devices"]}
    return [device for device in old["devices"]
            if new_by_name.get(device["name"]) != device]


def merge_known_fields(stored_raw: Optional[Dict[str, Any]],
                       draft: Dict[str, Any]) -> Dict[str, Any]:
    """Bekannte UI-Felder in die frisch gelesenen rohen Optionen mischen.

    Unbekannte künftige Top-Level-Felder bleiben dadurch erhalten – ein
    vollständiges Überschreiben würde sie stillschweigend löschen.
    """
    merged = dict(stored_raw or {})
    normalized = normalize_options(draft)
    for key in list(GLOBAL_DEFAULTS) + ["available_modes", "devices"]:
        merged[key] = normalized[key]
    return merged


# ---------------------------------------------------------------------------
# Kleine Helfer
# ---------------------------------------------------------------------------

def _as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_float(value: Any, default: Optional[float]) -> Optional[float]:
    if isinstance(value, bool) or value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _number(device: Dict[str, Any], key: str, fail, *, text: str,
            minimum: Optional[float] = None,
            exclusive_minimum: Optional[float] = None,
            maximum: Optional[float] = None) -> Optional[float]:
    value = device.get(key)
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail(key, text)
        return None
    if minimum is not None and value < minimum:
        fail(key, text)
        return None
    if exclusive_minimum is not None and value <= exclusive_minimum:
        fail(key, text)
        return None
    if maximum is not None and value > maximum:
        fail(key, text)
        return None
    return float(value)


def _require_entity(device: Dict[str, Any], key: str, fail) -> None:
    value = device.get(key) or ""
    if not value:
        fail(key, "Pflichtfeld: vollständige Entity-ID einer vorhandenen Entität.")
    elif not _ENTITY_RE.match(value):
        fail(key, "Vollständige Entity-ID erwartet, z. B. sensor.beispiel.")


def _optional_entity(device: Dict[str, Any], key: str, fail) -> None:
    value = device.get(key) or ""
    if value and not _ENTITY_RE.match(value):
        fail(key, "Vollständige Entity-ID erwartet, z. B. sensor.beispiel.")


def _short_path(path: str) -> str:
    """„devices[2].technical_maximum" → „technical_maximum" für die Gerätekarte."""
    return path.split(".", 1)[1] if "." in path else path
