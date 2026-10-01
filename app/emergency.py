"""Notabschaltung (D-059).

Eine konfigurierte Bedingung (Entität, Operator, Sollwert) wird jede Sekunde
geprüft. Trifft sie zu, wirft das HEMS sofort und ohne Ausnahme alle Lasten ab,
schickt die Geräte über eine frei konfigurierbare Zielliste zurück in ihre
eigene Automatik und hält danach still, bis ein Mensch quittiert.

Der Merker „Notabschaltung aktiv“ ist die einzige eigene Persistenz des
Add-ons: eine kleine JSON-Datei unter /data. Ein HA-Helfer reicht nicht, weil
der Merker auch dann gelten muss, wenn HA selbst neu startet oder den Helfer
verliert. `sensor.ems_notabschaltung_aktiv` spiegelt ihn nur zur Anzeige.

Ablauf der Abschaltfolge – einmal beim Auslösen und einmal nach jedem
Add-on-Start mit gesetztem Merker, danach schreibt das HEMS nichts mehr:

1. Alle konfigurierten Geräte auf ihren sicheren Zustand (0 W / aus / standby),
   ohne Zeitschutz, Rampe, Totband, Kaskade oder Zwang.
2. Das Post-Cycle-Skript, damit es die Helferwerte an die Geräte weiterreicht.
3. Die Zielzeilen in eingetragener Reihenfolge – die Automatik gewinnt zuletzt.

Fehlgeschlagene Befehle werden je Zyklus wiederholt, bis sie durchgehen;
erfolgreiche nie.
"""

import asyncio
import datetime
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from emergency_rules import (
    NUMERIC_OPERATORS,
    OPERATOR_LABELS,
    OPERATORS,
    TARGET_KINDS,
    TARGET_NUMBER,
    TARGET_ON_OFF,
    TARGET_OPTION,
    TARGET_PRESS,
    UNUSABLE_STATES,
    as_number,
    target_error,
)
from ems.ops import WriteOp, safe_shutdown_ops

log = logging.getLogger(__name__)

BERLIN = ZoneInfo("Europe/Berlin")
DISPLAY_TIME_FORMAT = "%d.%m.%Y %H:%M:%S"

OWNER = "notabschaltung"
SENSOR_ENTITY_ID = "sensor.ems_notabschaltung_aktiv"
LATCH_FILENAME = "notabschaltung.json"

CONDITION_MET = "met"
CONDITION_NOT_MET = "not_met"
CONDITION_INVALID = "invalid"


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

@dataclass
class EmergencyConfig:
    condition_entity: str = ""
    condition_operator: str = "=="
    condition_value: str = ""
    targets: List[Dict[str, str]] = field(default_factory=list)

    @property
    def configured(self) -> bool:
        return bool(self.condition_entity)

    @classmethod
    def from_options(cls, options: Dict[str, Any]) -> "EmergencyConfig":
        return cls(
            condition_entity=str(options.get("emergency_condition_entity") or ""),
            condition_operator=str(options.get("emergency_condition_operator") or "=="),
            condition_value=str(options.get("emergency_condition_value") or ""),
            targets=list(options.get("emergency_targets") or []),
        )


def target_op(entity: str, value: str) -> Optional[WriteOp]:
    """Der Service-Aufruf einer Zielzeile, oder None bei ungültiger Zeile."""
    if target_error(entity, value):
        return None
    domain = entity.split(".", 1)[0]
    kind = TARGET_KINDS[domain]
    data: Dict[str, Any] = {"entity_id": entity}
    if kind == TARGET_ON_OFF:
        return WriteOp(domain, "turn_on" if value == "on" else "turn_off", data, OWNER)
    if kind == TARGET_OPTION:
        return WriteOp(domain, "select_option", {**data, "option": value}, OWNER)
    if kind == TARGET_NUMBER:
        return WriteOp(domain, "set_value", {**data, "value": as_number(value)}, OWNER)
    if kind == TARGET_PRESS:
        return WriteOp(domain, "press", data, OWNER)
    return WriteOp("script", "turn_on", data, OWNER)


def target_ops(targets: List[Dict[str, str]]) -> List[WriteOp]:
    """Alle gültigen Zielzeilen in eingetragener Reihenfolge."""
    ops: List[WriteOp] = []
    for index, row in enumerate(targets):
        entity = str(row.get("entity") or "")
        op = target_op(entity, str(row.get("value") or ""))
        if op is None:
            log.error("Notabschaltung: Zielzeile %d (%s) ist ungültig und wird übersprungen.",
                      index + 1, entity or "ohne Entität")
            continue
        ops.append(op)
    return ops


def shutdown_ops(device_configs: List[Dict[str, Any]]) -> List[WriteOp]:
    """Sicherer Zustand für JEDES konfigurierte Gerät – auch für ungültige,
    gesperrte oder per Zwang laufende. Ohne Ausnahme heißt ohne Ausnahme."""
    return [op for config in device_configs for op in safe_shutdown_ops(config)]


def describe_op(op: WriteOp) -> str:
    """Kurzform für Panel und Log, z. B. „switch.turn_off switch.heizstab“."""
    return f"{op.domain}.{op.service} {op.data.get('entity_id', '')}".strip()


# ---------------------------------------------------------------------------
# Bedingung
# ---------------------------------------------------------------------------

@dataclass
class ConditionResult:
    state: str                     # met | not_met | invalid
    current: Optional[str] = None  # gemessener State, roh
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"state": self.state, "current": self.current, "reason": self.reason}


def evaluate(entity: str, operator: str, value: str,
             entry: Optional[Dict[str, Any]]) -> ConditionResult:
    """Wertet die Bedingung gegen einen HA-Zustand aus.

    `>`, `≥`, `<`, `≤` vergleichen nur Zahlen. `=` und `≠` vergleichen Zahlen
    numerisch („1.0“ = „1“), alles andere als Text ohne Groß-/Kleinschreibung.
    Nicht auswertbar ist nie „trifft zu“.
    """
    if entry is None:
        return ConditionResult(CONDITION_INVALID, None,
                               f"{entity} existiert in Home Assistant nicht.")
    raw = entry.get("state")
    current = None if raw is None else str(raw)
    if current is None or current.strip().lower() in UNUSABLE_STATES:
        return ConditionResult(CONDITION_INVALID, current,
                               f"{entity} meldet „{current or 'leer'}“.")
    if operator not in OPERATORS:
        return ConditionResult(CONDITION_INVALID, current, f"Unbekannter Operator „{operator}“.")

    label = OPERATOR_LABELS[operator]
    ist = as_number(current)
    soll = as_number(value)
    if operator in NUMERIC_OPERATORS:
        if ist is None:
            return ConditionResult(CONDITION_INVALID, current,
                                   f"{entity} meldet „{current}“ – keine Zahl.")
        if soll is None:
            return ConditionResult(CONDITION_INVALID, current,
                                   f"Sollwert „{value}“ ist keine Zahl.")
        met = {">": ist > soll, ">=": ist >= soll,
               "<": ist < soll, "<=": ist <= soll}[operator]
    elif ist is not None and soll is not None:
        met = (ist == soll) == (operator == "==")
    else:
        gleich = current.strip().casefold() == value.strip().casefold()
        met = gleich == (operator == "==")

    reason = f"{entity} = {current} (Bedingung: {label} {value})"
    return ConditionResult(CONDITION_MET if met else CONDITION_NOT_MET, current, reason)


# ---------------------------------------------------------------------------
# Merker
# ---------------------------------------------------------------------------

@dataclass
class Latch:
    active: bool = False
    since_iso: str = ""
    trigger: Dict[str, Any] = field(default_factory=dict)


class LatchStore:
    """Die Merkerdatei. Fehlend = nicht aktiv, kaputt = aktiv (fail-safe)."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Tuple[Latch, str]:
        if not self.path.exists():
            return Latch(), ""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("active"), bool):
                raise ValueError("Feld 'active' fehlt oder ist kein Wahrheitswert")
            trigger = data.get("trigger")
            return Latch(
                active=data["active"],
                since_iso=str(data.get("since") or ""),
                trigger=trigger if isinstance(trigger, dict) else {},
            ), ""
        except Exception as exc:
            return Latch(active=True), (
                f"Merkerdatei {self.path} ist unlesbar ({exc}) – Notabschaltung gilt als aktiv."
            )

    def save(self, latch: Latch) -> None:
        """Schreibt atomar. Wirft OSError, wenn das Dateisystem nicht mitspielt."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = {"active": latch.active, "since": latch.since_iso, "trigger": latch.trigger}
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)


def display_time(iso: str) -> str:
    """ISO-Zeitstempel → TT.MM.JJJJ hh:mm:ss in Berliner Zeit, ohne Offset."""
    if not iso:
        return ""
    try:
        moment = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BERLIN)
    return moment.astimezone(BERLIN).strftime(DISPLAY_TIME_FORMAT)


# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------

class EmergencyStop:
    """Zustand und Ablauf der Notabschaltung.

    `ha` braucht `execute_write_ops`, `call_service` und `set_state`. Der
    `write_lock` gehört allen Schreibern: der Regelzyklus hält ihn um seine
    Write-Ops, die Notabschaltung um ihre Folge. So landet nie ein Sollwert
    des Zyklus nach dem Abwurf.
    """

    def __init__(self, *, ha, store: LatchStore, config: EmergencyConfig,
                 device_configs: List[Dict[str, Any]], post_cycle_script: str = "",
                 config_error: str = "",
                 now: Callable[[], datetime.datetime] = lambda: datetime.datetime.now(BERLIN)):
        self._ha = ha
        self._store = store
        self.config = config
        self._device_configs = device_configs
        self._post_cycle_script = post_cycle_script
        self.config_error = config_error
        self._now = now
        self.write_lock = asyncio.Lock()

        self.active = False
        self.since_iso = ""
        self.trigger: Dict[str, Any] = {}
        self.pending_ops: List[WriteOp] = []
        self.last_condition: Optional[ConditionResult] = None
        self.file_error = ""
        self._sequence_due = False

    # -- Start ------------------------------------------------------------

    def load(self) -> None:
        """Liest den Merker. Ist er gesetzt, läuft die Folge im nächsten Zyklus erneut."""
        latch, error = self._store.load()
        self.file_error = error
        if error:
            log.error(error)
        if latch.active:
            self.active = True
            self.since_iso = latch.since_iso
            self.trigger = latch.trigger
            self._sequence_due = True
            log.error("Notabschaltung ist seit %s aktiv – HEMS bleibt bis zur Quittierung still.",
                      display_time(self.since_iso) or "unbekannt")

    # -- Bedingung --------------------------------------------------------

    def check(self, entry: Optional[Dict[str, Any]]) -> ConditionResult:
        cfg = self.config
        result = evaluate(cfg.condition_entity, cfg.condition_operator, cfg.condition_value, entry)
        self.last_condition = result
        return result

    def mark_unreachable(self, error: str) -> None:
        self.last_condition = ConditionResult(
            CONDITION_INVALID, None, f"Home Assistant nicht erreichbar: {error}")

    # -- Auslösen ---------------------------------------------------------

    def is_active(self) -> bool:
        """Abbruchprüfung für laufende Schreib-Chargen des Regelzyklus."""
        return self.active

    async def trigger_now(self, result: ConditionResult) -> None:
        if self.active:
            return
        # Ohne await bis hierher: eine zweite Auslösung sieht active bereits.
        self.active = True
        self.since_iso = self._now().replace(microsecond=0).isoformat()
        self.trigger = {
            "entity": self.config.condition_entity,
            "operator": self.config.condition_operator,
            "value": self.config.condition_value,
            "measured": result.current,
        }
        self._persist(Latch(True, self.since_iso, self.trigger))
        log.error("NOTABSCHALTUNG ausgelöst: %s %s %s (gemessen: %s) – alle Lasten werden abgeworfen.",
                  self.config.condition_entity,
                  OPERATOR_LABELS.get(self.config.condition_operator, self.config.condition_operator),
                  self.config.condition_value, result.current)
        async with self.write_lock:
            await self._run_sequence()

    async def run_due_sequence(self) -> None:
        """Nach einem Add-on-Start mit gesetztem Merker: Folge einmal erneut."""
        if not (self.active and self._sequence_due):
            return
        async with self.write_lock:
            await self._run_sequence()

    async def _run_sequence(self) -> None:
        self._sequence_due = False
        failed: List[WriteOp] = []

        results = await self._ha.execute_write_ops(shutdown_ops(self._device_configs))
        failed += [r.op for r in results if not r.ok]

        if self._post_cycle_script:
            script_op = WriteOp("script", "turn_on", {"entity_id": self._post_cycle_script}, OWNER)
            results = await self._ha.execute_write_ops([script_op])
            failed += [r.op for r in results if not r.ok]

        results = await self._ha.execute_write_ops(target_ops(self.config.targets))
        failed += [r.op for r in results if not r.ok]

        self.pending_ops = failed
        if failed:
            log.error("Notabschaltung: %d Befehl(e) fehlgeschlagen, Wiederholung je Zyklus: %s",
                      len(failed), ", ".join(describe_op(op) for op in failed))
        else:
            log.warning("Notabschaltung: Abschaltfolge vollständig ausgeführt.")
        await self.publish_sensor()

    async def retry_pending(self) -> None:
        """Wiederholt nur, was fehlgeschlagen ist – in ursprünglicher Reihenfolge."""
        if not (self.active and self.pending_ops):
            return
        async with self.write_lock:
            results = await self._ha.execute_write_ops(self.pending_ops)
            self.pending_ops = [r.op for r in results if not r.ok]
        if not self.pending_ops:
            log.warning("Notabschaltung: alle offenen Befehle nachgeholt.")

    # -- Quittieren -------------------------------------------------------

    def ack_block_reason(self) -> str:
        """Leer = Quittieren erlaubt (auf Basis der letzten Prüfung)."""
        if not self.active:
            return "Es ist keine Notabschaltung aktiv."
        if not self.config.configured:
            return ""
        result = self.last_condition
        if result is None:
            return "Bedingung wurde noch nicht geprüft."
        if result.state == CONDITION_MET:
            return f"Die Auslösebedingung trifft noch zu: {result.reason}"
        if result.state == CONDITION_INVALID:
            return f"Die Auslösebedingung ist nicht prüfbar: {result.reason}"
        return ""

    async def acknowledge(self, entry: Optional[Dict[str, Any]]) -> str:
        """Quittiert gegen einen frischen Zustand. Liefert den Sperrgrund, leer = quittiert."""
        if self.config.configured:
            self.check(entry)
        reason = self.ack_block_reason()
        if reason:
            return reason
        async with self.write_lock:
            try:
                self._store.save(Latch(False))
            except OSError as exc:
                self.file_error = f"Merkerdatei nicht beschreibbar: {exc}"
                log.error(self.file_error)
                return ("Quittieren nicht möglich: der Merker lässt sich nicht löschen und "
                        "käme nach einem Neustart zurück.")
            self.file_error = ""
            log.warning("Notabschaltung quittiert (aktiv seit %s) – HEMS regelt wieder.",
                        display_time(self.since_iso) or "unbekannt")
            self.active = False
            self.since_iso = ""
            self.trigger = {}
            self.pending_ops = []
            self._sequence_due = False
        await self.publish_sensor()
        return ""

    # -- Anzeige ----------------------------------------------------------

    def _persist(self, latch: Latch) -> None:
        try:
            self._store.save(latch)
            self.file_error = ""
        except OSError as exc:
            # Abgeworfen wird trotzdem: Sicherheit geht vor Merkfähigkeit.
            self.file_error = f"Merkerdatei nicht beschreibbar: {exc} – Neustart vergisst die Notabschaltung."
            log.error(self.file_error)

    def sensor_state(self) -> Tuple[str, Dict[str, Any]]:
        trigger = self.trigger or {}
        attributes: Dict[str, Any] = {
            "friendly_name": "HEMS Notabschaltung aktiv",
            "icon": "mdi:alert-octagon" if self.active else "mdi:shield-check",
            "seit": display_time(self.since_iso),
            "ausloeser_entity": trigger.get("entity", ""),
            "operator": OPERATOR_LABELS.get(trigger.get("operator", ""), ""),
            "sollwert": trigger.get("value", ""),
            "gemessener_wert": trigger.get("measured"),
            "offene_befehle": len(self.pending_ops),
        }
        return ("on" if self.active else "off"), attributes

    async def publish_sensor(self) -> None:
        state, attributes = self.sensor_state()
        await self._ha.set_state(SENSOR_ENTITY_ID, state, attributes)

    def to_status_dict(self) -> Dict[str, Any]:
        trigger = None
        if self.trigger:
            trigger = {
                **self.trigger,
                "operator_label": OPERATOR_LABELS.get(self.trigger.get("operator", ""), ""),
            }
        block = self.ack_block_reason() if self.active else ""
        return {
            "configured": self.config.configured,
            "config_error": self.config_error,
            "condition_entity": self.config.condition_entity,
            "condition_operator": self.config.condition_operator,
            "condition_operator_label": OPERATOR_LABELS.get(self.config.condition_operator, ""),
            "condition_value": self.config.condition_value,
            "active": self.active,
            "since": display_time(self.since_iso),
            "since_iso": self.since_iso,
            "trigger": trigger,
            "condition": self.last_condition.to_dict() if self.last_condition else None,
            "can_acknowledge": self.active and not block,
            "ack_block_reason": block,
            "pending_ops": [describe_op(op) for op in self.pending_ops],
            "file_error": self.file_error,
            "sensor_entity": SENSOR_ENTITY_ID,
        }
