"""Schnittstellen-Entität des HEMS: sensor.hems_schnittstelle (D-069).

Grundsatz (D-069): Jede Einheit veröffentlicht genau eine Entität
``sensor.<einheit>_schnittstelle`` mit allen Informationen für die anderen
Teilnehmer. Das Add-on schreibt seine nach jedem durchlaufenen Zyklus in die
HA-Zustandsmaschine. Sie trägt

* das Lebenszeichen (D-062): ``zyklus_zaehler`` ändert sich bei jeder
  Veröffentlichung. Wallbox- und Battery-Provider erkennen daran, ob das HEMS
  noch regelt – ein unverändert bleibender Sollwert ist normaler Betrieb und
  taugt nicht als Lebenszeichen;
* je Speicher die Ist-Lade- und Ist-Entladeleistung aus den HEMS-Sensoren
  (``<prefix>_ladeleistung``, ``<prefix>_entladeleistung``). Der Battery-Provider
  rechnet damit seinen Soll/Ist-Vergleich, weil diese Sensoren schneller sind
  als die Gerätewerte.

State ist die Liste der Speicher-Präfixe, durch Komma getrennt. Verträge:
``contract/contract_hems_wallbox_provider/`` und ``contract/contract_hems_battery_provider/``.

Grenzen wie beim Flow-Publisher (D-046):

* Es schaltet nichts. Der Sensor ist reine Information, kein Regelpfad.
* Es wirft nie. Ein misslungener Schreibvorgang darf keinen Zyklus kosten.
* Die Provider werten nur die Änderung des Zählers aus, nie die Uhrzeit —
  ``erzeugt_am`` ist reine Anzeige.
"""

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

log = logging.getLogger(__name__)

STATUS_ENTITY_ID = "sensor.hems_schnittstelle"
# Version der Attributstruktur. 2: Lebenszeichen aus sensor.skytech_hems_status
# hierher verlegt, State = Speicher-Präfixe, Istwerte je Speicher (D-069).
CONTRACT_VERSION = 2


@dataclass(frozen=True)
class BatteryInterfaceValue:
    """Was das HEMS je Speicher veröffentlicht. `None` = kein gültiger Istwert."""

    prefix: str
    lade_ist_w: Optional[float]
    entlade_ist_w: Optional[float]


def _valid_power(value: Optional[float]) -> bool:
    return value is not None and math.isfinite(value) and value >= 0


def build_status_state(counter: int, interval_s: float, created_at: str,
                       batteries: Iterable[BatteryInterfaceValue] = ()
                       ) -> Tuple[str, Dict[str, Any]]:
    """State und Attribute der Schnittstellen-Entität.

    Ein Speicher ohne gültigen Istwert steht im State, seine beiden
    Leistungsattribute fehlen aber: der Provider pausiert dann seinen
    Soll/Ist-Vergleich, statt mit einem geratenen Wert zu rechnen.
    """
    batteries = list(batteries)
    attributes: Dict[str, Any] = {
        "friendly_name":       "HEMS-Schnittstelle",
        "icon":                "mdi:heart-pulse",
        "zyklus_zaehler":      counter,
        "zyklus_intervall_s":  interval_s,
        "erzeugt_am":          created_at,
        "vertrag_version":     CONTRACT_VERSION,
    }
    for battery in batteries:
        if _valid_power(battery.lade_ist_w) and _valid_power(battery.entlade_ist_w):
            attributes[f"{battery.prefix}_ladeleistung"] = round(battery.lade_ist_w, 1)
            attributes[f"{battery.prefix}_entladeleistung"] = round(battery.entlade_ist_w, 1)
    return ",".join(b.prefix for b in batteries), attributes


class StatusPublisher:
    """Hält den Zykluszähler und schreibt die Schnittstellen-Entität."""

    def __init__(self) -> None:
        self._counter = 0

    @property
    def counter(self) -> int:
        return self._counter

    async def publish(self, ha_client, interval_s: float, created_at: str,
                      batteries: Iterable[BatteryInterfaceValue] = ()) -> bool:
        """Erhöht den Zähler und schreibt den Sensor. Wirft nie."""
        self._counter += 1
        try:
            state, attributes = build_status_state(
                self._counter, interval_s, created_at, batteries)
            return bool(await ha_client.set_state(STATUS_ENTITY_ID, state, attributes))
        except Exception as exc:
            log.warning("HEMS-Schnittstelle konnte nicht veröffentlicht werden: %s", exc)
            return False
