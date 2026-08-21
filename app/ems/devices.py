"""
EMS-Gerätehierarchie.

Device (ABC)
├── ControllableDevice  – stufenlose Leistungsregelung (Heizstab, Wallbox)
│   └── BatteryDevice   – AC-gekoppelter Speicher, bidirektional
└── BinaryDevice        – AN/AUS mit Zeitschutz (Heizlüfter)

Für einen neuen Gerätetyp: Klasse von Device ableiten und in
controller._build_devices() eintragen. Kein weiterer Code muss angefasst werden.
"""

import logging
import math
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from .state import (
    StateProxy, Resolved, safe_float, parse_ts,
    STATE_VALID, STATE_INVALID, SOURCE_INTERNAL,
)

log = logging.getLogger(__name__)

# Schwelle (in Watt), unterhalb derer ein Leistungswert als „null" gilt.
# Vermeidet fragile exakte Float-Vergleiche (x == 0) bei aus Umrechnungen
# stammenden Werten.
EPS_W = 1.0
EP_COMMIT_ENTITY = "sensor.ep_plan_commit"


def _optional_number(value: Optional[float]) -> Optional[float]:
    """`None` bleibt `None` – nur so ist „kein Add-on-Wert" von `0` unterscheidbar."""
    return None if value is None else float(value)


class Device(ABC):
    """Abstrakte Basis für alle vom EMS verwalteten Geräte."""

    def __init__(self, id: str, allowed_modes: List[str],
                 entity_prefix: Optional[str] = None,
                 label: Optional[str] = None):
        self.id            = id
        self.label         = label or id
        self.priority: int = 99
        self.eligible      = False
        self.source        = "aus"        # Steuerquelle: 'aus' | 'user' | 'ep'
        self._allowed_modes  = allowed_modes
        self._entity_prefix  = entity_prefix or id
        # Zeitstempel des aktuellen Zyklus (einheitliche Zeitquelle, vom
        # Controller gesetzt). Wird auch von to_status_dict verwendet, damit
        # alle Zeitberechnungen denselben Bezugspunkt nutzen.
        self._now_ts: float = 0.0
        self._ep_proposal_status = "not_requested"
        # Je Zyklus gesammelte Entitätsdiagnose: {entity_id: {role, state, source}}.
        # Sie beantwortet die Frage, die vorher nur ein Debug-Log beantworten
        # konnte: welcher Wert wirkt gerade, und warum nicht der aus HA.
        self._entity_diagnostics: Dict[str, Dict[str, str]] = {}

    # Vom Nutzer wählbare Gerätemodi. `auto` = Energy Pilot, `manuell` = normale
    # Regeln, `aus` = gerätespezifischer Kill-Switch.
    DEVICE_MODES = ("auto", "manuell", "aus")

    def begin_cycle(self, now_ts: float) -> None:
        """Setzt die gemeinsame Zykluszeit und leert die Zyklusdiagnose."""
        self._now_ts = now_ts
        self._ep_proposal_status = "not_requested"
        self._entity_diagnostics = {}

    # ------------------------------------------------------------------
    # Diagnostizierte Auflösung – jede Klasse liest ausschließlich hierüber
    # ------------------------------------------------------------------

    @property
    def entity_diagnostics(self) -> Dict[str, Dict[str, str]]:
        return self._entity_diagnostics

    def _note(self, entity_id: str, role: str, resolved: Resolved) -> Resolved:
        """Merkt sich Ursache und Quelle eines gelesenen States."""
        self._entity_diagnostics[entity_id] = {
            "role":   role,
            "state":  resolved.state,
            "source": resolved.source,
        }
        return resolved

    def _num(self, st: StateProxy, entity_id: str, role: str, *,
             addon: Optional[float] = None, internal: Optional[float] = None,
             minimum: Optional[float] = None,
             maximum: Optional[float] = None) -> float:
        resolved = self._note(entity_id, role, st.resolve_number(
            entity_id, addon=addon, internal=internal,
            minimum=minimum, maximum=maximum,
        ))
        return 0.0 if resolved.value is None else float(resolved.value)

    def _flag(self, st: StateProxy, entity_id: str, role: str, *,
              fallback: bool = False,
              missing_fallback: Optional[bool] = None) -> bool:
        return bool(self._note(entity_id, role, st.resolve_bool(
            entity_id, fallback=fallback, missing_fallback=missing_fallback,
        )).value)

    def _choice(self, st: StateProxy, entity_id: str, role: str,
                options: Tuple[str, ...], *, fallback: str,
                addon: Optional[str] = None) -> str:
        return str(self._note(entity_id, role, st.resolve_select(
            entity_id, options, fallback=fallback, addon=addon,
        )).value)

    # ------------------------------------------------------------------
    # Freigabe (global + gerätespezifische Freigabe + technische Freigabe + Modus)
    # ------------------------------------------------------------------

    def resolve_source(self, st: StateProxy,
                       ems_enabled: bool, global_mode: str, hard_lockout: bool) -> str:
        """
        Steuerquelle bestimmen: 'aus' | 'user' | 'ep'.

        Überall gilt: auto = KI (Energy Pilot), manuell = normale Regeln, aus = aus.
          - global "auto"        -> alle Geräte 'ep' (außer per-Gerät modus == aus)
          - global manuell/nur_* -> per-Gerät modus entscheidet:
              auto    -> 'ep' (überspringt das nur_heizen/nur_laden-Typ-Gate)
              manuell -> 'user', sofern global im Typ-Gate self._allowed_modes liegt
              aus     -> 'aus'
        """
        # Bewusst vor dem Abbruch gelesen: der Gerätemodus gehört auch dann in
        # die Diagnose, wenn die Anlage global aus ist.
        modus = self._choice(st, f"input_select.ems_{self._entity_prefix}_modus",
                             "modus", self.DEVICE_MODES, fallback="manuell")
        if not ems_enabled or hard_lockout or global_mode == "aus":
            return "aus"
        # Per-Gerät-Kill gilt immer – auch bei global == "auto"
        if modus == "aus":
            return "aus"
        if global_mode == "auto":
            return "ep"
        if modus == "auto":
            return "ep"
        if global_mode not in self._allowed_modes:
            return "aus"
        return "user"

    def check_eligible(self, st: StateProxy) -> bool:
        """
        Freigabe-Prüfung je Steuerquelle (self.source vom Controller gesetzt).
        Die technische Freigabe bleibt IMMER hartes Gate, auch bei Quelle 'ep'.
        """
        if self.source == "aus":
            return False
        return self._device_eligible(st)

    def _device_eligible(self, st: StateProxy) -> bool:
        # _technische_freigabe (Gerät betriebsbereit) ist immer hartes Gate.
        # Bedien-Freigabe:
        #   Quelle 'user' -> Nutzer-Schalter _freigabe
        #   Quelle 'ep'   -> EP-Vorschlag freigabe (Fallback: Nutzer _freigabe)
        pfx = self._entity_prefix
        technische_freigabe = self._flag(
            st, f"input_boolean.ems_{pfx}_technische_freigabe", "technische_freigabe")
        user_freigabe = self._flag(st, f"input_boolean.ems_{pfx}_freigabe", "freigabe")
        if not technische_freigabe:
            return False
        if self.source == "ep":
            return self._ep_bool(st, "freigabe", user_freigabe)
        return user_freigabe

    # ------------------------------------------------------------------
    # EP-Vorschlagswerte (Energy Pilot) lesen – mit Fallback auf Nutzerwert.
    # Fällt ein Vorschlagssensor aus, greift der Nutzerwert (KI-Ausfall darf die
    # Anlage nie blockieren).
    # ------------------------------------------------------------------

    def _ep_entity(self, field: str) -> str:
        return f"sensor.ep_{self._entity_prefix}_{field}_vorschlag"

    def _mark_ep_failure(self, status: str) -> None:
        """Bewahrt den ersten Vorschlagsfehler eines Zyklus für die Diagnose."""
        if self._ep_proposal_status in ("not_requested", "valid"):
            self._ep_proposal_status = status

    def _ep_raw(self, st: StateProxy, field: str) -> object:
        """Liest nur einen vollständig publizierten und aktuell gültigen EP-Vorschlag."""
        entity_id = self._ep_entity(field)
        raw = st.get(entity_id)
        if raw in ("unavailable", "unknown", None):
            self._mark_ep_failure("missing_value")
            return None

        commit_plan_id = st.get(EP_COMMIT_ENTITY)
        commit_attrs = st.getattr(EP_COMMIT_ENTITY) or {}
        if commit_plan_id in ("unavailable", "unknown", None):
            self._mark_ep_failure("missing_commit")
            return None

        valid_from = parse_ts(commit_attrs.get("valid_from"))
        valid_until = parse_ts(commit_attrs.get("valid_until"))
        if valid_from <= 0 or valid_until <= valid_from:
            self._mark_ep_failure("invalid_commit")
            return None
        if self._now_ts < valid_from or self._now_ts >= valid_until:
            self._mark_ep_failure("expired_commit")
            return None

        proposal_attrs = st.getattr(entity_id) or {}
        proposal_from = parse_ts(proposal_attrs.get("valid_from"))
        proposal_until = parse_ts(proposal_attrs.get("valid_until"))
        if (
            str(proposal_attrs.get("plan_id") or "") != str(commit_plan_id)
            or proposal_from != valid_from
            or proposal_until != valid_until
        ):
            self._mark_ep_failure("mismatched_plan")
            return None

        if self._ep_proposal_status == "not_requested":
            self._ep_proposal_status = "valid"
        return raw

    def _ep_num(self, st: StateProxy, field: str, fallback: float) -> float:
        raw = self._ep_raw(st, field)
        if raw is None:
            return fallback
        return safe_float(raw, fallback)

    def _ep_bool(self, st: StateProxy, field: str, fallback: bool) -> bool:
        raw = self._ep_raw(st, field)
        if raw is None:
            return fallback
        return str(raw).lower() in ("on", "true", "1")

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

    @property
    def netz_support_w(self) -> float:
        """Leistung, die dieses Gerät AKTIV ins Hausnetz einspeist.

        Erhöht residual_w, ist aber kein PV-Überschuss und muss daher aus Pool-
        und Defizitrechnung herausgerechnet werden. Anders als current_w zählt
        hier IMMER der Messwert – auch eine Entladung, die das HEMS nicht selbst
        angefordert hat (Sollwert-Nachlauf, Feinregelung im Gerät), verfälscht
        den Pool. Für alle reinen Verbraucher: 0.0.
        """
        return 0.0

    @property
    def gemessene_last_w(self) -> float:
        """Gemessene Leistungsaufnahme, OHNE Force-Modus-Filter.

        Basis der Entladeplanung: Was hier zurückaddiert wird, gilt NICHT als
        Hausverbrauch und wird von einem Speicher nicht gedeckt. Anders als
        current_w ohne eligible-Gate und ohne Deckelung auf die HEMS-Anforderung
        – sobald eine Last den Netzpunkt verfälscht, zählt sie hier, unabhängig
        davon wer sie eingeschaltet hat.
        """
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
                 phase_switch_delay_s: float = 300.0,
                 technical_minimum: Optional[float] = None,
                 technical_maximum: Optional[float] = None,
                 increase_delay_s: Optional[float] = None,
                 decrease_delay_s: Optional[float] = None,
                 maximum_step_change: Optional[float] = None,
                 minimum_step_change: Optional[float] = None):
        super().__init__(id, allowed_modes, entity_prefix, label)
        self.entity_actual_w      = entity_actual_w
        self.entity_anforderung_w = entity_anforderung_w
        self.output_unit          = output_unit if output_unit in ('watt', 'ampere') else 'watt'
        self._allowed_phases               = sorted(set(allowed_phases or [1]))
        self.voltage_l1_entity             = voltage_l1_entity
        self.voltage_l2_entity             = voltage_l2_entity
        self.voltage_l3_entity             = voltage_l3_entity
        # Konfig-Fallback für die Phasenwechsel-Sperrzeit; ein gültiger HA-State
        # überschreibt ihn je Zyklus – auch ein gültiger Wert 0.
        self._config_phase_switch_delay_s  = (
            None if phase_switch_delay_s is None else float(phase_switch_delay_s))
        self.phase_switch_delay_s          = (
            30.0 if self._config_phase_switch_delay_s is None
            else self._config_phase_switch_delay_s)

        # ---- Verpflichtende Add-on-Fallbacks in NATIVER Einheit (W oder A) ----
        # Sie greifen bei fehlender, nicht verfügbarer und ungültiger HA-Entität
        # gleichermaßen; verschieden ist nur die gemeldete Ursache. `None` heißt
        # „kein Add-on-Wert" und kommt nur beim Speicher und in Unit-Tests vor,
        # die die Grenzen direkt setzen.
        self._addon_technical_minimum   = _optional_number(technical_minimum)
        self._addon_technical_maximum   = _optional_number(technical_maximum)
        self._addon_increase_delay_s    = _optional_number(increase_delay_s)
        self._addon_decrease_delay_s    = _optional_number(decrease_delay_s)
        self._addon_maximum_step_change = _optional_number(maximum_step_change)
        self._addon_minimum_step_change = _optional_number(minimum_step_change)

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

    def _hems_power_w(self) -> float:
        """Tatsächliche Leistung, soweit sie vom HEMS angefordert wurde.

        Wird das Gerät extern angesteuert (Force-Modus außerhalb des HEMS), liegt
        _actual_w über der Anforderung. Dieser Anteil ist für das HEMS nicht
        freigebbar und darf daher weder in den Pool zurückgerechnet noch als
        abregelbare Entlastung gezählt werden.
        """
        if not self.eligible:
            return 0.0
        return min(self._actual_w, self._anforderung_current_w)

    @property
    def current_w(self) -> float:
        return self._hems_power_w()

    @property
    def max_relief_w(self) -> float:
        return max(self._hems_power_w() - self.min_technisch_w, 0.0)

    @property
    def gemessene_last_w(self) -> float:
        # Bewusst der rohe Messwert: kein eligible-Gate, keine Deckelung auf die
        # Anforderung. Ein extern erzwungener Heizstab ist Überschussverbraucher
        # und bleibt es, auch wenn das HEMS ihn gerade nicht angefordert hat.
        return self._actual_w

    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        self._now_ts = now_ts
        pfx = self._entity_prefix
        self._global_puffer_w = global_puffer_w

        def helper(suffix: str) -> str:
            return f"input_number.ems_{pfx}_{suffix}"

        self._voltage_l1 = self._read_voltage(st, self.voltage_l1_entity, "voltage_l1")
        self._voltage_l2 = self._read_voltage(st, self.voltage_l2_entity, "voltage_l2")
        self._voltage_l3 = self._read_voltage(st, self.voltage_l3_entity, "voltage_l3")

        # Phasenwechsel-Sperrzeit: gültiger HA-State (auch 0) > Add-on-Feld > 30 s.
        if self.output_unit == 'ampere' and len(self._allowed_phases) > 1:
            self.phase_switch_delay_s = self._num(
                st, helper("min_umschaltzeit_s"), "phase_switch_delay_s",
                addon=self._config_phase_switch_delay_s, internal=30.0, minimum=0.0,
            )
            # Im letzten Zyklus geschriebene Phasenanzahl – für korrektes Rücklesen
            ha_ph = int(self._num(st, helper("anzahl_phase"), "phase_count",
                                  internal=float(self._current_phases)))
            self._ha_phases = ha_ph if ha_ph in self._allowed_phases else self._current_phases
        else:
            self._ha_phases = self._current_phases

        self.priority  = int(self._num(st, helper("prioritat"), "prioritat", internal=99.0))
        # reserve_w ist auch im Ampere-Modus immer Watt und hat kein Add-on-Feld.
        self.reserve_w = self._num(st, helper("reserve_w"), "reserve_w",
                                   internal=0.0, minimum=0.0)
        self.hoch_regelzeit_s = self._num(
            st, helper("hoch_regelzeit_s"), "increase_delay_s",
            addon=self._addon_increase_delay_s, internal=0.0, minimum=0.0)
        self.runter_regelzeit_s = self._num(
            st, helper("runter_regelzeit_s"), "decrease_delay_s",
            addon=self._addon_decrease_delay_s, internal=0.0, minimum=0.0)

        # Rohwerte in nativer Einheit lesen (_a oder _w je nach output_unit).
        # Die Add-on-Fallbacks liegen in derselben Einheit; die Umrechnung nach
        # Watt passiert erst danach in _apply_raw_to_watt().
        self._raw_min = self._num(
            st, helper(self._suf("min_technisch")), "technical_minimum",
            addon=self._addon_technical_minimum, internal=0.0, minimum=0.0)
        self._raw_max = self._num(
            st, helper(self._suf("max_technisch")), "technical_maximum",
            addon=self._addon_technical_maximum, internal=0.0, minimum=0.0)
        self._raw_geschuetzt = self._num(
            st, helper(self._suf("geschutzte_mindestleistung")), "geschutzte_mindestleistung",
            internal=0.0, minimum=0.0)
        self._raw_max_change = self._num(
            st, helper(self._suf("max_anderung_pro_schritt")), "maximum_step_change",
            addon=self._addon_maximum_step_change, internal=1000.0, minimum=0.0)
        self._raw_deadband = self._num(
            st, helper(self._suf("min_anderung_pro_schritt")), "minimum_step_change",
            addon=self._addon_minimum_step_change, internal=0.0, minimum=0.0)

        # EP-Übernahme: Priorität und geschützte Mindestleistung aus dem Vorschlag.
        # EP liefert die Mindestleistung nur in Watt -> nur bei output_unit=watt
        # übernehmen; im Ampere-Modus greift der Fallback (Nutzerwert bleibt).
        if self.source == "ep":
            self.priority = int(self._ep_num(st, "prio", self.priority))
            if self.output_unit == "watt":
                self._raw_geschuetzt = self._ep_num(
                    st, "geschutzte_mindestleistung_w", self._raw_geschuetzt
                )

        # Nach Watt umrechnen mit aktueller Phasenanzahl (kann später von select_phases angepasst werden)
        self._apply_raw_to_watt()

        self._actual_w = max(
            self._num(st, self.entity_actual_w, "actual_power", internal=0.0), 0.0)

        # Sollwert lesen; aus nativer Einheit nach Watt mit HA-Phasenanzahl umrechnen (für Genauigkeit)
        raw_anf = self._num(st, self.entity_anforderung_w, "request", internal=0.0)
        if self.output_unit == 'ampere':
            self._anforderung_current_w = raw_anf * self._eff_for(self._ha_phases)
        else:
            self._anforderung_current_w = raw_anf

        self._anforderung_age_s = now_ts - parse_ts(
            st.get(self.entity_anforderung_w + ".last_changed")
        )

    def _read_voltage(self, st: StateProxy, entity: Optional[str], role: str) -> float:
        """Phasenspannung mit Plausibilitätsprüfung 180 < U < 260 V, sonst 230 V.

        Ein Wert außerhalb des Fensters ist kein Messwert, sondern ein
        Sensorfehler – und wird deshalb als `invalid` gemeldet, nicht als gültig.
        """
        if not entity:
            return 230.0
        resolved = st.resolve_number(entity, internal=230.0)
        if resolved.state == STATE_VALID and not (180.0 < float(resolved.value) < 260.0):
            resolved = Resolved(230.0, STATE_INVALID, SOURCE_INTERNAL)
        self._note(entity, role, resolved)
        return float(resolved.value)

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
        """Durchlauf 1: das technische Minimum beanspruchen, damit niedriger-priore
        Geräte erst starten können, nachdem jedes höher-priore Gerät sein Minimum
        garantiert hat.

        Schwelle ist AUSSCHLIESSLICH min_technisch_w – die technische Untergrenze,
        ab der das Gerät überhaupt laufen kann. geschuetzte_mindestleistung_w ist
        bewusst NICHT Teil dieser Schwelle: Sie ist reine Reservierung gegen binäre
        Verbraucher (via _schutz_w in consume_from_pool) und darf das Gerät nicht
        ausschalten, wenn der Pool zwar min_technisch_w trägt, aber nicht die volle
        geschützte Leistung."""
        if not self.eligible or remaining_w <= 0:
            self._alloc_w = 0.0
            return remaining_w
        min_w = self.min_technisch_w
        if min_w <= 0:
            # Keine technische Untergrenze – vollständig dem Überschuss-Durchlauf überlassen
            self._alloc_w = 0.0
            return remaining_w
        if remaining_w >= min_w:
            self._alloc_w = min_w
            return remaining_w - min_w
        self._alloc_w = 0.0
        return remaining_w

    def allocate_surplus(self, remaining_w: float) -> float:
        """Durchlauf 2: nachdem alle Geräte ihr technisches Minimum haben, den
        Überschuss in Prioritätsreihenfolge (höchste Priorität zuerst) bis
        max_technisch_w verteilen."""
        if not self.eligible or remaining_w <= 0:
            return remaining_w
        if self.min_technisch_w > 0 and self._alloc_w == 0:
            # Hat in Durchlauf 1 das technische Minimum nicht erhalten → Gerät bleibt aus
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
            "source":                self.source,
            "ep_proposal_status":    self._ep_proposal_status,
            "entity_diagnostics":    self._entity_diagnostics,
            "actual_w":              self._actual_w,
            "anforderung_current_w": self._anforderung_current_w,
            "alloc_w":               self._alloc_w,
            "new_w":                 self._new_w,
            "schutz_w":              self._schutz_w,
            # Roher, vom User gepflegter Schutz-Sockel (ohne Reserve/Puffer). schutz_w ist
            # der effektive Schutz (Sockel + reserve_w + global_puffer_w, geklemmt) und darf
            # NICHT als "geschützte Mindestleistung" verglichen/angezeigt werden – dafür ist
            # dieser Rohwert da (Energy-Pilot Plan-Rückkopplung).
            "geschuetzte_mindestleistung_w": self.geschuetzte_mindestleistung_w,
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
            # Effektiver Mindestleistungs-Schutz in Ampere (schutz_w über Phasen×Spannung
            # zurückgerechnet), damit Ampere-Konsumenten (Energy Pilot) einheitengleich
            # vergleichen können – analog zu new_a. Kein floor: Schutz nicht unterschätzen.
            d["schutz_a"]        = round(self._schutz_w / eff, 2) if eff > 0 else 0.0
            # Roher Schutz-Sockel in Ampere (nativer Nutzerwert, ohne Reserve/Puffer) –
            # Pendant zu geschuetzte_mindestleistung_w für den einheitengleichen EP-Vergleich.
            d["geschuetzte_mindestleistung_a"] = round(self._raw_geschuetzt, 2)
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
                 label: Optional[str] = None,
                 power_w: Optional[float] = None,
                 on_reserve_w: Optional[float] = None,
                 min_runtime_s: Optional[float] = None,
                 min_offtime_s: Optional[float] = None,
                 off_delay_s: Optional[float] = None):
        super().__init__(id, allowed_modes, entity_prefix, label)
        self.entity_switch         = entity_switch
        self.entity_anforderung_an = entity_anforderung_an

        # ---- Verpflichtende Add-on-Fallbacks (Watt bzw. Sekunden) ----
        # Ein fehlender Helfer ließ ein binäres Gerät bisher still mit
        # leistung_w = 0 weiterlaufen und machte die Pool-Rechnung unbrauchbar.
        self._addon_power_w       = _optional_number(power_w)
        self._addon_on_reserve_w  = _optional_number(on_reserve_w)
        self._addon_min_runtime_s = _optional_number(min_runtime_s)
        self._addon_min_offtime_s = _optional_number(min_offtime_s)
        self._addon_off_delay_s   = _optional_number(off_delay_s)

        # ---- Konfig-Parameter (je Zyklus aus HA aktualisiert) ----
        self.power_w       = 0.0
        self.on_reserve_w  = 0.0
        self.min_runtime_s = 0.0
        self.min_offtime_s = 0.0
        self.off_delay_s   = 0.0

        # ---- Laufzeitzustand (je Zyklus aus HA gelesen) ----
        self._actual_on       = False
        self._anforderung_an  = False
        self._switch_age_s    = 0.0

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
    def anforderung_an(self) -> bool:
        return self._anforderung_an

    @property
    def current_w(self) -> float:
        # Nur Leistung zurückrechnen, die das HEMS selbst angefordert hat. Ein extern
        # (Force-Modus) eingeschalteter Schalter ist für das HEMS nicht freigebbar; seine
        # Last steckt bereits in residual_w und darf den Pool nicht zusätzlich aufblähen.
        return self.power_w if (self._actual_on and self._anforderung_an) else 0.0

    @property
    def gemessene_last_w(self) -> float:
        # Gegenstück zu current_w: hier zählt der Schalterzustand allein, auch
        # ohne HEMS-Anforderung (Force-Modus).
        return self.power_w if self._actual_on else 0.0

    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        self._now_ts = now_ts
        pfx = self._entity_prefix

        def helper(suffix: str) -> str:
            return f"input_number.ems_{pfx}_{suffix}"

        self.priority = int(self._num(st, helper("prioritat"), "prioritat", internal=99.0))
        self.power_w = self._num(st, helper("leistung_w"), "power_w",
                                 addon=self._addon_power_w, internal=0.0, minimum=0.0)
        self.on_reserve_w = self._num(st, helper("einschaltreserve_w"), "on_reserve_w",
                                      addon=self._addon_on_reserve_w, internal=0.0, minimum=0.0)
        self.min_runtime_s = self._num(st, helper("mindestlaufzeit_s"), "min_runtime_s",
                                       addon=self._addon_min_runtime_s, internal=0.0, minimum=0.0)
        self.min_offtime_s = self._num(st, helper("mindestauszeit_s"), "min_offtime_s",
                                       addon=self._addon_min_offtime_s, internal=0.0, minimum=0.0)
        self.off_delay_s = self._num(st, helper("abschaltverzogerung_s"), "off_delay_s",
                                     addon=self._addon_off_delay_s, internal=0.0, minimum=0.0)

        # EP-Übernahme: Priorität aus dem Vorschlag (Fallback: Nutzerwert)
        if self.source == "ep":
            self.priority = int(self._ep_num(st, "prio", self.priority))

        self._actual_on      = self._flag(st, self.entity_switch, "switch")
        self._anforderung_an = self._flag(st, self.entity_anforderung_an, "request")
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
            "source":               self.source,
            "ep_proposal_status":   self._ep_proposal_status,
            "entity_diagnostics":   self._entity_diagnostics,
            "power_w":              self.power_w,
            "actual_on":            self._actual_on,
            "anforderung_an":       self._anforderung_an,
            "desired_on":           self._desired_on,
            "candidate_on":         self._candidate_on,
            "final_on":             self._final_on,
            "in_min_runtime":       self.in_min_runtime,
            "switch_age_s":         round(self._switch_age_s),
            "min_runtime_s":        self.min_runtime_s,
            "min_offtime_s":        self.min_offtime_s,
            "off_delay_remaining_s": off_delay_remaining,
        }


# =============================================================================
# BatteryDevice – AC-gekoppelter Speicher, bidirektional
# =============================================================================

class BatteryDevice(ControllableDevice):
    """AC-gekoppelter Batteriespeicher, vollständig vom HEMS geregelt.

    Der Speicher regelt NICHT selbst auf Netzpunkt +-0 – das macht das HEMS.
    Geschrieben werden wie überall nur HA-Helfer; die Übersetzung nach
    Modbus/MQTT übernimmt eine HA-Automation.

    Ladepfad:    geerbter ControllableDevice-Pfad (Pool-Allokation, Rampe,
                 Deadband), nur durch SoC- und Freigabe-Gates begrenzt.
    Entladepfad: Ziel wird vom Controller zugeteilt (_allocate_discharge), hier
                 nur begrenzt, asymmetrisch gerampt und geschrieben.

    Ausgabe (D-B20): EIN signierter Sollwert (+ laden / - entladen) plus die
    Betriebsart. Deshalb gibt es genau ein last_changed und damit auch nur eine
    Rampen-Alterung für beide Richtungen.

    Invariante: _new_lade_w == 0 oder _new_entlade_w == 0.
    """

    # Vom Nutzer wählbare Betriebsarten. 'inverter' gibt es bewusst nicht:
    # ohne autonome Rückfallregelung im Gerät wäre der Zustand nicht erreichbar.
    BETRIEBSARTEN = ("auto", "nur_laden", "nur_entladen", "standby")

    def __init__(self, id: str, allowed_modes: List[str], *,
                 soc_entity: str,
                 charge_power_entity: Optional[str] = None,
                 discharge_power_entity: Optional[str] = None,
                 power_entity: Optional[str] = None,
                 power_sign: str = "positiv_laden",
                 available_charge_power_entity: Optional[str] = None,
                 available_discharge_power_entity: Optional[str] = None,
                 capacity_kwh: float = 0.0,
                 entity_prefix: Optional[str] = None,
                 label: Optional[str] = None):
        prefix = entity_prefix or id
        super().__init__(
            id, allowed_modes,
            entity_actual_w=charge_power_entity or power_entity or "",
            entity_anforderung_w=f"input_number.ems_{prefix}_anforderung_leistung_w",
            entity_prefix=prefix,
            label=label,
            output_unit="watt",          # Speicher werden immer in Watt geregelt
        )
        self.soc_entity                       = soc_entity
        self.charge_power_entity              = charge_power_entity
        self.discharge_power_entity           = discharge_power_entity
        self.power_entity                     = power_entity
        self.power_sign                       = (power_sign if power_sign in
                                                 ("positiv_laden", "positiv_entladen")
                                                 else "positiv_laden")
        self.available_charge_power_entity    = available_charge_power_entity
        self.available_discharge_power_entity = available_discharge_power_entity
        self.capacity_kwh                     = float(capacity_kwh or 0.0)

        # ---- Konfig-Parameter (je Zyklus aus HA aktualisiert) ----
        self.entlade_priority          = 50
        self.max_ladeleistung_w        = 0.0
        self.min_ladeleistung_w        = 0.0
        self.max_entladeleistung_w     = 0.0
        self.min_entladeleistung_w     = 0.0
        self.soc_min_prozent           = 10.0
        self.soc_max_prozent           = 100.0
        self.soc_reserve_prozent       = 0.0
        self.soc_taper_band_prozent    = 5.0
        self.soc_max_hysterese_prozent = 2.0
        self.entlade_sofort_schwelle_w = 300.0
        self.umschalt_totzone_w        = 100.0
        self.min_umschaltzeit_s        = 300.0
        self.laden_erlaubt             = False
        self.entladen_erlaubt          = False
        self.betriebsart               = "standby"
        # v2 (Netzladen). In v1 hält die Klemme in calculate_ramp den Pfad zu;
        # die Felder existieren, damit später keine Config-Migration nötig ist.
        self.netzladen_aktiv           = False
        self.netzlade_leistung_w       = 0.0

        # ---- Laufzeitzustand aus HA ----
        self._soc            = 0.0
        self._soc_valid      = False
        self._power_valid    = False
        self._lade_ist_w     = 0.0
        self._entlade_ist_w  = 0.0
        self._lade_anf_w     = 0.0
        self._entlade_anf_w  = 0.0
        self._betriebsart_anf: Optional[str] = None
        self._wr_lade_limit_w:    Optional[float] = None
        self._wr_entlade_limit_w: Optional[float] = None

        # ---- Interner Zustand, überlebt Zyklen ----
        self._last_direction_change_ts: float = 0.0
        self._soc_max_latch = False

        # ---- Ergebnisse pro Zyklus ----
        self._entlade_ziel_w        = 0.0
        self._new_lade_w            = 0.0
        self._new_entlade_w         = 0.0
        self._new_betriebsart       = "standby"
        self._lade_block:    Optional[str] = None
        self._entlade_block: Optional[str] = None
        self._blockiert_grund: Optional[str] = None

    # ------------------------------------------------------------------
    # Nur-Lese-Zustand für Controller, Tests und Statusanzeige
    # ------------------------------------------------------------------

    @property
    def soc_prozent(self) -> float:
        return self._soc

    @property
    def entlade_ziel_w(self) -> float:
        """Vom Controller zugeteilter Entladeanteil – Zuteilungsebene, nicht Sollwert."""
        return self._entlade_ziel_w

    @property
    def lade_anforderung_w(self) -> float:
        """Aktuell in HA stehender Ladeanteil des signierten Sollwerts."""
        return self._lade_anf_w

    @property
    def entlade_anforderung_w(self) -> float:
        """Aktuell in HA stehender Entladeanteil des signierten Sollwerts."""
        return self._entlade_anf_w

    @property
    def new_lade_w(self) -> float:
        return self._new_lade_w

    @property
    def new_entlade_w(self) -> float:
        return self._new_entlade_w

    @property
    def new_betriebsart(self) -> str:
        return self._new_betriebsart

    @property
    def sensoren_gueltig(self) -> bool:
        return self._soc_valid and self._power_valid

    # ------------------------------------------------------------------
    # Zyklusstart
    # ------------------------------------------------------------------

    def begin_cycle(self, now_ts: float) -> None:
        super().begin_cycle(now_ts)
        self._lade_block = self._entlade_block = self._blockiert_grund = None
        self._entlade_ziel_w = 0.0

    # ------------------------------------------------------------------
    # Pool-Semantik
    # ------------------------------------------------------------------

    @property
    def current_w(self) -> float:
        """Nur vom HEMS angeforderte LADEleistung aus PV-Überschuss.

        Bei Netzladen (v2) bewusst 0: diese Leistung stammt nicht aus dem
        PV-Überschuss und darf nicht in den Pool zurückgerechnet werden – sonst
        würden die Überschussverbraucher aus dem Netz mitgespeist.
        """
        if not self.eligible or self.netzladen_aktiv:
            return 0.0
        return min(self._lade_ist_w, self._lade_anf_w)

    @property
    def gemessene_last_w(self) -> float:
        """Gemessene LADEleistung – auch bei Netzladen, anders als current_w.

        Verhindert, dass ein Speicher, der aus dem Netz lädt, für einen ANDEREN
        Speicher wie Hausverbrauch aussieht (Kreisstrom über zwei Geräte).
        """
        return self._lade_ist_w

    @property
    def netz_support_w(self) -> float:
        """Gemessene Entladung – immer, unabhängig von eligible und Ursache."""
        return self._entlade_ist_w

    @property
    def max_relief_w(self) -> float:
        """Sofort abschaltbare Ladeleistung.

        Anders als bei einem Heizstab ist min_technisch_w hier KEINE Untergrenze
        fürs Abschalten – der Speicher kann von jedem Ladewert unverzüglich auf 0.
        """
        return self.current_w

    def select_phases(self, pool_w: float, now_ts: float) -> None:
        return  # Speicher werden immer in Watt geregelt

    # ------------------------------------------------------------------
    # HA-Zustand lesen
    # ------------------------------------------------------------------

    def update_from_ha(self, st: StateProxy, now_ts: float,
                       global_puffer_w: float) -> None:
        # Basisklasse liest Priorität, Reserve, Regelzeiten, Schrittweite und
        # Totband. min_/max_technisch_w gibt es beim Speicher nicht als Helfer –
        # sie werden unten aus den Speichergrenzen befüllt.
        super().update_from_ha(st, now_ts, global_puffer_w)
        pfx = self._entity_prefix

        def n(suffix: str, default: float = 0.0) -> float:
            return safe_float(st.get(f"input_number.ems_{pfx}_{suffix}"), default)

        def b(suffix: str) -> bool:
            return st.get(f"input_boolean.ems_{pfx}_{suffix}") == "on"

        self.entlade_priority          = int(n("entlade_prioritat", self.entlade_priority))
        self.max_ladeleistung_w        = n("max_ladeleistung_w")
        self.min_ladeleistung_w        = n("min_ladeleistung_w")
        self.max_entladeleistung_w     = n("max_entladeleistung_w")
        self.min_entladeleistung_w     = n("min_entladeleistung_w")
        self.soc_min_prozent           = n("soc_min_prozent", 10.0)
        self.soc_max_prozent           = n("soc_max_prozent", 100.0)
        self.soc_reserve_prozent       = n("soc_reserve_prozent", 0.0)
        self.soc_taper_band_prozent    = n("soc_taper_band_prozent", 5.0)
        self.soc_max_hysterese_prozent = n("soc_max_hysterese_prozent", 2.0)
        self.entlade_sofort_schwelle_w = n("entlade_sofort_schwelle_w", 300.0)
        self.umschalt_totzone_w        = n("umschalt_totzone_w", 100.0)
        self.min_umschaltzeit_s        = n("min_umschaltzeit_s", 300.0)
        self.laden_erlaubt             = b("laden_erlaubt")
        self.entladen_erlaubt          = b("entladen_erlaubt")
        self.netzladen_aktiv           = b("netzladen_aktiv")
        self.netzlade_leistung_w       = n("netzlade_leistung_w")

        betriebsart = st.get(f"input_select.ems_{pfx}_betriebsart")
        self.betriebsart = betriebsart if betriebsart in self.BETRIEBSARTEN else "standby"

        # EP-Übernahme mit der üblichen Fallback-Semantik: fällt ein Vorschlag
        # aus, greift der Nutzerwert.
        if self.source == "ep":
            self.entlade_priority      = int(self._ep_num(st, "entlade_prio", self.entlade_priority))
            self.soc_max_prozent       = self._ep_num(st, "soc_ziel_prozent", self.soc_max_prozent)
            self.soc_min_prozent       = self._ep_num(st, "soc_min_prozent", self.soc_min_prozent)
            self.max_ladeleistung_w    = self._ep_num(st, "lade_max_w", self.max_ladeleistung_w)
            self.max_entladeleistung_w = self._ep_num(st, "entlade_max_w", self.max_entladeleistung_w)
            vorschlag = self._ep_raw(st, "betriebsart")
            if vorschlag is not None and str(vorschlag) in self.BETRIEBSARTEN:
                self.betriebsart = str(vorschlag)

        # --- Messwerte ---
        soc_raw = st.get(self.soc_entity) if self.soc_entity else None
        self._soc_valid = soc_raw not in (None, "unavailable", "unknown")
        self._soc = safe_float(soc_raw, 0.0) if self._soc_valid else 0.0
        self._update_soc_latch()

        self._power_valid, self._lade_ist_w, self._entlade_ist_w = self._read_power(st)
        # Für die geerbte Pool-Rückrechnung ist der Speicher ein Verbraucher:
        # _actual_w ist die Ladeleistung, nicht die Nettoleistung.
        self._actual_w = self._lade_ist_w

        self._wr_lade_limit_w    = self._optional_limit(st, self.available_charge_power_entity)
        self._wr_entlade_limit_w = self._optional_limit(st, self.available_discharge_power_entity)

        # --- Signierten Sollwert aufteilen (D-B20) ---
        anf_signed = self._anforderung_current_w
        self._lade_anf_w    = max(anf_signed, 0.0)
        self._entlade_anf_w = max(-anf_signed, 0.0)
        self._betriebsart_anf = st.get(f"input_select.ems_{pfx}_anforderung_betriebsart")

        # --- Technische Grenzen der Basisklasse aus den Speichergrenzen füllen ---
        # Über _raw_* + _apply_raw_to_watt, damit _schutz_w konsistent neu
        # berechnet wird und die geerbte 2-Pass-Allokation unverändert greift.
        self._raw_min = self.min_ladeleistung_w
        self._raw_max = self._lade_limit_w()
        self._apply_raw_to_watt()

    def _read_power(self, st: StateProxy):
        """Normalisiert die Ist-Leistung auf (gültig, laden_w, entladen_w), beide >= 0."""
        if self.power_entity:
            raw = st.get(self.power_entity)
            if raw in (None, "unavailable", "unknown"):
                return False, 0.0, 0.0
            p = safe_float(raw, 0.0)
            if self.power_sign == "positiv_entladen":
                p = -p
            return True, max(p, 0.0), max(-p, 0.0)

        lade_raw    = st.get(self.charge_power_entity)    if self.charge_power_entity    else None
        entlade_raw = st.get(self.discharge_power_entity) if self.discharge_power_entity else None
        if (lade_raw in (None, "unavailable", "unknown")
                or entlade_raw in (None, "unavailable", "unknown")):
            return False, 0.0, 0.0
        return True, max(safe_float(lade_raw), 0.0), max(safe_float(entlade_raw), 0.0)

    @staticmethod
    def _optional_limit(st: StateProxy, entity: Optional[str]) -> Optional[float]:
        """Momentanes Geräte-Limit (Temperatur-/Zell-Derating). None = kein Limit gemeldet."""
        if not entity:
            return None
        raw = st.get(entity)
        if raw in (None, "unavailable", "unknown"):
            return None
        return max(safe_float(raw, 0.0), 0.0)

    def _update_soc_latch(self) -> None:
        """Hysterese am Ladedeckel: ab soc_max gesperrt, Freigabe erst
        soc_max_hysterese_prozent darunter. Ohne sie flippt der Speicher bei
        100 % im Takt zwischen Laden und Standby."""
        if not self._soc_valid:
            return
        if self._soc >= self.soc_max_prozent:
            self._soc_max_latch = True
        elif self._soc <= self.soc_max_prozent - self.soc_max_hysterese_prozent:
            self._soc_max_latch = False

    # ------------------------------------------------------------------
    # Grenzen
    # ------------------------------------------------------------------

    def _lade_limit_w(self) -> float:
        """Momentan zulässige Ladeleistung nach SoC-Taper und Geräte-Derating."""
        if not self.laden_erlaubt or not self._soc_valid or self._soc_max_latch:
            return 0.0
        basis = self.max_ladeleistung_w
        kopf  = self.soc_max_prozent - self._soc
        if kopf <= 0:
            return 0.0
        if self.soc_taper_band_prozent > 0 and kopf < self.soc_taper_band_prozent:
            basis *= kopf / self.soc_taper_band_prozent
        if self._wr_lade_limit_w is not None:
            basis = min(basis, self._wr_lade_limit_w)   # Derating hat Vorrang
        return max(basis, 0.0)

    def _entlade_boden_prozent(self) -> float:
        return max(self.soc_min_prozent, self.soc_reserve_prozent)

    def _entlade_limit_w(self) -> float:
        """Momentan zulässige Entladeleistung nach SoC-Taper und Geräte-Derating."""
        if not self.entladen_erlaubt or not self._soc_valid:
            return 0.0
        kopf = self._soc - self._entlade_boden_prozent()
        if kopf <= 0:
            return 0.0
        basis = self.max_entladeleistung_w
        if self.soc_taper_band_prozent > 0 and kopf < self.soc_taper_band_prozent:
            basis *= kopf / self.soc_taper_band_prozent
        if self._wr_entlade_limit_w is not None:
            basis = min(basis, self._wr_entlade_limit_w)
        return max(basis, 0.0)

    # ------------------------------------------------------------------
    # Ladeseite – die geerbte Allokation wird nur begrenzt
    # ------------------------------------------------------------------

    def _darf_laden(self) -> bool:
        """Sperrgründe des Ladepfads in der Reihenfolge, in der sie greifen.

        Der erste zutreffende Grund landet in _lade_block und wird in der
        Statusanzeige sichtbar – bei sechs Sperrmechanismen ist 'lädt gerade
        nicht' sonst nur über Debug-Logs erklärbar.
        """
        gruende = (
            (not self.eligible,                                "nicht_freigegeben"),
            (not self.sensoren_gueltig,                        "sensor_ungueltig"),
            (self.betriebsart not in ("auto", "nur_laden"),     "betriebsart"),
            (not self.laden_erlaubt,                            "laden_gesperrt"),
            (self._wr_lade_limit_w is not None
             and self._wr_lade_limit_w <= 0,                    "wr_derating"),
            (self._lade_limit_w() <= 0,                         "soc_max"),
        )
        for trifft_zu, grund in gruende:
            if trifft_zu:
                self._lade_block = grund
                return False
        self._lade_block = None
        return True

    def consume_from_pool(self, remaining_w: float, _: float) -> float:
        """Reserviert schutz_w nur, wenn der Speicher überhaupt laden darf.

        Anders als bei einem Heizstab kann der Ladepfad gerade gesperrt sein
        (Betriebsart, SoC-Deckel, Derating). Dann darf der Speicher den binären
        Geräten keine Leistung wegnehmen, die er selbst nicht abrufen kann.
        """
        return super().consume_from_pool(remaining_w, _) if self._darf_laden() else remaining_w

    def allocate_minimum(self, remaining_w: float) -> float:
        if not self._darf_laden():
            self._alloc_w = 0.0
            return remaining_w
        return super().allocate_minimum(remaining_w)

    def allocate_surplus(self, remaining_w: float) -> float:
        return super().allocate_surplus(remaining_w) if self._darf_laden() else remaining_w

    # ------------------------------------------------------------------
    # Entladeseite – Ziel kommt vom Controller (D-B15)
    # ------------------------------------------------------------------

    def entlade_kapazitaet_w(self) -> float:
        """Wieviel dieser Speicher JETZT beisteuern könnte – Basis der Aufteilung."""
        gruende = (
            (not self.eligible,                                 "nicht_freigegeben"),
            (not self.sensoren_gueltig,                         "sensor_ungueltig"),
            (self.betriebsart not in ("auto", "nur_entladen"),   "betriebsart"),
            (not self.entladen_erlaubt,                          "entladen_gesperrt"),
            (self.netzladen_aktiv,                               "netzladen"),
            (self._soc <= self._entlade_boden_prozent(),
             "soc_reserve" if self.soc_reserve_prozent > self.soc_min_prozent else "soc_min"),
        )
        for trifft_zu, grund in gruende:
            if trifft_zu:
                self._entlade_block = grund
                return 0.0
        limit = self._entlade_limit_w()
        if limit <= 0:
            self._entlade_block = "wr_derating"
            return 0.0
        self._entlade_block = None
        return limit

    def set_discharge_target(self, w: float) -> None:
        """Wird von EMSController._allocate_discharge aufgerufen."""
        self._entlade_ziel_w = max(0.0, min(w, self.entlade_kapazitaet_w()))

    # ------------------------------------------------------------------
    # Richtungsauflösung und Rampen
    # ------------------------------------------------------------------

    def _sicherer_zustand(self) -> str:
        """Zustand bei EMS-Ausfall, Lockout oder fehlender Freigabe.

        Immer standby: es gibt keine autonome Rueckfallregelung, auf die man
        umschalten koennte. Entscheidend ist deshalb, dass get_write_ops diesen
        Zustand AKTIV schreibt - 'nichts tun' liesse den letzten Sollwert stehen
        und der Speicher entlaedt bis leer weiter.
        """
        return "standby"

    def _aktuelle_richtung(self) -> int:
        if self._lade_anf_w > EPS_W:
            return 1
        if self._entlade_anf_w > EPS_W:
            return -1
        return 0

    @staticmethod
    def _raste(w: float, min_w: float) -> float:
        """Unterhalb der technischen Untergrenze gibt es nur 0 – nie überschießen."""
        return 0.0 if w < max(min_w, EPS_W) else float(round(w))

    def _ramp_laden(self, ziel_w: float, current_deficit_w: float) -> float:
        aktuell = self._lade_anf_w
        age_s   = self._anforderung_age_s
        if ziel_w > aktuell:
            if age_s < self.hoch_regelzeit_s:
                return aktuell
            return min(ziel_w, aktuell + self.max_anderung_pro_schritt_w)
        if ziel_w < aktuell:
            if current_deficit_w > 0:
                return ziel_w          # bei Defizit sofort abregeln, wie jeder Verbraucher
            if age_s < self.runter_regelzeit_s:
                return aktuell
            return max(ziel_w, aktuell - self.max_anderung_pro_schritt_w)
        return aktuell

    def _ramp_entladen(self, ziel_w: float) -> float:
        """RUNTER schnell bei echtem Lastabwurf, gedämpft bei kleinen Abweichungen.

        Grosse Absenkungen sind reale Lastabwuerfe (Backofen aus) -> sofort,
        sonst exportieren wir Batteriestrom (H-5).
        Kleine Absenkungen sind meist Sensor-Versatz oder Rauschen -> daempfen,
        sonst entsteht daraus ein Grenzzyklus (H-7).
        """
        delta = self._entlade_anf_w - ziel_w                  # > 0 = runter
        if delta > self.entlade_sofort_schwelle_w:
            return ziel_w
        if delta > 0:
            return max(ziel_w, self._entlade_anf_w - self.max_anderung_pro_schritt_w)
        if self._anforderung_age_s < self.hoch_regelzeit_s:
            return self._entlade_anf_w
        return min(ziel_w, self._entlade_anf_w + self.max_anderung_pro_schritt_w)

    def calculate_ramp(self, current_deficit_w: float = 0.0) -> None:
        """Löst die Richtung auf, wendet Totzone und Umschaltsperre an, rampt.

        Wird vom Controller für ALLE Geräte aufgerufen – die Entladeplanung muss
        also vorher gelaufen sein (D-B07).
        """
        umschaltsperre = totzone = False

        if not self.eligible or not self.sensoren_gueltig or self.betriebsart == "standby":
            self._new_lade_w = self._new_entlade_w = 0.0
            self._new_betriebsart = self._sicherer_zustand()
            self._blockiert_grund = None
            return

        lade_wunsch    = self._alloc_w if self._darf_laden() else 0.0
        entlade_wunsch = self._entlade_ziel_w

        # D-B10: aus der PV-Logik heraus wird bei Hausdefizit nie geladen.
        # Die Klemme ist die Absicherung gegen Rechenfehler an anderer Stelle.
        if entlade_wunsch > 0 and not self.netzladen_aktiv:
            if lade_wunsch > 0:
                self._lade_block = "hausdefizit"
            lade_wunsch = 0.0
        # D-B16: Netzladen schlägt Entladen, sonst Kreisstrom mit Round-Trip-Verlust
        if self.netzladen_aktiv:
            entlade_wunsch = 0.0
            lade_wunsch    = self.netzlade_leistung_w

        netto = lade_wunsch - entlade_wunsch                  # + laden / - entladen

        if netto != 0.0 and abs(netto) < self.umschalt_totzone_w:
            netto, totzone = 0.0, True

        # Umschaltsperre: in der Sperrzeit wird STANDBY gefahren, nicht die alte
        # Richtung fortgesetzt – sonst entlädt der Speicher in den PV-Überschuss.
        richtung_neu = 0 if netto == 0 else (1 if netto > 0 else -1)
        richtung_alt = self._aktuelle_richtung()
        if (richtung_neu and richtung_alt and richtung_neu != richtung_alt
                and self._now_ts - self._last_direction_change_ts < self.min_umschaltzeit_s):
            netto, richtung_neu, umschaltsperre = 0.0, 0, True
        if richtung_neu and richtung_neu != richtung_alt:
            self._last_direction_change_ts = self._now_ts

        if netto > 0:
            self._new_lade_w    = self._ramp_laden(netto, current_deficit_w)
            self._new_entlade_w = 0.0
        elif netto < 0:
            self._new_lade_w    = 0.0
            self._new_entlade_w = self._ramp_entladen(-netto)
        else:
            self._new_lade_w = self._new_entlade_w = 0.0

        self._new_lade_w    = self._raste(self._new_lade_w,    self.min_ladeleistung_w)
        self._new_entlade_w = self._raste(self._new_entlade_w, self.min_entladeleistung_w)

        if self._new_lade_w > 0:
            self._new_betriebsart = "laden"
        elif self._new_entlade_w > 0:
            self._new_betriebsart = "entladen"
        else:
            self._new_betriebsart = "standby"

        self._blockiert_grund = ("umschaltsperre" if umschaltsperre
                                 else "totzone" if totzone else None)

    # ------------------------------------------------------------------
    # Ausgabe
    # ------------------------------------------------------------------

    def get_write_ops(self) -> List[Tuple[str, str, Dict]]:
        """Schreibt signierten Sollwert und Betriebsart (D-B11/D-B20).

        Reihenfolge: beim Einschalten und Ändern erst die Betriebsart, dann die
        Leistung; beim Abschalten umgekehrt – ein Modussprung bei stehender
        Leistung kann am Gerät einen Stromstoss erzeugen.

        Der sichere Zustand wird AKTIV geschrieben, nicht ausgelassen. 'Nichts
        tun' liesse den letzten Sollwert in HA stehen.
        """
        betriebsart_entity = f"input_select.ems_{self._entity_prefix}_anforderung_betriebsart"

        neu_signed = int(round(self._new_lade_w - self._new_entlade_w))
        alt_signed = int(round(self._lade_anf_w - self._entlade_anf_w))
        delta      = abs(neu_signed - alt_signed)

        # Totband wie bei ControllableDevice: würde jeden Zyklus derselbe Wert
        # geschrieben, setzte das last_changed zurück und die Rampen-Alterung
        # wäre kaputt. Zwei Ausnahmen, in denen Geschwindigkeit vorgeht:
        # Vorzeichenwechsel und das Zurücknehmen einer laufenden Entladung.
        vorzeichenwechsel  = (neu_signed > 0) != (alt_signed > 0) or (neu_signed < 0) != (alt_signed < 0)
        entladung_zurueck  = alt_signed < 0 and neu_signed > alt_signed
        schreibt_leistung  = delta > 0 and (
            vorzeichenwechsel or entladung_zurueck
            or self.deadband_w <= 0 or delta >= self.deadband_w
        )
        schreibt_betriebsart = self._new_betriebsart != self._betriebsart_anf

        if not schreibt_leistung:
            # Totband aktiv – die Anzeige soll zeigen, was wirklich in HA steht.
            self._new_lade_w    = self._lade_anf_w
            self._new_entlade_w = self._entlade_anf_w
            neu_signed          = alt_signed

        leistung_op = ("input_number", "set_value", {
            "entity_id": self.entity_anforderung_w,
            "value":     float(neu_signed),
        })
        betriebsart_op = ("input_select", "select_option", {
            "entity_id": betriebsart_entity,
            "option":    self._new_betriebsart,
        })

        ops: List[Tuple[str, str, Dict]] = []
        if self._new_betriebsart == "standby":
            if schreibt_leistung:
                ops.append(leistung_op)
            if schreibt_betriebsart:
                ops.append(betriebsart_op)
        else:
            if schreibt_betriebsart:
                ops.append(betriebsart_op)
            if schreibt_leistung:
                ops.append(leistung_op)
        return ops

    # ------------------------------------------------------------------
    # Statusanzeige
    # ------------------------------------------------------------------

    def to_status_dict(self) -> Dict:
        rest_s = 0.0
        if self._last_direction_change_ts > 0:
            rest_s = max(0.0, round(
                self.min_umschaltzeit_s - (self._now_ts - self._last_direction_change_ts)
            ))
        d: Dict = {
            "type":                  "battery",
            "id":                    self.id,
            "label":                 self.label,
            "priority":              self.priority,
            "entlade_prioritat":     self.entlade_priority,
            "eligible":              self.eligible,
            "source":                self.source,
            "ep_proposal_status":    self._ep_proposal_status,
            "sensoren_gueltig":      self.sensoren_gueltig,
            "soc_prozent":           round(self._soc, 1),
            "capacity_kwh":          self.capacity_kwh,
            "betriebsart":           self.betriebsart,
            "betriebsart_effektiv":  self._new_betriebsart,
            "lade_ist_w":            self._lade_ist_w,
            "entlade_ist_w":         self._entlade_ist_w,
            "lade_anforderung_w":    self._lade_anf_w,
            "entlade_anforderung_w": self._entlade_anf_w,
            "new_lade_w":            self._new_lade_w,
            "new_entlade_w":         self._new_entlade_w,
            "netto_w":               self._new_lade_w - self._new_entlade_w,
            # Roh und effektiv getrennt: der Nutzerwert und die Grenze nach
            # SoC-Taper und Geräte-Derating sind zwei verschiedene Grössen.
            "max_ladeleistung_w":    self.max_ladeleistung_w,
            "max_entladeleistung_w": self.max_entladeleistung_w,
            "lade_limit_w":          self._lade_limit_w(),
            "entlade_limit_w":       self._entlade_limit_w(),
            "hausdefizit_anteil_w":  self._entlade_ziel_w,
            "schutz_w":              self._schutz_w,
            "geschuetzte_mindestleistung_w": self.geschuetzte_mindestleistung_w,
            "laden_erlaubt":         self.laden_erlaubt,
            "entladen_erlaubt":      self.entladen_erlaubt,
            "netzladen_aktiv":       self.netzladen_aktiv,
            "soc_min_prozent":       self.soc_min_prozent,
            "soc_max_prozent":       self.soc_max_prozent,
            "soc_reserve_prozent":   self.soc_reserve_prozent,
            "umschaltsperre_rest_s": rest_s,
            "lade_blockiert_grund":    self._lade_block,
            "entlade_blockiert_grund": self._entlade_block,
            "blockiert_grund":         self._blockiert_grund,
        }
        if self.capacity_kwh > 0:
            d["energie_kwh"] = round(self.capacity_kwh * self._soc / 100.0, 2)
        return d
