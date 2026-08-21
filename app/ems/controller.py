"""
EMSController – orchestriert den vollständigen Regelzyklus.

Geräte werden EINMAL beim Start erzeugt und bleiben über alle Zyklen hinweg
bestehen, damit interner Zustand (z. B. BinaryDevice._off_since_ts) zwischen
Aufrufen erhalten bleibt, ohne HA-Helfer-Entitäten zu benötigen.
"""

import datetime
import logging
import time
from dataclasses import asdict
from typing import Dict, List, Optional

from configuration import (
    DEFAULT_RESIDUAL_ENTITY,
    NORMAL_MODES,
    SPECIAL_MODES,
    parse_modes,
    serialize_modes,
    validate_options,
)

from .ops import WriteOp, WriteResult
from .state import StateProxy, safe_float
from .devices import Device, ControllableDevice, BinaryDevice, BatteryDevice

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Globale HA-Entitätsnamen
# ---------------------------------------------------------------------------

HA_EMS_ENABLED               = "input_boolean.ems_pv_regelung_aktiv"
HA_GLOBAL_MODE               = "input_select.ems_regelmodus"
HA_GLOBAL_PUFFER_W           = "input_number.ems_globaler_puffer_w"
HA_GLOBAL_EINSCHALTRESERVE_W = "input_number.ems_einschaltreserve_global_w"
HA_DEBUG_OUTPUT              = "input_boolean.ems_pyems_debug_output"
# Der Entlade-Abschlag ist eine SYSTEMgrösse und wird genau einmal auf das
# Hausdefizit angewandt – je Speicher wäre er bei n Speichern n-fach wirksam.
# Namensraum ems_ac_speicher_*, weil ems_speicher_* der bestehenden
# E3DC-Regelung in Home Assistant gehört.
HA_AC_SPEICHER_ENTLADE_ABSCHLAG_W = "input_number.ems_ac_speicher_entlade_abschlag_w"

# Standard-Entität für den verfügbaren PV-Überschuss (aus configuration.py
# re-exportiert, damit Bestandskonsumenten sie weiter hier finden).

HARD_LOCKOUT_THRESHOLD_W = -50000.0


# ---------------------------------------------------------------------------
# Geräte-Registry – beim Start aus der Add-on-Konfiguration aufgebaut
# ---------------------------------------------------------------------------

def _build_devices(device_configs: List[dict]) -> List[Device]:
    """Instanziiert BEREITS VALIDIERTE Geräteeinträge.

    Prüfen und Bauen sind getrennt: was hier ankommt, ist gültig – das hat
    configuration.validate_options() entschieden. Ungültige Einträge sind dort
    schon als inactive_devices ausgesondert worden und tauchen mit ihren
    Feldfehlern im Status auf, statt in einer Log-Zeile zu verschwinden.
    """
    devices: List[Device] = []
    for cfg in device_configs:
        name   = cfg["name"]
        cls    = cfg["class"]
        prefix = cfg["entity_prefix"]
        label  = cfg["label"] or None
        modes  = parse_modes(cfg["allowed_modes"])

        if cls == "controllable":
            output_unit = cfg["output_unit"]
            suffix      = "a" if output_unit == "ampere" else "w"
            devices.append(ControllableDevice(
                id=name,
                allowed_modes=modes,
                entity_actual_w=cfg["actual_power_entity"],
                entity_anforderung_w=f"input_number.ems_{prefix}_anforderung_leistung_{suffix}",
                entity_prefix=prefix,
                label=label,
                output_unit=output_unit,
                allowed_phases=[int(value) for value in cfg["phases"].split(",")],
                voltage_l1_entity=cfg["voltage_l1_entity"] or None,
                voltage_l2_entity=cfg["voltage_l2_entity"] or None,
                voltage_l3_entity=cfg["voltage_l3_entity"] or None,
                phase_switch_delay_s=cfg["phase_switch_delay_s"],
                technical_minimum=cfg["technical_minimum"],
                technical_maximum=cfg["technical_maximum"],
                increase_delay_s=cfg["increase_delay_s"],
                decrease_delay_s=cfg["decrease_delay_s"],
                maximum_step_change=cfg["maximum_step_change"],
                minimum_step_change=cfg["minimum_step_change"],
            ))

        elif cls == "binary":
            devices.append(BinaryDevice(
                id=name,
                allowed_modes=modes,
                entity_switch=cfg["switch_entity"],
                entity_anforderung_an=f"input_boolean.ems_{prefix}_anforderung_an",
                entity_prefix=prefix,
                label=label,
                power_w=cfg["power_w"],
                on_reserve_w=cfg["on_reserve_w"],
                min_runtime_s=cfg["min_runtime_s"],
                min_offtime_s=cfg["min_offtime_s"],
                off_delay_s=cfg["off_delay_s"],
            ))

        else:
            devices.append(BatteryDevice(
                id=name,
                allowed_modes=modes,
                soc_entity=cfg["soc_entity"],
                charge_power_entity=cfg["charge_power_entity"] or None,
                discharge_power_entity=cfg["discharge_power_entity"] or None,
                power_entity=cfg["power_entity"] or None,
                power_sign=cfg["power_sign"],
                available_charge_power_w=cfg["available_charge_power_w"],
                available_discharge_power_w=cfg["available_discharge_power_w"],
                capacity_kwh=cfg["capacity_kwh"],
                soc_max_hysteresis_percent=cfg["soc_max_hysteresis_percent"],
                direction_switch_delay_s=cfg["direction_switch_delay_s"],
                entity_prefix=prefix,
                label=label,
            ))

        log.info("Gerät registriert: '%s' (%s, prefix='%s', modi=%s)",
                 name, cls, prefix, modes or ["nur Energy Pilot"])

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
                 residual_power_entity: Optional[str] = None,
                 speicher_in_residual_enthalten: bool = True,
                 available_modes: Optional[object] = None):
        # Die globalen Felder prüft der Aufrufer; hier interessiert nur, welche
        # Geräteeinträge instanziierbar sind und welche normalen Regelmodi gelten.
        self._available_modes: List[str] = (
            list(NORMAL_MODES) if available_modes is None
            else parse_modes(available_modes if isinstance(available_modes, str)
                             else ",".join(available_modes))
        )
        validated = validate_options({
            "devices": device_configs,
            "available_modes": serialize_modes(self._available_modes),
        })
        self._device_configs: List[Dict] = validated.devices
        self._devices: List[Device] = _build_devices(validated.devices)
        self._inactive_devices: List[Dict] = [asdict(issue)
                                              for issue in validated.inactive_devices]
        for issue in validated.inactive_devices:
            log.error("Gerät '%s' (%s) ist inaktiv: %s",
                      issue.name or f"Position {issue.index + 1}", issue.device_class or "?",
                      "; ".join(f"{key}: {text}" for key, text in issue.errors.items()))
        # Ein global nicht aktivierter Regelmodus wird gemeldet, sobald er sich
        # ändert – jeden Zyklus zu warnen macht das Log unlesbar.
        self._last_unconfigured_mode: Optional[str] = None
        # Letzter Schreibfehler je Geräte-ID. Er stammt aus dem VORHERIGEN
        # Zyklus und gilt genau einen Zyklus: das Gerät fährt dann seinen
        # sicheren Zustand. Klappt das, ist es im Zyklus darauf wieder aktiv.
        self._write_failures: Dict[str, str] = {}
        self._residual_entity = (residual_power_entity or "").strip() or DEFAULT_RESIDUAL_ENTITY
        # Ist die Speicherleistung im Überschuss-Sensor enthalten (Messpunkt an
        # der Netzübergabe, Normalfall bei AC-Kopplung), muss sie herausgerechnet
        # werden – sonst liest das EMS die eigene Entladung als PV-Überschuss.
        self._speicher_in_residual = bool(speicher_in_residual_enthalten)
        log.info("EMSController bereit – %d Geräte registriert, Überschuss-Sensor='%s', "
                 "Speicher im Überschuss-Sensor=%s.",
                 len(self._devices), self._residual_entity, self._speicher_in_residual)

    def report_write_results(self, results: List[WriteResult]) -> None:
        """Ordnet fehlgeschlagene Schreiboperationen ihrem Gerät zu (behebt B-2).

        Bisher wurden sie nur geloggt, der Zyklus galt als erfolgreich und in
        der Oberfläche war nichts zu sehen. Die Karte wird bei jedem Zyklus neu
        aufgebaut: ein Gerät, das nichts geschrieben hat oder dessen Schreiben
        durchging, steht danach nicht mehr darin.
        """
        self._write_failures = {
            result.op.owner: result.error
            for result in results
            if result.op.owner and not result.ok
        }
        for device_id, error in self._write_failures.items():
            log.error("Gerät '%s': Schreiben fehlgeschlagen (%s) – nur sicherer "
                      "Zustand bis das Ziel wieder funktioniert.", device_id, error)

    @property
    def device_configs(self) -> List[Dict]:
        """Die validierten Konfigurationen der tatsächlich registrierten Geräte."""
        return self._device_configs

    @property
    def inactive_devices(self) -> List[Dict]:
        """Beim Start übersprungene Geräteeinträge samt Feldfehlern."""
        return self._inactive_devices

    @property
    def available_modes(self) -> List[str]:
        return list(self._available_modes)

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

        # Hinter einem normalen Modus, der global nicht aktiviert ist, steht keine
        # Regellogik – dieser Zyklus ist deshalb sicher inaktiv. Der rohe HA-State
        # bleibt im Status sichtbar; die Optionen des Helfers legt oder ändert das
        # Add-on nicht.
        global_mode_configured = (global_mode in SPECIAL_MODES
                                  or global_mode in self._available_modes)
        if not global_mode_configured and global_mode != self._last_unconfigured_mode:
            log.warning("EMS: Regelmodus '%s' ist nicht konfiguriert (aktiviert: %s) – "
                        "Zyklus bleibt sicher inaktiv.",
                        global_mode, ", ".join(self._available_modes) or "keiner")
        self._last_unconfigured_mode = None if global_mode_configured else global_mode
        effective_mode = global_mode if global_mode_configured else "aus"
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
                st, ems_enabled, effective_mode, hard_lockout
            )
            device.eligible = device.check_eligible(st)
            device.update_from_ha(st, now_ts, global_puffer)
            # Hartes Gate VOR der Pool-Verteilung: ein Gerät, dessen Sollwert
            # nirgends ankommt, darf keine Leistung reservieren, die dann
            # niemand abruft. Es fährt weiter seinen sicheren Zustand, damit ein
            # repariertes Ziel ohne Neustart wieder eingefangen wird.
            device.check_runtime_health(st, self._write_failures.get(device.id, ""))
            if not device.runtime_active:
                device.eligible = False

        # ── 3. Netz-Bereinigung ─────────────────────────────────────────
        # Ein Speicher ist kein Verbraucher mit Vorzeichen: seine Entladung
        # erhöht residual_w, ist aber kein PV-Überschuss. Erst bereinigen,
        # dann regeln – sonst schaukelt sich der Pool auf (H-1).
        netz_support_w = sum(d.netz_support_w for d in self._devices)
        residual_bereinigt_w = (residual_w - netz_support_w
                                if self._speicher_in_residual else residual_w)

        # ── 4. Pool und Hausdefizit ─────────────────────────────────────
        # Zwei Summen, weil "was kann ich freigeben?" und "was soll der
        # Speicher decken?" zwei verschiedene Fragen sind:
        #   current_w        filtert den Force-Modus heraus  -> Pool
        #   gemessene_last_w filtert nichts                  -> Entladung
        # Eine von Hand eingeschaltete HEMS-Last ist weiterhin ein
        # Überschussverbraucher und wird vom Speicher nicht gedeckt.
        hems_last_w          = sum(d.current_w        for d in self._devices)
        hems_last_gemessen_w = sum(d.gemessene_last_w for d in self._devices)

        pool_roh_w      = residual_bereinigt_w + hems_last_w
        entlade_basis_w = residual_bereinigt_w + hems_last_gemessen_w

        # Bewusst nicht max(x, 0.0): das liefert bei x == -0.0 ein negatives Null
        # zurueck, und die Oberflaeche zeigte dann "-0 W".
        if not ems_enabled or effective_mode == "aus" or hard_lockout:
            pool_w = hausdefizit_w = 0.0
        else:
            pool_w        = pool_roh_w if pool_roh_w > 0 else 0.0
            hausdefizit_w = -entlade_basis_w if entlade_basis_w < 0 else 0.0

        # ── 5. Defizit ──────────────────────────────────────────────────
        current_deficit_w    = (-residual_bereinigt_w
                                if residual_bereinigt_w < 0 else 0.0)
        total_relief_w       = sum(d.max_relief_w for d in self._devices)
        binary_immediate_off = current_deficit_w > total_relief_w

        if current_deficit_w > 0 and debug_output:
            log.warning("EMS DEFIZIT: %.0fW  hausdefizit=%.0fW  sofort_aus=%s",
                        current_deficit_w, hausdefizit_w, binary_immediate_off)

        # Ein Speicher, der entlädt, während nennenswerter Überschuss verteilt
        # wird, ist physikalisch fast immer ein Konfigurationsfehler. Bewusst
        # ohne debug_output-Bedingung – das ist keine Debug-Information.
        if netz_support_w > 200 and pool_w > 200:
            log.warning("EMS Speicher: Entladung %.0fW UND Pool %.0fW gleichzeitig – "
                        "Speicher entlädt in den PV-Überschuss hinein. Prüfen: "
                        "speicher_in_residual_enthalten, Summensensor doppelt gezählt, "
                        "Umschaltsperre zu lang.", netz_support_w, pool_w)

        # ── 6. Binärer Wunschzustand (Pool in Prioritätsreihenfolge verbraucht) ──
        remaining_w = pool_w
        for device in sorted(self._devices, key=lambda d: d.priority):
            remaining_w = device.consume_from_pool(remaining_w, global_einschaltreserve)

        # ── 7. Binärer Kandidat (Zeit-Guards, off_delay) ────────────────
        binary_devices = [d for d in self._devices if isinstance(d, BinaryDevice)]
        for device in binary_devices:
            device.calculate_candidate(now_ts)

        # ── 8. Kandidat → final kopieren, dann Kaskade + One-Change anwenden ──
        for device in binary_devices:
            device.final_on = device.candidate_on

        self._apply_priority_cascade(binary_devices)
        self._limit_one_change(binary_devices, binary_immediate_off)

        # off_delay-Timer für final als AUS bestimmte Geräte zurücksetzen
        for device in binary_devices:
            if not device.final_on:
                device.reset_off_timer()

        # ── 9. Regelbare Geräte zuteilen (2 Durchläufe: Minimum zuerst) ──
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

        # ── 10. Entladeplanung ──────────────────────────────────────────
        # MUSS nach der Verbraucher-Allokation und vor calculate_ramp laufen:
        # der Speicher löst dort seine Richtung auf (D-B07).
        batteries = [d for d in self._devices if isinstance(d, BatteryDevice)]
        entlade_abschlag_w = safe_float(st.get(HA_AC_SPEICHER_ENTLADE_ABSCHLAG_W))
        self._allocate_discharge(batteries, hausdefizit_w, entlade_abschlag_w)

        # ── 11. Rampenbegrenzung ─────────────────────────────────────────
        for device in self._devices:
            device.calculate_ramp(current_deficit_w)

        # ── 12. Debug-Logging ───────────────────────────────────────────
        if debug_output:
            self._log_cycle(binary_devices, pool_w, binary_immediate_off, now_ts)

        # ── 13. HA-Schreiboperationen sammeln ───────────────────────────
        write_ops: List[WriteOp] = [op for d in self._devices for op in d.get_write_ops()]

        # ── 14. Status-Snapshot für die Web-UI aufbauen ─────────────────
        status = {
            "ems_enabled":           ems_enabled,
            # Roher HA-State, damit sichtbar bleibt, was der Helfer meldet.
            "global_mode":           global_mode,
            "global_mode_configured": global_mode_configured,
            "available_modes":       list(self._available_modes),
            "hard_lockout":          hard_lockout,
            "residual_sensor_valid": residual_sensor_valid,
            "residual_w":            residual_w,
            "residual_bereinigt_w":  residual_bereinigt_w,
            "netz_support_w":        netz_support_w,
            "hems_last_w":           hems_last_w,
            "hems_last_gemessen_w":  hems_last_gemessen_w,
            "pool_roh_w":            pool_roh_w,
            "pool_w":                pool_w,
            "entlade_basis_w":       entlade_basis_w,
            "hausdefizit_w":         hausdefizit_w,
            "current_deficit_w":     current_deficit_w,
            "binary_immediate_off":  binary_immediate_off,
            "binary_total_w":        binary_total_w,
            "devices":               [d.to_status_dict() for d in self._devices],
            # Beim Start übersprungene Einträge: sichtbar mit Feldfehlern, aber
            # ausdrücklich ohne erfundene Ist-, SoC- oder Schaltwerte.
            "inactive_devices":      self._inactive_devices,
            # Ein einzelnes Gerät mit kaputtem Schreibziel macht den Zyklus
            # nicht rot – die übrigen regeln weiter.
            "devices_inactive_runtime": [d.id for d in self._devices
                                         if not d.runtime_active],
            "timestamp":             now_dt,
        }

        return {"status": status, "write_ops": write_ops}

    # ------------------------------------------------------------------
    # Entlade-Koordination (D-B15)
    # ------------------------------------------------------------------

    def _allocate_discharge(self, batteries: List[BatteryDevice],
                            hausdefizit_w: float, entlade_abschlag_w: float) -> None:
        """Verteilt den Hausverbrauchs-Fehlbetrag auf die entladebereiten Speicher.

        Rechnet jeder Speicher unabhängig "ich decke das Defizit", entladen bei
        drei Speichern und 2 kW Defizit alle drei mit 2 kW und 4 kW gehen ins
        Netz (H-3). Die Aufteilung gehört deshalb genau einmal hierher.

        hausdefizit_w enthält per Konstruktion KEINE HEMS-Gerätelast, auch keine
        fremdgesteuerte – die Abgrenzung "nicht für Überschussverbraucher" ist
        damit bereits erledigt und braucht hier keine Sonderbehandlung.
        """
        for battery in batteries:
            battery.set_discharge_target(0.0)

        if hausdefizit_w <= 0:
            return

        kandidaten = [b for b in batteries if b.entlade_kapazitaet_w() > 0]
        if not kandidaten:
            if hausdefizit_w > 100:
                log.info("EMS Speicher: %.0fW Hausdefizit, kein Speicher entladebereit",
                         hausdefizit_w)
            return

        # Der Abschlag ist eine Systemgrösse und wird EINMAL abgezogen, nicht je
        # Speicher. Er sorgt dafür, dass im eingeschwungenen Zustand ein kleiner
        # Restbezug bleibt statt eines Exports (H-5).
        ziel_w = max(hausdefizit_w - max(entlade_abschlag_w, 0.0), 0.0)
        if ziel_w <= 0:
            return

        rest_w = ziel_w
        for battery in self._discharge_order(kandidaten):
            anteil_w = min(rest_w, battery.entlade_kapazitaet_w())
            battery.set_discharge_target(anteil_w)
            rest_w -= anteil_w
            if rest_w <= 0:
                break

        if rest_w > 100:
            log.info("EMS Speicher: %.0fW Hausdefizit ungedeckt (alle Speicher am Limit)",
                     rest_w)

    @staticmethod
    def _discharge_order(kandidaten: List[BatteryDevice]) -> List[BatteryDevice]:
        """Strikt nach Entladepriorität (D-B17), klein = zuerst.

        sorted() ist stabil, damit entscheidet bei Gleichstand die Reihenfolge in
        der Add-on-Konfiguration. Der SoC spielt in der Reihenfolge bewusst keine
        Rolle – ein leerer Speicher fällt über entlade_kapazitaet_w() heraus.
        """
        return sorted(kandidaten, key=lambda b: b.entlade_priority)

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
            if isinstance(d, BatteryDevice):
                netto_alt = d.lade_anforderung_w - d.entlade_anforderung_w
                netto_neu = d.new_lade_w - d.new_entlade_w
                if int(netto_neu) != int(netto_alt):
                    log.info("EMS [%s] %.0fW→%.0fW  soc=%.0f%%  betriebsart=%s  "
                             "ziel=%.0fW  pool=%.0fW",
                             d.id, netto_alt, netto_neu, d.soc_prozent,
                             d.new_betriebsart, d.entlade_ziel_w, pool_w)
            elif isinstance(d, ControllableDevice):
                if int(d.new_w) != int(d.anforderung_current_w):
                    log.info("EMS [%s] %.0fW→%.0fW  prio=%d  alloc=%.0fW  pool=%.0fW",
                             d.id, d.anforderung_current_w, d.new_w,
                             d.priority, d.alloc_w, pool_w)
