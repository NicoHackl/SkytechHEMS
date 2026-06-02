"""
EMS device hierarchy.

Device (ABC)
├── ControllableDevice  – stufenlose Leistungsregelung (Heizstab, Wallbox)
└── BinaryDevice        – AN/AUS mit Zeitschutz (Heizlüfter)

Für einen neuen Gerätetyp: Klasse von Device ableiten, in controller._build_devices() eintragen.
Kein weiterer Code muss angefasst werden.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from .state import StateProxy, safe_float, parse_ts

log = logging.getLogger(__name__)


class Device(ABC):
    """Abstract base for all EMS-managed devices."""

    def __init__(self, id: str, allowed_modes: List[str],
                 entity_prefix: Optional[str] = None):
        self.id            = id
        self.priority: int = 99
        self.eligible      = False
        self._allowed_modes   = allowed_modes
        # entity_prefix defaults to id; override when HA naming diverges (e.g. wallbox_1 → wallbox)
        self._entity_prefix   = entity_prefix or id

    # ------------------------------------------------------------------
    # Eligibility (global + per-device freigabe/modus)
    # ------------------------------------------------------------------

    def check_eligible(self, st: StateProxy,
                       ems_enabled: bool, global_mode: str, hard_lockout: bool) -> bool:
        if not ems_enabled or hard_lockout or global_mode == "aus":
            return False
        if global_mode not in self._allowed_modes:
            return False
        return self._device_eligible(st)

    def _device_eligible(self, st: StateProxy) -> bool:
        pfx = self._entity_prefix
        freigabe = st.get(f"input_boolean.ems_{pfx}_freigabe") == "on"
        modus    = st.get(f"input_select.ems_{pfx}_modus")    == "auto"
        return freigabe and modus

    # ------------------------------------------------------------------
    # Polymorphic interface – implemented by each subclass
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def current_w(self) -> float:
        """Actual power draw used for pool back-calculation."""

    @property
    def max_relief_w(self) -> float:
        """Max power that can be shed immediately (for binary_immediate_off check)."""
        return 0.0

    @abstractmethod
    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        """Refresh config params and runtime sensor values from the HA state snapshot."""

    def consume_from_pool(self, remaining_w: float,
                          global_einschaltreserve_w: float) -> float:
        """Reserve / consume power from the prioritised pool. Returns updated remaining_w."""
        return remaining_w  # default: pass through

    def allocate(self, remaining_w: float) -> float:
        """Claim a slice of the remaining pool. Returns updated remaining_w."""
        return remaining_w  # default: pass through

    def calculate_ramp(self, current_deficit_w: float = 0.0) -> None:
        """Rate-limit the setpoint change. No-op for non-controllable devices."""

    @abstractmethod
    def get_write_ops(self) -> List[Tuple[str, str, Dict]]:
        """Return HA service calls: [(domain, service, data), ...]"""

    @abstractmethod
    def to_status_dict(self) -> Dict:
        """Snapshot for the web-UI /api/status endpoint."""


# =============================================================================
# ControllableDevice – stufenlose Leistungssteuerung
# =============================================================================

class ControllableDevice(Device):
    """Continuously variable setpoint device (e.g. Heizstab, Wallbox)."""

    def __init__(self, id: str, allowed_modes: List[str],
                 entity_actual_w: str, entity_anforderung_w: str,
                 entity_prefix: Optional[str] = None):
        super().__init__(id, allowed_modes, entity_prefix)
        self.entity_actual_w       = entity_actual_w
        self.entity_anforderung_w  = entity_anforderung_w

        # ---- Config params (refreshed from HA each cycle) ----
        self.min_technisch_w               = 0.0
        self.max_technisch_w               = 0.0
        self.geschuetzte_mindestleistung_w  = 0.0
        self.reserve_w                     = 0.0
        self.hoch_regelzeit_s              = 60.0
        self.runter_regelzeit_s            = 60.0
        self.max_anderung_pro_schritt_w    = 1000.0
        self.deadband_w                    = 0.0

        # ---- Runtime state (read from HA each cycle) ----
        # The setpoint entity stays in HA so external integrations (Modbus, etc.) can read it.
        self._actual_w              = 0.0
        self._anforderung_current_w = 0.0
        self._anforderung_age_s     = 0.0
        self._schutz_w              = 0.0

        # ---- Per-cycle results ----
        self._alloc_w = 0.0
        self._new_w   = 0.0

    # --- Exposed read-only state for controller logging ---
    @property
    def anforderung_current_w(self) -> float:
        return self._anforderung_current_w

    @property
    def new_w(self) -> float:
        return self._new_w

    @property
    def alloc_w(self) -> float:
        return self._alloc_w

    # --- Device interface ---

    @property
    def current_w(self) -> float:
        return self._actual_w

    @property
    def max_relief_w(self) -> float:
        return max(self._actual_w - self.min_technisch_w, 0.0) if self.eligible else 0.0

    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        pfx = self._entity_prefix

        def n(suffix: str, default: float = 0.0) -> float:
            return safe_float(st.get(f"input_number.ems_{pfx}_{suffix}"), default)

        self.priority                      = int(n("prioritat", self.priority))
        self.min_technisch_w               = n("min_technisch_w")
        self.max_technisch_w               = n("max_technisch_w")
        self.geschuetzte_mindestleistung_w  = n("geschutzte_mindestleistung_w")
        self.reserve_w                     = n("reserve_w")
        self.hoch_regelzeit_s              = n("hoch_regelzeit_s")
        self.runter_regelzeit_s            = n("runter_regelzeit_s")
        self.max_anderung_pro_schritt_w    = n("max_anderung_pro_schritt_w")
        self.deadband_w                    = n("min_anderung_pro_schritt_w")

        self._actual_w              = max(safe_float(st.get(self.entity_actual_w)), 0.0)
        self._anforderung_current_w = safe_float(st.get(self.entity_anforderung_w))
        self._anforderung_age_s     = now_ts - parse_ts(
            st.get(self.entity_anforderung_w + ".last_changed")
        )
        self._schutz_w = min(
            self.geschuetzte_mindestleistung_w + self.reserve_w + global_puffer_w,
            self.max_technisch_w,
        )

    def consume_from_pool(self, remaining_w: float, _: float) -> float:
        """Reserve schutz_w so binary devices cannot consume it."""
        return remaining_w - self._schutz_w if self.eligible else remaining_w

    def allocate(self, remaining_w: float) -> float:
        """Claim up to max_technisch_w from the remaining pool."""
        if not self.eligible or remaining_w <= 0:
            self._alloc_w = 0.0
            return remaining_w
        if self.min_technisch_w == 0 or remaining_w >= self.min_technisch_w:
            self._alloc_w = min(remaining_w, self.max_technisch_w)
        else:
            self._alloc_w = 0.0
        return remaining_w - self._alloc_w

    def calculate_ramp(self, current_deficit_w: float = 0.0) -> None:
        """Apply ramp-rate limiting; result stored in _new_w."""
        if not self.eligible:
            self._new_w = 0.0
            return

        ideal_w   = self._alloc_w
        current_w = self._anforderung_current_w
        age_s     = self._anforderung_age_s

        if ideal_w > current_w:
            new_w = (
                min(ideal_w, current_w + self.max_anderung_pro_schritt_w, self.max_technisch_w)
                if age_s >= self.hoch_regelzeit_s else current_w
            )
        elif ideal_w < current_w:
            if current_deficit_w > 0:
                new_w = ideal_w  # immediate ramp-down on deficit – no timing / step limit
            else:
                new_w = (
                    max(ideal_w, current_w - self.max_anderung_pro_schritt_w)
                    if age_s >= self.runter_regelzeit_s else current_w
                )
        else:
            new_w = current_w

        if 0 < new_w < self.min_technisch_w:
            new_w = self.min_technisch_w if ideal_w >= self.min_technisch_w else 0.0

        self._new_w = round(max(min(new_w, self.max_technisch_w), 0.0))

    def get_write_ops(self) -> List[Tuple[str, str, Dict]]:
        delta     = abs(self._new_w - self._anforderung_current_w)
        is_on_off = (self._new_w == 0) != (self._anforderung_current_w == 0)
        write     = is_on_off or self.deadband_w <= 0 or delta >= self.deadband_w

        if write:
            return [("input_number", "set_value", {
                "entity_id": self.entity_anforderung_w,
                "value":     self._new_w,
            })]
        self._new_w = self._anforderung_current_w  # deadband active – no write
        return []

    def to_status_dict(self) -> Dict:
        return {
            "type":                  "controllable",
            "id":                    self.id,
            "priority":              self.priority,
            "eligible":              self.eligible,
            "actual_w":              self._actual_w,
            "anforderung_current_w": self._anforderung_current_w,
            "alloc_w":               self._alloc_w,
            "new_w":                 self._new_w,
            "schutz_w":              self._schutz_w,
        }


# =============================================================================
# BinaryDevice – binärer Verbraucher mit Zeitschutz
# =============================================================================

class BinaryDevice(Device):
    """On/off device with min_runtime, min_offtime, and off_delay guards."""

    def __init__(self, id: str, allowed_modes: List[str],
                 entity_switch: str, entity_anforderung_an: str,
                 entity_prefix: Optional[str] = None):
        super().__init__(id, allowed_modes, entity_prefix)
        self.entity_switch         = entity_switch
        self.entity_anforderung_an = entity_anforderung_an
        # NOTE: entity_off_since removed – the two input_datetime HA helpers are replaced
        #       by the internal _off_since_ts variable below.

        # ---- Config params (refreshed from HA each cycle) ----
        self.power_w       = 0.0
        self.on_reserve_w  = 0.0
        self.min_runtime_s = 0.0
        self.min_offtime_s = 0.0
        self.off_delay_s   = 0.0

        # ---- Runtime state (read from HA each cycle) ----
        self._actual_on    = False
        self._switch_age_s = 0.0

        # ---- Internal persistent state (survives across cycles, replaces input_datetime) ----
        self._off_since_ts: float = 0.0  # 0.0 = timer not running

        # ---- Per-cycle computation ----
        self._desired_on   = False
        self._candidate_on = False
        self._final_on     = False

    # --- Exposed state for controller ---

    @property
    def actual_on(self) -> bool:
        return self._actual_on

    @property
    def desired_on(self) -> bool:
        return self._desired_on

    @property
    def candidate_on(self) -> bool:
        return self._candidate_on

    @property
    def final_on(self) -> bool:
        return self._final_on

    @final_on.setter
    def final_on(self, value: bool) -> None:
        self._final_on = value

    @property
    def in_min_runtime(self) -> bool:
        return self._actual_on and self._switch_age_s < self.min_runtime_s

    # --- Device interface ---

    @property
    def current_w(self) -> float:
        return self.power_w if self._actual_on else 0.0

    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        pfx = self._entity_prefix

        def n(suffix: str, default: float = 0.0) -> float:
            return safe_float(st.get(f"input_number.ems_{pfx}_{suffix}"), default)

        self.priority      = int(n("prioritat", self.priority))
        self.power_w       = n("leistung_w")
        self.on_reserve_w  = n("einschaltreserve_w")
        self.min_runtime_s = n("mindestlaufzeit_s")
        self.min_offtime_s = n("mindestauszeit_s")
        self.off_delay_s   = n("abschaltverzogerung_s")

        self._actual_on    = st.get(self.entity_switch) == "on"
        self._switch_age_s = now_ts - parse_ts(
            st.get(self.entity_switch + ".last_changed")
        )

    def consume_from_pool(self, remaining_w: float,
                          global_einschaltreserve_w: float) -> float:
        """Determine desired state via hysteresis; consume power_w if desired on."""
        if not self.eligible:
            return remaining_w
        on_threshold = self.power_w + self.on_reserve_w + global_einschaltreserve_w
        if self._actual_on:
            self._desired_on = remaining_w >= self.power_w
        else:
            self._desired_on = remaining_w >= on_threshold
        return remaining_w - self.power_w if self._desired_on else remaining_w

    def calculate_candidate(self, now_ts: float,
                             binary_immediate_off: bool) -> None:
        """Apply timing guards (min_runtime, off_delay, min_offtime) to desired state."""
        if not self.eligible:
            self._candidate_on = False
            self._off_since_ts = 0.0
            return

        if self._actual_on:
            if self._desired_on:
                self._candidate_on = True
                self._off_since_ts = 0.0
                return

            if binary_immediate_off:
                # Mindestlaufzeit schützt auch bei Notabschaltung
                if self._switch_age_s < self.min_runtime_s:
                    self._candidate_on = True
                    self._off_since_ts = 0.0
                else:
                    self._candidate_on = False
                return

            if self._switch_age_s < self.min_runtime_s:
                self._candidate_on = True
                self._off_since_ts = 0.0
                return

            # Start or continue the off_delay timer
            if self._off_since_ts <= 0:
                self._off_since_ts = now_ts

            pending_elapsed = now_ts - self._off_since_ts
            if self.off_delay_s == 0 or pending_elapsed >= self.off_delay_s:
                self._candidate_on = False
            else:
                self._candidate_on = True
        else:
            self._off_since_ts = 0.0
            self._candidate_on = (
                self._desired_on and self._switch_age_s >= self.min_offtime_s
            )

    def reset_off_timer(self) -> None:
        """Reset the off_delay timer. Called after priority cascade when device goes OFF."""
        self._off_since_ts = 0.0

    def get_write_ops(self) -> List[Tuple[str, str, Dict]]:
        svc = "turn_on" if self._final_on else "turn_off"
        return [("input_boolean", svc, {"entity_id": self.entity_anforderung_an})]

    def to_status_dict(self) -> Dict:
        return {
            "type":           "binary",
            "id":             self.id,
            "priority":       self.priority,
            "eligible":       self.eligible,
            "power_w":        self.power_w,
            "actual_on":      self._actual_on,
            "desired_on":     self._desired_on,
            "candidate_on":   self._candidate_on,
            "final_on":       self._final_on,
            "in_min_runtime": self.in_min_runtime,
            "switch_age_s":   round(self._switch_age_s),
            "min_runtime_s":  self.min_runtime_s,
            "min_offtime_s":  self.min_offtime_s,
        }
