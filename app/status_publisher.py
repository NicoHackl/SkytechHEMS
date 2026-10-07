"""HEMS-Lebenszeichen für die Provider-Integrationen (D-062).

Das Add-on schreibt nach jedem durchlaufenen Zyklus ``sensor.skytech_hems_status``
in die HA-Zustandsmaschine. Wallbox- und Battery-Provider erkennen daran, ob das
HEMS noch regelt: Ein unverändert bleibender Sollwert ist normaler Betrieb und
taugt deshalb nicht als Lebenszeichen. Vertrag: ``contract/contract_hems_wallbox_provider/``
und ``contract/contract_hems_battery_provider/``.

Grenzen wie beim Flow-Publisher (D-046):

* Es schaltet nichts. Der Sensor ist reine Information, kein Regelpfad.
* Es wirft nie. Ein misslungener Schreibvorgang darf keinen Zyklus kosten.
* Der Zähler ändert sich bei jeder Veröffentlichung. Die Provider werten nur die
  Änderung aus, nie die Uhrzeit — ``erzeugt_am`` ist reine Anzeige.
"""

import logging
from typing import Any, Dict, Tuple

log = logging.getLogger(__name__)

STATUS_ENTITY_ID = "sensor.skytech_hems_status"
CONTRACT_VERSION = 1


def build_status_state(counter: int, interval_s: float,
                       created_at: str) -> Tuple[str, Dict[str, Any]]:
    """State und Attribute des Lebenszeichens."""
    attributes: Dict[str, Any] = {
        "friendly_name":       "Skytech HEMS Status",
        "icon":                "mdi:heart-pulse",
        "zyklus_zaehler":      counter,
        "zyklus_intervall_s":  interval_s,
        "erzeugt_am":          created_at,
        "vertrag_version":     CONTRACT_VERSION,
    }
    return str(counter), attributes


class StatusPublisher:
    """Hält den Zykluszähler und schreibt das Lebenszeichen."""

    def __init__(self) -> None:
        self._counter = 0

    @property
    def counter(self) -> int:
        return self._counter

    async def publish(self, ha_client, interval_s: float, created_at: str) -> bool:
        """Erhöht den Zähler und schreibt den Sensor. Wirft nie."""
        self._counter += 1
        try:
            state, attributes = build_status_state(self._counter, interval_s, created_at)
            return bool(await ha_client.set_state(STATUS_ENTITY_ID, state, attributes))
        except Exception as exc:
            log.warning("HEMS-Lebenszeichen konnte nicht veröffentlicht werden: %s", exc)
            return False
