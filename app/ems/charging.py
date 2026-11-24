"""Watt-Ladeziele für EVMS, Wallbox-Provider und eigene HA-Automationen.

Die Gegenstelle liefert einen vollständigen Schnappschuss. Fehlende, alte oder
widersprüchliche Rückmeldungen sperren das Ziel auch unter Zwang. Ein neues
Zuordnungstoken verhindert, dass Vorgaben zum vorherigen Fahrzeug weitergelten.
"""

import math
import time

from .devices import ControllableDevice
from .state import STATE_VALID, Resolved, StateProxy

CHARGING_INTERFACES = {
    "evms": "sensor.evms_schnittstelle",
    "wallbox_provider": "sensor.wallbox_provider_schnittstelle",
    "automation": "sensor.wallbox_automation_schnittstelle",
}


class ChargingDevice(ControllableDevice):
    """Ein Ladeziel mit Wattbudget und explizit gewählter Gegenstelle."""

    READS_WALLBOX_INTERFACE = False

    def __init__(self, *, charging_backend: str, feedback_timeout_s: float, **kwargs):
        if kwargs.get("output_unit", "watt") != "watt":
            raise ValueError("Ladeziele erwarten Watt.")
        super().__init__(**kwargs)
        self.charging_backend = charging_backend
        self.interface_entity = CHARGING_INTERFACES[charging_backend]
        self.feedback_timeout_s = feedback_timeout_s
        self.assignment_id = ""
        self.measurement_valid = False
        self._last_sample = None
        self._last_sample_at = None

    @property
    def entity_prefix(self) -> str:
        return self._entity_prefix

    def _read_actual_power(self, st: StateProxy) -> Resolved:
        key = f"{self.entity_prefix}_istleistung_w"
        actual = self._note(f"{self.interface_entity}.{key}", "actual_power",
                            st.resolve_attribute_number(self.interface_entity, key, minimum=0))
        self.measurement_valid = actual.state == STATE_VALID
        if actual.state != STATE_VALID:
            self.mark_inactive("istleistung_ungueltig")
        return actual

    def update_from_ha(self, st: StateProxy, now_ts: float, global_puffer_w: float) -> None:
        super().update_from_ha(st, now_ts, global_puffer_w)
        self.assignment_id = ""
        self._geraet_sperrgrund = None
        attrs = st.getattr(self.interface_entity) or {}
        p = self.entity_prefix
        instance = attrs.get("instanz_id")
        assignment = attrs.get(f"{p}_zuordnung_id")
        counter = attrs.get(f"{p}_rueckmeldung_zaehler")
        version = attrs.get("ladevertrag_version")
        if (st.availability(self.interface_entity) != STATE_VALID
                or type(version) is not int or version != 1
                or not isinstance(instance, str) or not instance
                or not isinstance(assignment, str) or not assignment
                or type(counter) is not int or counter < 0):
            self._last_sample = None
            self._last_sample_at = None
            self.measurement_valid = False
            self.mark_inactive("laderueckmeldung_ungueltig")
            return

        self.assignment_id = assignment
        sample = (instance, assignment, counter)
        now = time.monotonic()
        # Ein restaurierter HA-State ist kein Lebenszeichen. Erst eine weitere
        # Probe derselben Zuordnung bestätigt, dass die Gegenstelle lebt.
        if self._last_sample is None or sample[:2] != self._last_sample[:2]:
            self._last_sample = sample
            self._last_sample_at = None
        elif sample != self._last_sample:
            self._last_sample = sample
            self._last_sample_at = now
        if self._last_sample_at is None or now - self._last_sample_at >= self.feedback_timeout_s:
            self.measurement_valid = False
            self.mark_inactive("laderueckmeldung_veraltet")

        release = st.resolve_attribute_bool(self.interface_entity, f"{p}_freigabe")
        if release.value is not True:
            reason = attrs.get(f"{p}_sperrgrund")
            self._geraet_sperrgrund = reason if isinstance(reason, str) and reason else "Keine Ladefreigabe"
            self.mark_inactive("wallbox_gesperrt")

        minimum = st.resolve_attribute_number(self.interface_entity, f"{p}_minimum_w", minimum=0)
        maximum = st.resolve_attribute_number(self.interface_entity, f"{p}_maximum_w", minimum=0)
        if minimum.value is None or maximum.value is None or maximum.value < minimum.value:
            self.mark_inactive("ladegrenzen_ungueltig")
            return
        self._raw_min = max(self._raw_min, minimum.value)
        self._raw_max = min(self._raw_max, maximum.value)
        if self._raw_max <= 0 or self._raw_min > self._raw_max:
            self.mark_inactive("ladegrenzen_ungueltig")
        self._apply_raw_to_watt()

    def get_write_ops(self):
        # Auch ein kleines abgesenktes Maximum muss trotz Totband sofort gelten.
        # Auf ganze Watt abrunden: ein Budget darf durch Rundung nicht wachsen.
        self._new_w = math.floor(max(0, min(self._new_w, self.max_technisch_w)))
        if not self.runtime_active or 0 < self._new_w < self.min_technisch_w:
            self._new_w = 0.0
        force_write = (self._anforderung_current_w > self.max_technisch_w
                       or 0 < self._anforderung_current_w < self.min_technisch_w)
        deadband = self.deadband_w
        if force_write:
            self.deadband_w = 0
        try:
            return super().get_write_ops()
        finally:
            self.deadband_w = deadband

    def to_status_dict(self):
        return {**super().to_status_dict(), "charging_backend": self.charging_backend,
                "charging_measurement_valid": self.measurement_valid,
                "charging_assignment_id": self.assignment_id,
                "charging_interface": self.interface_entity}
