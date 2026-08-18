"""
EMSController – orchestriert den vollständigen Regelzyklus.

Geräte werden EINMAL beim Start erzeugt und bleiben über alle Zyklen hinweg
bestehen, damit interner Zustand (z. B. BinaryDevice._off_since_ts) zwischen
Aufrufen erhalten bleibt, ohne HA-Helfer-Entitäten zu benötigen.
"""

import datetime
import logging
import time
from typing import Dict, List, Optional

from .state import StateProxy, safe_float
from .devices import Device, ControllableDevice, BinaryDevice

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Globale HA-Entitätsnamen
# ---------------------------------------------------------------------------

HA_EMS_ENABLED               = "input_boolean.ems_pv_regelung_aktiv"
HA_GLOBAL_MODE               = "input_select.ems_regelmodus"
HA_GLOBAL_PUFFER_W           = "input_number.ems_globaler_puffer_w"
HA_GLOBAL_EINSCHALTRESERVE_W = "input_number.ems_einschaltreserve_global_w"
HA_DEBUG_OUTPUT              = "input_boolean.ems_pyems_debug_output"

# Standard-Entität für den verfügbaren PV-Überschuss. Über die Add-on-Option
# `residual_power_entity` überschreibbar. Home Assistant slugifiziert Umlaute
# (ü→u, ö→o, ä→a, ß→ss), daher dieser ASCII-Name.
DEFAULT_RESIDUAL_ENTITY = "sensor.verfugbare_leistung_fur_uberschussverbraucher"

HARD_LOCKOUT_THRESHOLD_W = -50000.0


# ---------------------------------------------------------------------------
# Geräte-Registry – beim Start aus der Add-on-Konfiguration aufgebaut
# ---------------------------------------------------------------------------

def _build_devices(device_configs: List[dict]) -> List[Device]:
    """Baut die Geräteliste aus den config.yaml-Einträgen options.devices auf."""
    devices = []
    for cfg in device_configs:
        name = (cfg.get("name") or "").strip()
        cls  = (cfg.get("class") or "").strip()
        if not name:
            log.error("Gerätekonfiguration ohne 'name' übersprungen: %s", cfg)
            continue

        prefix = (cfg.get("entity_prefix") or "").strip() or name
        label  = (cfg.get("label")         or "").strip() or None
        # allowed_modes = Gerätetyp-Gate für Quelle 'user' (normale Regeln).
        # "auto" ist kein User-Gate mehr (auto = KI-Übernahme für alle Geräte) ->
        # Alt-Konfigurationen mit "auto" auf "manuell" abbilden (Rückwärtskompat).
        modes  = [("manuell" if m.strip() == "auto" else m.strip())
                  for m in (cfg.get("allowed_modes") or "manuell").split(",") if m.strip()]

        try:
            if cls == "controllable":
                actual_w = (cfg.get("actual_power_entity") or "").strip()
                if not actual_w:
                    raise ValueError("actual_power_entity ist leer")
                output_unit          = (cfg.get("output_unit") or "watt").strip()
                phases_raw           = (cfg.get("phases") or "1").strip()
                allowed_phases       = [int(p) for p in phases_raw.split(",")
                                        if p.strip() in ("1", "3")]
                if not allowed_phases:
                    allowed_phases = [1]
                phase_switch_delay_s = float(cfg.get("phase_switch_delay_s") or 300)
                def _ve(key: str) -> Optional[str]:
                    return (cfg.get(key) or "").strip() or None
                anf_suf              = 'a' if output_unit == 'ampere' else 'w'
                devices.append(ControllableDevice(
                    id=name,
                    allowed_modes=modes,
                    entity_actual_w=actual_w,
                    entity_anforderung_w=f"input_number.ems_{prefix}_anforderung_leistung_{anf_suf}",
                    entity_prefix=prefix,
                    label=label,
                    output_unit=output_unit,
                    allowed_phases=allowed_phases,
                    voltage_l1_entity=_ve("voltage_l1_entity"),
                    voltage_l2_entity=_ve("voltage_l2_entity"),
                    voltage_l3_entity=_ve("voltage_l3_entity"),
                    phase_switch_delay_s=phase_switch_delay_s,
                ))

            elif cls == "binary":
                switch = (cfg.get("switch_entity") or "").strip()
                if not switch:
                    raise ValueError("switch_entity ist leer")
                devices.append(BinaryDevice(
                    id=name,
                    allowed_modes=modes,
                    entity_switch=switch,
                    entity_anforderung_an=f"input_boolean.ems_{prefix}_anforderung_an",
                    entity_prefix=prefix,
                    label=label,
                ))

            else:
                raise ValueError(f"Unbekannte Klasse '{cls}' (erlaubt: controllable, binary)")

            log.info("Gerät registriert: '%s' (%s, prefix='%s', modi=%s)",
                     name, cls, prefix, modes)

        except Exception as exc:
            log.error("Gerät '%s' konnte nicht registriert werden: %s", name, exc)

    return devices


# ---------------------------------------------------------------------------
# EMSController
# ---------------------------------------------------------------------------

class EMSController:
    """
    Zustandsbehafteter EMS-Controller. Wird einmal in HEMSApp instanziiert;
    Geräteobjekte und ihr interner Zustand bleiben über alle Zyklen erhalten.
    """

    def __init__(self, device_configs: List[dict],
                 residual_power_entity: Optional[str] = None):
        self._devices: List[Device] = _build_devices(device_configs)
        self._residual_entity = (residual_power_entity or "").strip() or DEFAULT_RESIDUAL_ENTITY
        log.info("EMSController bereit – %d Geräte registriert, Überschuss-Sensor='%s'.",
                 len(self._devices), self._residual_entity)

    @property
    def residual_power_entity(self) -> str:
        """Öffentliche, aufgelöste Entität des Überschusssensors für den API-Vertrag."""
        return self._residual_entity

    # ------------------------------------------------------------------
    # Öffentlicher Einstiegspunkt
    # ------------------------------------------------------------------

    def run_cycle(self, st: StateProxy) -> Dict:
        """
        Führt einen Regelzyklus aus.

        Returns:
            {
                "status":    { ... },              # Web-UI-Snapshot
                "write_ops": [(domain, svc, data)] # auszuführende HA-Service-Aufrufe
            }
        """
        # Einheitliche Zeitquelle für den gesamten Zyklus: time.time() (Wanduhr-Epoch),
        # konsistent mit parse_ts() der HA-last_changed-Zeitstempel.
        now_ts = time.time()
        now_dt = datetime.datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d %H:%M:%S")

        # ── 1. Globale Eingänge ─────────────────────────────────────────
        debug_output            = st.get(HA_DEBUG_OUTPUT) == "on"
        ems_enabled             = st.get(HA_EMS_ENABLED) == "on"
        global_mode             = st.get(HA_GLOBAL_MODE) or "aus"
        global_puffer           = safe_float(st.get(HA_GLOBAL_PUFFER_W))
        global_einschaltreserve = safe_float(st.get(HA_GLOBAL_EINSCHALTRESERVE_W))

        residual_raw          = st.get(self._residual_entity)
        residual_sensor_valid = residual_raw not in ("unavailable", "unknown", None)
        residual_w            = safe_float(residual_raw) if residual_sensor_valid else 0.0
        hard_lockout          = (not residual_sensor_valid
                                 or residual_w <= HARD_LOCKOUT_THRESHOLD_W)

        if not residual_sensor_valid:
            log.error("EMS SENSOR LOCKOUT: %s ist '%s' – alle Verbraucher abschalten",
                      self._residual_entity, residual_raw)
        elif hard_lockout and debug_output:
            log.warning("EMS LOCKOUT: residual=%.0fW <= %.0fW",
                        residual_w, HARD_LOCKOUT_THRESHOLD_W)

        # ── 2. Alle Geräte aus HA aktualisieren ─────────────────────────
        for device in self._devices:
            device.begin_cycle(now_ts)
            device.source   = device.resolve_source(
                st, ems_enabled, global_mode, hard_lockout
            )
            device.eligible = device.check_eligible(st)
            device.update_from_ha(st, now_ts, global_puffer)

        # ── 3. Pool ─────────────────────────────────────────────────────
        pool_w = self._calc_pool(residual_w, ems_enabled, global_mode, hard_lockout)

        # ── 4. Defizit ──────────────────────────────────────────────────
        current_deficit_w    = max(-residual_w, 0.0)
        total_relief_w       = sum(d.max_relief_w for d in self._devices)
        binary_immediate_off = current_deficit_w > total_relief_w

        if current_deficit_w > 0 and debug_output:
            log.warning("EMS DEFIZIT: %.0fW  sofort_aus=%s",
                        current_deficit_w, binary_immediate_off)

        # ── 5. Binärer Wunschzustand (Pool in Prioritätsreihenfolge verbraucht) ──
        remaining_w = pool_w
        for device in sorted(self._devices, key=lambda d: d.priority):
            remaining_w = device.consume_from_pool(remaining_w, global_einschaltreserve)

        # ── 6. Binärer Kandidat (Zeit-Guards, off_delay) ────────────────
        binary_devices = [d for d in self._devices if isinstance(d, BinaryDevice)]
        for device in binary_devices:
            device.calculate_candidate(now_ts)

        # ── 7. Kandidat → final kopieren, dann Kaskade + One-Change anwenden ──
        for device in binary_devices:
            device.final_on = device.candidate_on

        self._apply_priority_cascade(binary_devices)
        self._limit_one_change(binary_devices, binary_immediate_off)

        # off_delay-Timer für final als AUS bestimmte Geräte zurücksetzen
        for device in binary_devices:
            if not device.final_on:
                device.reset_off_timer()

        # ── 8. Regelbare Geräte zuteilen (2 Durchläufe: Minimum zuerst) ──
        # Regel: 1. Prioritätsreihenfolge  2. Jedes Gerät erhält sein min_technisch_w,
        #           bevor ein niedriger-priores Gerät aktiviert wird.
        #        3. Der Überschuss geht dann zuerst an das höchst-priore Gerät.
        binary_total_w = sum(d.power_w for d in binary_devices if d.final_on)
        remaining_w    = max(pool_w - binary_total_w, 0.0)
        sorted_ctrl    = [d for d in sorted(self._devices, key=lambda d: d.priority)
                          if isinstance(d, ControllableDevice)]

        # Phasenwahl + Durchlauf 1: technisches Minimum je Gerät garantieren
        for device in sorted_ctrl:
            device.select_phases(remaining_w, now_ts)
            remaining_w = device.allocate_minimum(remaining_w)

        # Durchlauf 2: Überschuss in Prioritätsreihenfolge bis max verteilen
        for device in sorted_ctrl:
            remaining_w = device.allocate_surplus(remaining_w)

        # ── 9. Rampenbegrenzung ─────────────────────────────────────────
        for device in self._devices:
            device.calculate_ramp(current_deficit_w)

        # ── 10. Debug-Logging ───────────────────────────────────────────
        if debug_output:
            self._log_cycle(binary_devices, pool_w, binary_immediate_off, now_ts)

        # ── 11. HA-Schreiboperationen sammeln ───────────────────────────
        write_ops = [op for d in self._devices for op in d.get_write_ops()]

        # ── 12. Status-Snapshot für die Web-UI aufbauen ─────────────────
        status = {
            "ems_enabled":           ems_enabled,
            "global_mode":           global_mode,
            "hard_lockout":          hard_lockout,
            "residual_sensor_valid": residual_sensor_valid,
            "residual_w":            residual_w,
            "pool_w":                pool_w,
            "current_deficit_w":     current_deficit_w,
            "binary_immediate_off":  binary_immediate_off,
            "binary_total_w":        binary_total_w,
            "devices":               [d.to_status_dict() for d in self._devices],
            "timestamp":             now_dt,
        }

        return {"status": status, "write_ops": write_ops}

    # ------------------------------------------------------------------
    # Pool
    # ------------------------------------------------------------------

    def _calc_pool(self, residual_w: float, ems_enabled: bool,
                   global_mode: str, hard_lockout: bool) -> float:
        if not ems_enabled or global_mode == "aus" or hard_lockout:
            return 0.0
        actual_used_w = sum(d.current_w for d in self._devices)
        return max(residual_w + actual_used_w, 0.0)

    # ------------------------------------------------------------------
    # Prioritätskaskade
    # ------------------------------------------------------------------

    def _apply_priority_cascade(self, binary_devices: List[BinaryDevice]) -> None:
        sorted_b = sorted(binary_devices, key=lambda d: d.priority)

        # NB: Eine prioritätsbasierte Demotion (niedriger-priore Geräte sofort
        # abschalten, sobald ein höher-priores Gerät abschalten will) gibt es
        # bewusst NICHT mehr. Sie hätte ein niedriger-priores Gerät nur dann
        # zwangsweise ausgeschaltet, wenn es sich noch in seiner
        # Abschaltverzögerung befindet – und genau die soll IMMER gelten.
        # Das Abschalt-Timing wird daher ausschließlich von den Geräte-Guards
        # (Mindestlaufzeit + Abschaltverzögerung) in calculate_candidate
        # bestimmt.

        # Promotion: höher-priore Geräte dürfen nicht aus sein, während niedriger-priore an sind
        for i, high in enumerate(sorted_b):
            for low in sorted_b[i + 1:]:
                if low.final_on:
                    if high.eligible and (high.actual_on or high.candidate_on):
                        high.final_on = True
                        high.reset_off_timer()

    # ------------------------------------------------------------------
    # One-Change-Limit
    # ------------------------------------------------------------------

    def _limit_one_change(self, binary_devices: List[BinaryDevice],
                          binary_immediate_off: bool) -> None:
        if binary_immediate_off:
            return

        turn_offs = [d for d in binary_devices if d.actual_on  and not d.final_on]
        turn_ons  = [d for d in binary_devices if not d.actual_on and d.final_on]

        if len(turn_offs) + len(turn_ons) <= 1:
            return

        if turn_offs:
            # Unwichtigstes (höchste Prioritätszahl) schaltet zuerst ab
            for d in sorted(turn_offs, key=lambda d: d.priority, reverse=True)[1:]:
                d.final_on = True
            for d in turn_ons:
                d.final_on = False
        else:
            # Nur Einschaltungen: höchste Priorität (niedrigste Zahl) gewinnt
            for d in sorted(turn_ons, key=lambda d: d.priority)[1:]:
                d.final_on = False

    # ------------------------------------------------------------------
    # Debug-Logging
    # ------------------------------------------------------------------

    def _log_cycle(self, binary_devices: List[BinaryDevice],
                   pool_w: float, binary_immediate_off: bool, now_ts: float) -> None:
        for d in binary_devices:
            if d.actual_on != d.final_on:
                direction = "AUS→AN" if d.final_on else "AN→AUS"
                reason    = ("Notabschaltung" if binary_immediate_off and not d.final_on
                             else "desired" + ("=JA" if d.final_on else "=NEIN"))
                log.info("EMS [%s] %s  prio=%d  pool=%.0fW  %s",
                         d.id, direction, d.priority, pool_w, reason)
            elif d.actual_on and d.final_on and not d.desired_on:
                if d.in_min_runtime:
                    log.info("EMS [%s] BLEIBT AN  min_runtime schützt", d.id)
                elif d.candidate_on and d._off_since_ts > 0:
                    elapsed = now_ts - d._off_since_ts
                    log.info("EMS [%s] BLEIBT AN  off_delay läuft (%.0fs)", d.id, elapsed)

        for d in self._devices:
            if isinstance(d, ControllableDevice):
                if int(d.new_w) != int(d.anforderung_current_w):
                    log.info("EMS [%s] %.0fW→%.0fW  prio=%d  alloc=%.0fW  pool=%.0fW",
                             d.id, d.anforderung_current_w, d.new_w,
                             d.priority, d.alloc_w, pool_w)
