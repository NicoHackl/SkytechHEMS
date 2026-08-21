"""Schreiboperationen des Regelzyklus und ihre Zielprüfung.

Eine Operation trägt ihren Besitzer mit. Nur so lässt sich ein
fehlgeschlagener Service-Aufruf dem verursachenden Gerät zuordnen, statt ihn in
einer anonymen Log-Zeile zu verlieren (B-2).

`WriteOp` ist bewusst ein NamedTuple und kein Dataclass: die Operationen wurden
bisher als `(domain, service, data)`-Tupel herumgereicht, und jeder bestehende
Konsument – Tests eingeschlossen – greift per Index darauf zu. Ein NamedTuple
gibt den Feldern Namen und Typen, ohne diesen Zugriff zu brechen.
"""

from typing import Any, Dict, List, NamedTuple, Tuple


class WriteOp(NamedTuple):
    """Ein HA-Service-Aufruf samt verursachendem Gerät."""

    domain: str
    service: str
    data: Dict[str, Any]
    owner: str = ""          # Geräte-ID; leer = globale Operation


class WriteResult(NamedTuple):
    """Ergebnis einer ausgeführten Operation."""

    op: WriteOp
    ok: bool
    error: str = ""


class WriteTarget(NamedTuple):
    """Eine Entität, die ein Gerät beschreiben MUSS, damit es regeln kann.

    Für Schreibziele gibt es keinen Fallback: einen Sollwert kann man nicht
    erfinden. Fehlt das Ziel, hat es die falsche Domain oder nicht die nötigen
    Optionen, ist das Gerät nicht regelbar – und zwar nur dieses.
    """

    entity_id: str
    role: str
    domain: str
    options: Tuple[str, ...] = ()          # nötige input_select-Optionen
    requires_negative_minimum: bool = False


# ---------------------------------------------------------------------------
# Sichere Ausgangszustände
# ---------------------------------------------------------------------------

# Reihenfolge beim Speicher: erst die signierte Leistung auf 0, danach die
# Betriebsart auf standby. Ein Modussprung bei stehender Leistung kann am Gerät
# einen Stromstoss erzeugen.
def safe_shutdown_ops(device_config: Dict[str, Any]) -> List[WriteOp]:
    """Operationen, die ein Gerät sicher stilllegen.

    Abgeleitet aus der ALTEN, laufenden Konfiguration – nur deren Schreibziele
    existieren gerade. Aus dem bearbeiteten Entwurf abgeleitet würde man die
    neuen Entitäten beschreiben und die alten weiterlaufen lassen.
    """
    name = device_config.get("name") or ""
    prefix = device_config.get("entity_prefix") or name
    device_class = device_config.get("class") or ""

    if device_class == "controllable":
        suffix = "a" if device_config.get("output_unit") == "ampere" else "w"
        return [WriteOp("input_number", "set_value", {
            "entity_id": f"input_number.ems_{prefix}_anforderung_leistung_{suffix}",
            "value": 0.0,
        }, name)]

    if device_class == "binary":
        return [WriteOp("input_boolean", "turn_off", {
            "entity_id": f"input_boolean.ems_{prefix}_anforderung_an",
        }, name)]

    if device_class == "battery":
        return [
            WriteOp("input_number", "set_value", {
                "entity_id": f"input_number.ems_{prefix}_anforderung_leistung_w",
                "value": 0.0,
            }, name),
            WriteOp("input_select", "select_option", {
                "entity_id": f"input_select.ems_{prefix}_anforderung_betriebsart",
                "option": "standby",
            }, name),
        ]

    return []
