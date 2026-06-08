"""
EMS-Gerätehierarchie.

Device (ABC)
├── ControllableDevice  – stufenlose Leistungsregelung (Heizstab, Wallbox)
└── BinaryDevice        – AN/AUS mit Zeitschutz (Heizlüfter)

Für einen neuen Gerätetyp: Klasse von Device ableiten und in
controller._build_devices() eintragen. Kein weiterer Code muss angefasst werden.
"""

import logging
import math
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from .state import StateProxy, safe_float, parse_ts

log = logging.getLogger(__name__)

# Schwelle (in Watt), unterhalb derer ein Leistungswert als „null" gilt.
# Vermeidet fragile exakte Float-Vergleiche (x == 0) bei aus Umrechnungen
# stammenden Werten.
EPS_W = 1.0


class Device(ABC):
    """Abstrakte Basis für alle vom EMS verwalteten Geräte."""

    def __init__(self, id: str, allowed_modes: List[str],
                 entity_prefix: Optional[str] = None,
                 label: Optional[str] = None):
        self.id            = id
        self.label         = label or id
        self.priority: int = 99
        self.eligible      = False
        self._allowed_modes  = allowed_modes
        self._entity_prefix  = entity_prefix or id
        # Zeitstempel des aktuellen Zyklus (einheitliche Zeitquelle, vom
        # Controller gesetzt). Wird auch von to_status_dict verwendet, damit
        # alle Zeitberechnungen denselben Bezugspunkt nutzen.
        self._now_ts: float = 0.0

    # ------------------------------------------------------------------
    # Freigabe (global + gerätespezifische Freigabe/Modus)
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
    # Polymorphe Schnittstelle – von jeder Unterklasse implementiert
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def current_w(self) -> float:
        """Tatsächliche Leistungsaufnahme zur Pool-Rückrechnung."""

    @property
    def max_relief_w(self) -> float:
        """Maximal sofort abregelbare Leistung (für binary_immediate_off-Prüfung)."""
        return 0.0

    @abstractmethod
    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        """Aktualisiert Konfigurationsparameter und Sensorwerte aus dem HA-Snapshot."""

    def consume_from_pool(self, remaining_w: float,
                          global_einschaltreserve_w: float) -> float:
        """Reserviert/verbraucht Leistung aus dem priorisierten Pool. Gibt aktualisiertes remaining_w zurück."""
        return remaining_w

    def calculate_ramp(self, current_deficit_w: float = 0.0) -> None:
        """Begrenzt die Sollwertänderung. Bei nicht regelbaren Geräten ein No-Op."""

    @abstractmethod
    def get_write_ops(self) -> List[Tuple[str, str, Dict]]:
        """Liefert HA-Service-Aufrufe: [(domain, service, data), ...]"""

    @abstractmethod
    def to_status_dict(self) -> Dict:
        """Snapshot für den /api/status-Endpunkt der Web-UI."""


# =============================================================================
# ControllableDevice – stufenlose Leistungssteuerung
# =============================================================================

class ControllableDevice(Device):
    """Stufenlos regelbares Gerät (z. B. Heizstab, Wallbox).

    output_unit='watt':   HA-Helfer nutzen das _w-Suffix; alle Werte in Watt.
    output_unit='ampere': HA-Helfer nutzen das _a-Suffix für gerätespezifische
                          Grenzwerte; Werte werden über Phasenanzahl × Spannung
                          zwischen W und A umgerechnet. Die Phasenanzahl wird je
                          Zyklus gewählt und nach input_number.ems_<prefix>_anzahl_phase
                          geschrieben.
    """

    def __init__(self, id: str, allowed_modes: List[str],
                 entity_actual_w: str, entity_anforderung_w: str,
                 entity_prefix: Optional[str] = None,
                 label: Optional[str] = None,
                 output_unit: str = 'watt',
                 allowed_phases: Optional[List[int]] = None,
                 voltage_l1_entity: Optional[str] = None,
                 voltage_l2_entity: Optional[str] = None,
                 voltage_l3_entity: Optional[str] = None,
                 phase_switch_delay_s: float = 300.0):
        super().__init__(id, allowed_modes, entity_prefix, label)
        self.entity_actual_w      = entity_actual_w
        self.entity_anforderung_w = entity_anforderung_w
        self.output_unit          = output_unit if output_unit in ('watt', 'ampere') else 'watt'
        self._allowed_phases               = sorted(set(allowed_phases or [1]))
        self.voltage_l1_entity             = voltage_l1_entity
        self.voltage_l2_entity             = voltage_l2_entity
        self.voltage_l3_entity             = voltage_l3_entity
        # Konfig-Fallback für die Phasenwechsel-Sperrzeit; HA-Entität überschreibt je Zyklus
        self._config_phase_switch_delay_s  = float(phase_switch_delay_s) if phase_switch_delay_s else 0.0
        self.phase_switch_delay_s          = self._config_phase_switch_delay_s or 30.0

        # ---- Konfig-Parameter (Watt; je Zyklus via _apply_raw_to_watt aktualisiert) ----
        self.min_technisch_w               = 0.0
        self.max_technisch_w               = 0.0
        self.geschuetzte_mindestleistung_w  = 0.0
        self.reserve_w                     = 0.0
        self.hoch_regelzeit_s              = 60.0
        self.runter_regelzeit_s            = 60.0
        self.max_anderung_pro_schritt_w    = 1000.0
        self.deadband_w                    = 0.0

        # ---- Rohwerte in nativer Einheit (A oder W) aus HA; je Zyklus nach W umgerechnet ----
        self._raw_min        = 0.0
        self._raw_max        = 0.0
        self._raw_geschuetzt = 0.0
        self._raw_max_change = 1000.0
        self._raw_deadband   = 0.0

        # ---- Laufzeitzustand ----
        self._actual_w              = 0.0
        self._anforderung_current_w = 0.0  # intern immer Watt
        self._anforderung_age_s     = 0.0
        self._schutz_w              = 0.0
        self._voltage_l1            = 230.0
        self._voltage_l2            = 230.0
        self._voltage_l3            = 230.0
        self._global_puffer_w       = 0.0
        self._current_phases        = self._allowed_phases[0]
        self._ha_phases             = self._allowed_phases[0]  # zuletzt aus HA gelesene Phasen
        self._last_phase_change_ts  = 0.0

        # ---- Ergebnisse pro Zyklus ----
        self._alloc_w = 0.0
        self._new_w   = 0.0

    # ------------------------------------------------------------------
    # Interne Hilfsfunktionen
    # ------------------------------------------------------------------

    def _suf(self, base: str) -> str:
        """Liefert das HA-Helfer-Suffix mit korrekter Einheit: base_a (Ampere) oder base_w (Watt)."""
        return f"{base}_{'a' if self.output_unit == 'ampere' else 'w'}"

    def _eff_for(self, phases: int) -> float:
        """Watt pro Ampere für eine gegebene Phasenanzahl anhand der Phasenspannungen.

        1-phasig: P = I × V_L1
        3-phasig: P = I × (V_L1 + V_L2 + V_L3)
        """
        if self.output_unit != 'ampere':
            return 1.0
        if phases == 1:
            return self._voltage_l1
        return self._voltage_l1 + self._voltage_l2 + self._voltage_l3

    def _eff(self) -> float:
        """Watt pro Ampere für die aktuell gewählte Phasenanzahl."""
        return self._eff_for(self._current_phases)

    def _apply_raw_to_watt(self) -> None:
        """Rechnet Rohwerte aus nativer Einheit nach Watt um (über _current_phases × Spannung).

        Berechnet außerdem _schutz_w neu, damit consume_from_pool stets einen
        konsistenten Wert nutzt – auch nach einem Phasenwechsel innerhalb des
        Zyklus via select_phases().
        """
        eff = self._eff()
        if self.output_unit == 'ampere':
            self.min_technisch_w              = self._raw_min        * eff
            self.max_technisch_w              = self._raw_max        * eff
            self.geschuetzte_mindestleistung_w = self._raw_geschuetzt * eff
            self.max_anderung_pro_schritt_w   = self._raw_max_change * eff
            self.deadband_w                   = self._raw_deadband   * eff
        else:
            self.min_technisch_w              = self._raw_min
            self.max_technisch_w              = self._raw_max
            self.geschuetzte_mindestleistung_w = self._raw_geschuetzt
            self.max_anderung_pro_schritt_w   = self._raw_max_change
            self.deadband_w                   = self._raw_deadband
        self._schutz_w = min(
            self.geschuetzte_mindestleistung_w + self.reserve_w + self._global_puffer_w,
            self.max_technisch_w,
        )

    # ------------------------------------------------------------------
    # Nur-Lese-Zustand für das Controller-Logging
    # ------------------------------------------------------------------

    @property
    def anforderung_current_w(self) -> float:
        return self._anforderung_current_w

    @property
    def new_w(self) -> float:
        return self._new_w

    @property
    def alloc_w(self) -> float:
        return self._alloc_w

    # ------------------------------------------------------------------
    # Device-Schnittstelle
    # ------------------------------------------------------------------

    @property
    def current_w(self) -> float:
        return self._actual_w

    @property
    def max_relief_w(self) -> float:
        return max(self._actual_w - self.min_technisch_w, 0.0) if self.eligible else 0.0

    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        self._now_ts = now_ts
        pfx = self._entity_prefix
        self._global_puffer_w = global_puffer_w

        def n(suffix: str, default: float = 0.0) -> float:
            return safe_float(st.get(f"input_number.ems_{pfx}_{suffix}"), default)

        # Phasenspannungen – Plausibilitätsprüfung 180–260 V je Phase, Fallback 230 V
        def _read_v(entity: Optional[str]) -> float:
            if not entity:
                return 230.0
            v = safe_float(st.get(entity), 0.0)
            return v if 180.0 < v < 260.0 else 230.0

        self._voltage_l1 = _read_v(self.voltage_l1_entity)
        self._voltage_l2 = _read_v(self.voltage_l2_entity)
        self._voltage_l3 = _read_v(self.voltage_l3_entity)

        # Phasenwechsel-Sperrzeit: HA-Entität > Konfig-Wert > 30 s harter Default
        if self.output_unit == 'ampere' and len(self._allowed_phases) > 1:
            raw_delay = st.get(f"input_number.ems_{pfx}_min_umschaltzeit_s")
            if raw_delay not in (None, "unavailable", "unknown"):
                ha_delay = safe_float(raw_delay, 0.0)
                self.phase_switch_delay_s = ha_delay if ha_delay > 0 else (self._config_phase_switch_delay_s or 30.0)
            else:
                self.phase_switch_delay_s = self._config_phase_switch_delay_s or 30.0

        # Im letzten Zyklus geschriebene Phasenanzahl – für korrektes Rücklesen der Anforderung
        if self.output_unit == 'ampere' and len(self._allowed_phases) > 1:
            ha_ph = int(safe_float(
                st.get(f"input_number.ems_{pfx}_anzahl_phase"), self._current_phases
            ))
            self._ha_phases = ha_ph if ha_ph in self._allowed_phases else self._current_phases
        else:
            self._ha_phases = self._current_phases

        self.priority           = int(n("prioritat", self.priority))
        self.reserve_w          = n("reserve_w")
        self.hoch_regelzeit_s   = n("hoch_regelzeit_s")
        self.runter_regelzeit_s = n("runter_regelzeit_s")

        # Rohwerte in nativer Einheit lesen (_a oder _w je nach output_unit)
        self._raw_min        = n(self._suf("min_technisch"))
        self._raw_max        = n(self._suf("max_technisch"))
        self._raw_geschuetzt = n(self._suf("geschutzte_mindestleistung"))
        self._raw_max_change = n(self._suf("max_anderung_pro_schritt"), 1000.0)
        self._raw_deadband   = n(self._suf("min_anderung_pro_schritt"), 0.0)

        # Nach Watt umrechnen mit aktueller Phasenanzahl (kann später von select_phases angepasst werden)
        self._apply_raw_to_watt()

        self._actual_w = max(safe_float(st.get(self.entity_actual_w)), 0.0)

        # Sollwert lesen; aus nativer Einheit nach Watt mit HA-Phasenanzahl umrechnen (für Genauigkeit)
        raw_anf = safe_float(st.get(self.entity_anforderung_w))
        if self.output_unit == 'ampere':
            self._anforderung_current_w = raw_anf * self._eff_for(self._ha_phases)
        else:
            self._anforderung_current_w = raw_anf

        self._anforderung_age_s = now_ts - parse_ts(
            st.get(self.entity_anforderung_w + ".last_changed")
        )

    def select_phases(self, pool_w: float, now_ts: float) -> None:
        """Wählt die Phasenanzahl für diesen Zyklus (zurückhaltende Umschaltstrategie).

        Ladestart (Sollwert == 0): die höchstmögliche Phasenanzahl wählen, für die
          der Pool das Minimum trägt. Reicht der Überschuss nur einphasig (z. B.
          2 kW), wird einphasig mit der daraus resultierenden Ampere-Zahl geladen.
        Aktives Laden (Sollwert > 0):
          - Bei der aktuellen Phasenanzahl bleiben, solange sie das Minimum noch trägt.
          - Nur HOCH schalten, wenn die aktuelle Phasenanzahl voll ausgereizt ist
            (Pool übersteigt max_a).
          - Nur RUNTER schalten, wenn die aktuelle Phasenanzahl das min_a nicht mehr trägt.
        Die Hysterese-Sperrzeit gilt nur im aktiven Laden, nicht beim Ladestart.
        """
        if self.output_unit != 'ampere' or len(self._allowed_phases) == 1 or not self.eligible:
            return

        is_initial_start = self._anforderung_current_w < EPS_W

        # Hysterese gilt nur während des aktiven Ladens
        if not is_initial_start:
            if (self._last_phase_change_ts > 0 and
                    now_ts - self._last_phase_change_ts < self.phase_switch_delay_s):
                return

        if is_initial_start:
            # Höchstmögliche Phasenanzahl, die der Pool am Minimum-Schwellwert trägt;
            # andernfalls Fallback auf die niedrigste Phasenanzahl (einphasig).
            selected = min(self._allowed_phases)  # Fallback: niedrigste
            for ph in sorted(self._allowed_phases, reverse=True):
                eff = self._eff_for(ph)
                if eff > 0 and math.floor(pool_w / eff) >= self._raw_min:
                    selected = ph
                    break
            reason = "Ladestart"
        else:
            # Zurückhaltend: nur umschalten, wenn erzwungen
            eff_cur = self._eff_for(self._current_phases)
            can_sustain = eff_cur > 0 and math.floor(pool_w / eff_cur) >= self._raw_min

            if can_sustain:
                # HOCH nur, wenn die aktuelle Phasenanzahl an der Maximalkapazität ist
                higher = [ph for ph in self._allowed_phases if ph > self._current_phases]
                if (higher and self._raw_max > 0 and eff_cur > 0
                        and math.floor(pool_w / eff_cur) >= self._raw_max):
                    selected = self._current_phases  # bleiben, sofern keine höhere Phase passt
                    for ph in sorted(higher):
                        eff = self._eff_for(ph)
                        if eff > 0 and math.floor(pool_w / eff) >= self._raw_min:
                            selected = ph
                            break
                    reason = "Hochschalten (max erreicht)"
                else:
                    selected = self._current_phases  # bleiben – kein Grund zu schalten
                    reason = ""
            else:
                # RUNTER: aktuelle Phasenanzahl trägt das Minimum nicht mehr
                lower = [ph for ph in self._allowed_phases if ph < self._current_phases]
                selected = min(self._allowed_phases)  # Fallback
                for ph in sorted(lower):
                    eff = self._eff_for(ph)
                    if eff > 0 and math.floor(pool_w / eff) >= self._raw_min:
                        selected = ph
                        break
                reason = "Runterschalten (min unterschritten)"

        if selected != self._current_phases:
            log.info("EMS [%s] Phasenwechsel %d→%d  pool=%.0fW  L1=%.1fV L2=%.1fV L3=%.1fV  (%s)",
                     self.id, self._current_phases, selected, pool_w,
                     self._voltage_l1, self._voltage_l2, self._voltage_l3, reason)
            self._current_phases = selected
            self._last_phase_change_ts = now_ts
            self._apply_raw_to_watt()
            self._anforderung_age_s = 0.0

    def consume_from_pool(self, remaining_w: float, _: float) -> float:
        """Reserviert schutz_w, damit binäre Geräte diese Leistung nicht verbrauchen."""
        return remaining_w - self._schutz_w if self.eligible else remaining_w

    def allocate_minimum(self, remaining_w: float) -> float:
        """Durchlauf 1: das effektive Minimum beanspruchen, damit niedriger-priore
        Geräte erst starten können, nachdem jedes höher-priore Gerät sein Minimum
        garantiert hat.
        Effektives Minimum = max(min_technisch_w, geschuetzte_mindestleistung_w)."""
        if not self.eligible or remaining_w <= 0:
            self._alloc_w = 0.0
            return remaining_w
        min_w = max(self.min_technisch_w, self.geschuetzte_mindestleistung_w)
        if min_w <= 0:
            # Kein Minimum definiert – vollständig dem Überschuss-Durchlauf überlassen
            self._alloc_w = 0.0
            return remaining_w
        if remaining_w >= min_w:
            self._alloc_w = min_w
            return remaining_w - min_w
        self._alloc_w = 0.0
        return remaining_w

    def allocate_surplus(self, remaining_w: float) -> float:
        """Durchlauf 2: nachdem alle Geräte ihr Minimum haben, den Überschuss in
        Prioritätsreihenfolge (höchste Priorität zuerst) bis max_technisch_w verteilen."""
        if not self.eligible or remaining_w <= 0:
            return remaining_w
        eff_min = max(self.min_technisch_w, self.geschuetzte_mindestleistung_w)
        if eff_min > 0 and self._alloc_w == 0:
            # Hat in Durchlauf 1 kein Minimum erhalten → Gerät bleibt aus
            return remaining_w
        additional = min(remaining_w, self.max_technisch_w - self._alloc_w)
        if additional > 0:
            self._alloc_w += additional
            return remaining_w - additional
        return remaining_w

    def calculate_ramp(self, current_deficit_w: float = 0.0) -> None:
        """Wendet die Rampenbegrenzung an; Ergebnis in _new_w."""
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
                new_w = ideal_w  # sofortiges Abregeln bei Defizit
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
        is_on_off = (self._new_w < EPS_W) != (self._anforderung_current_w < EPS_W)
        # Nur schreiben, wenn sich der Wert tatsächlich ändert – würde man jeden
        # Zyklus denselben Wert schreiben, setzte das last_changed zurück und
        # anforderung_age_s könnte nicht korrekt altern, was das Rampen-Timing
        # (hoch_regelzeit_s / runter_regelzeit_s) zerstört.
        write = is_on_off or (delta > 0 and (self.deadband_w <= 0 or delta >= self.deadband_w))

        ops: List[Tuple[str, str, Dict]] = []

        # Phasenanzahl nur schreiben, wenn sie sich geändert hat (hält die HA-Schreibanzahl niedrig)
        if self.output_unit == 'ampere' and self._current_phases != self._ha_phases:
            ops.append(("input_number", "set_value", {
                "entity_id": f"input_number.ems_{self._entity_prefix}_anzahl_phase",
                "value":     float(self._current_phases),
            }))

        if write:
            eff   = self._eff()
            value = math.floor(self._new_w / eff) if self.output_unit == 'ampere' and eff > 0 else self._new_w
            ops.append(("input_number", "set_value", {
                "entity_id": self.entity_anforderung_w,
                "value":     value,
            }))
        else:
            self._new_w = self._anforderung_current_w  # Deadband aktiv – kein Schreibvorgang

        return ops

    def to_status_dict(self) -> Dict:
        d: Dict = {
            "type":                  "controllable",
            "id":                    self.id,
            "label":                 self.label,
            "priority":              self.priority,
            "eligible":              self.eligible,
            "actual_w":              self._actual_w,
            "anforderung_current_w": self._anforderung_current_w,
            "alloc_w":               self._alloc_w,
            "new_w":                 self._new_w,
            "schutz_w":              self._schutz_w,
            "output_unit":           self.output_unit,
        }
        if self.output_unit == 'ampere':
            eff = self._eff()
            d["current_phases"]  = self._current_phases
            d["allowed_phases"]  = self._allowed_phases
            d["voltage_l1"]      = round(self._voltage_l1, 1)
            d["voltage_l2"]      = round(self._voltage_l2, 1)
            d["voltage_l3"]      = round(self._voltage_l3, 1)
            d["new_a"]           = math.floor(self._new_w / eff) if eff > 0 else 0
            if len(self._allowed_phases) > 1 and self._last_phase_change_ts > 0:
                remaining = self.phase_switch_delay_s - (self._now_ts - self._last_phase_change_ts)
                d["phase_lock_remaining_s"] = max(0.0, round(remaining))
        return d


# =============================================================================
# BinaryDevice – binärer Verbraucher mit Zeitschutz
# =============================================================================

class BinaryDevice(Device):
    """AN/AUS-Gerät mit Zeitschutz: Mindestlaufzeit, Mindestauszeit, Abschaltverzögerung."""

    def __init__(self, id: str, allowed_modes: List[str],
                 entity_switch: str, entity_anforderung_an: str,
                 entity_prefix: Optional[str] = None,
                 label: Optional[str] = None):
        super().__init__(id, allowed_modes, entity_prefix, label)
        self.entity_switch         = entity_switch
        self.entity_anforderung_an = entity_anforderung_an

        # ---- Konfig-Parameter (je Zyklus aus HA aktualisiert) ----
        self.power_w       = 0.0
        self.on_reserve_w  = 0.0
        self.min_runtime_s = 0.0
        self.min_offtime_s = 0.0
        self.off_delay_s   = 0.0

        # ---- Laufzeitzustand (je Zyklus aus HA gelesen) ----
        self._actual_on    = False
        self._switch_age_s = 0.0

        # ---- Interner persistenter Zustand (überlebt über Zyklen hinweg) ----
        self._off_since_ts: float = 0.0

        # ---- Berechnung pro Zyklus ----
        self._desired_on   = False
        self._candidate_on = False
        self._final_on     = False

    # --- Zustand für den Controller ---

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

    # --- Device-Schnittstelle ---

    @property
    def current_w(self) -> float:
        return self.power_w if self._actual_on else 0.0

    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        self._now_ts = now_ts
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
        """Bestimmt den Wunschzustand per Hysterese; verbraucht power_w wenn gewünscht an."""
        if not self.eligible:
            return remaining_w
        on_threshold = self.power_w + self.on_reserve_w + global_einschaltreserve_w
        if self._actual_on:
            self._desired_on = remaining_w >= self.power_w
        else:
            self._desired_on = remaining_w >= on_threshold
        return remaining_w - self.power_w if self._desired_on else remaining_w

    def calculate_candidate(self, now_ts: float) -> None:
        """Wendet die Zeit-Guards (Mindestlaufzeit, Abschaltverzögerung, Mindestauszeit) auf den Wunschzustand an.

        Mindestlaufzeit UND Abschaltverzögerung gelten IMMER – auch bei einer
        Notabschaltung (binary_immediate_off). Erst wenn das Gerät die
        Mindestlaufzeit erfüllt hat *und* die Abschaltverzögerung abgelaufen
        ist, wird der Aus-Befehl freigegeben.
        """
        if not self.eligible:
            self._candidate_on = False
            self._off_since_ts = 0.0
            return

        if self._actual_on:
            if self._desired_on:
                self._candidate_on = True
                self._off_since_ts = 0.0
                return

            if self._switch_age_s < self.min_runtime_s:
                self._candidate_on = True
                self._off_since_ts = 0.0
                return

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
        """Setzt den Abschaltverzögerungs-Timer zurück. Wird nach der Prioritätskaskade aufgerufen, wenn das Gerät AUS geht."""
        self._off_since_ts = 0.0

    def get_write_ops(self) -> List[Tuple[str, str, Dict]]:
        svc = "turn_on" if self._final_on else "turn_off"
        return [("input_boolean", svc, {"entity_id": self.entity_anforderung_an})]

    def to_status_dict(self) -> Dict:
        off_delay_remaining: Optional[float] = None
        if (self._actual_on and not self._desired_on
                and self._off_since_ts > 0 and self.off_delay_s > 0):
            off_delay_remaining = round(
                max(0.0, self.off_delay_s - (self._now_ts - self._off_since_ts))
            )
        return {
            "type":                 "binary",
            "id":                   self.id,
            "label":                self.label,
            "priority":             self.priority,
            "eligible":             self.eligible,
            "power_w":              self.power_w,
            "actual_on":            self._actual_on,
            "desired_on":           self._desired_on,
            "candidate_on":         self._candidate_on,
            "final_on":             self._final_on,
            "in_min_runtime":       self.in_min_runtime,
            "switch_age_s":         round(self._switch_age_s),
            "min_runtime_s":        self.min_runtime_s,
            "min_offtime_s":        self.min_offtime_s,
            "off_delay_remaining_s": off_delay_remaining,
        }
