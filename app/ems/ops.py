"""Schreiboperationen des Regelzyklus und ihre Zielprüfung.

Eine Operation trägt ihren Besitzer mit. Nur so lässt sich ein
fehlgeschlagener Service-Aufruf dem verursachenden Gerät zuordnen, statt ihn in
einer anonymen Log-Zeile zu verlieren (B-2).

`WriteOp` ist bewusst ein NamedTuple und kein Dataclass: die Operationen wurden
bisher als `(domain, service, data)`-Tupel herumgereicht, und jeder bestehende
Konsument – Tests eingeschlossen – greift per Index darauf zu. Ein NamedTuple
gibt den Feldern Namen und Typen, ohne diesen Zugriff zu brechen.
"""

from typing import Any, Dict, NamedTuple, Tuple


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
