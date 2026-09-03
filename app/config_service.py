"""Fachlogik hinter den Konfigurations-Endpunkten.

Bewusst ohne HTTP-Kenntnis: die aiohttp-Handler in `main.py` bleiben dünn und
übersetzen nur noch Ausnahmen in Statuscodes. So ist der ganze Ablauf – lesen,
validieren, Revision prüfen, mischen, speichern, sicher deaktivieren, neu
starten – ohne Webserver testbar, und `main.py` wächst nicht weiter zu.

Reihenfolge beim Speichern, in genau dieser Abfolge:

1. eigene fachliche Validierung (`configuration.validate_options`);
2. Validierung durch den Supervisor gegen das Manifest-Schema;
3. Revisionsprüfung unmittelbar vor dem Schreiben;
4. bekannte Felder in die FRISCH gelesenen rohen Optionen mischen;
5. speichern – ohne Neustart.
"""

import asyncio
import logging
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional

from configuration import (
    BATTERY_POWER_FIELDS,
    BATTERY_STATIC_DEFAULTS,
    BINARY_FALLBACK_DEFAULTS,
    CONTROLLABLE_FALLBACK_DEFAULTS,
    DEVICE_CLASSES,
    GLOBAL_DEFAULTS,
    LOG_LEVELS,
    NORMAL_MODES,
    OUTPUT_UNITS,
    PHASE_VALUES,
    POWER_SIGNS,
    PROTECTED_MINIMUM_SCOPES,
    SPECIAL_MODES,
    devices_needing_shutdown,
    merge_known_fields,
    normalize_options,
    revision,
    validate_options,
)
from ems.ops import safe_shutdown_ops
from ems.state import StateProxy
from formula import run_formula
from supervisor_client import (
    SupervisorPermissionDenied,
    SupervisorRejected,
    SupervisorUnavailable,
)

log = logging.getLogger(__name__)

# Domains, die die Entitätsauswahl der Oberfläche standardmäßig anbietet.
DEFAULT_ENTITY_DOMAINS = ("sensor", "switch", "script")

# Nach dem Auslösen des Neustarts bleibt der Antwort Zeit, den Browser zu
# erreichen, bevor der Supervisor den Prozess beendet.
RESTART_DELAY_S = 0.5


class ConfigProblem(Exception):
    """Fachlicher Fehler mit passendem HTTP-Status."""

    status = 500

    def __init__(self, message: str, payload: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.payload = payload or {}


class ConfigInvalid(ConfigProblem):
    status = 422


class ConfigConflict(ConfigProblem):
    status = 409


class ConfigReadOnly(ConfigProblem):
    status = 503


class ConfigUnavailable(ConfigProblem):
    status = 502


class ConfigPermissionDenied(ConfigProblem):
    status = 403


class ConfigService:
    """Verwaltet die Add-on-Optionen für die eigene Oberfläche."""

    def __init__(self, *, supervisor, write_ops, local_options: Dict[str, Any],
                 loaded_options: Dict[str, Any], instance_id: str,
                 entity_snapshot: Callable[[], Dict[str, Dict]],
                 restart_hook: Optional[Callable[[], Any]] = None,
                 restart_delay_s: float = RESTART_DELAY_S):
        self._supervisor = supervisor
        self._write_ops = write_ops                 # async (List[WriteOp]) -> List[WriteResult]
        self._local_options = local_options          # roh aus /data/options.json
        self._loaded_options = loaded_options        # Stand, mit dem der Controller läuft
        self._loaded_revision = revision(loaded_options)
        self._instance_id = instance_id
        self._entity_snapshot = entity_snapshot
        self._restart_hook = restart_hook
        self._restart_delay_s = restart_delay_s
        # Die laufende Neustart-Aufgabe bleibt greifbar: sonst wäre von außen
        # nicht feststellbar, ob der Neustart tatsächlich angestoßen wurde.
        self.restart_task: Optional["asyncio.Task"] = None

    # ------------------------------------------------------------------
    # Lesen
    # ------------------------------------------------------------------

    async def stored_options(self) -> Dict[str, Any]:
        """Die aktuell beim Supervisor gespeicherten ROHEN Optionen.

        Ohne Supervisor bleibt die beim Start gelesene Datei die einzige Quelle;
        gespeichert werden kann dann nichts.
        """
        if not self._supervisor.available:
            return self._local_options
        info = await self._supervisor.get_self_info()
        options = info.get("options")
        return options if isinstance(options, dict) else {}

    async def addon_version(self) -> str:
        """Version des laufenden Add-ons, vom Supervisor.

        Der einzige Weg zur Laufzeit: `config.yaml` liegt nicht im Image
        (`COPY app/ .`), und ein YAML-Parser ist nicht installiert. Ohne
        Supervisor bleibt die Version leer statt geraten.
        """
        if not self._supervisor.available:
            return ""
        try:
            info = await self._supervisor.get_self_info()
        except Exception:
            return ""
        return str(info.get("version") or "")

    async def read(self) -> Dict[str, Any]:
        """Alles, was die Konfigurationsseite zum Anzeigen braucht."""
        supervisor_error = ""
        try:
            stored = await self.stored_options()
        except (SupervisorUnavailable, SupervisorRejected) as exc:
            # Nicht scheitern: die lokal gelesene Konfiguration ist besser als
            # eine leere Seite – nur schreiben lässt sich dann nicht.
            supervisor_error = str(exc)
            stored = self._local_options

        validated = validate_options(stored)
        stored_revision = revision(stored)
        schreibbar = self._supervisor.available and not supervisor_error

        return {
            "options": validated.options,
            "valid": validated.valid,
            "errors": validated.errors,
            "field_errors": validated.field_errors,
            "inactive_devices": [asdict(issue) for issue in validated.inactive_devices],
            "stored_revision": stored_revision,
            "loaded_revision": self._loaded_revision,
            "restart_required": stored_revision != self._loaded_revision,
            "can_save": schreibbar,
            "can_restart": schreibbar,
            "supervisor_available": self._supervisor.available,
            "supervisor_error": supervisor_error,
            "instance_id": self._instance_id,
            "supported": self.supported(),
        }

    @staticmethod
    def supported() -> Dict[str, Any]:
        """Wertebereiche und Formular-Startwerte – eine Quelle für Server und UI."""
        return {
            "modes": list(NORMAL_MODES),
            "special_modes": list(SPECIAL_MODES),
            "device_classes": list(DEVICE_CLASSES),
            "log_levels": list(LOG_LEVELS),
            "output_units": list(OUTPUT_UNITS),
            "phases": list(PHASE_VALUES),
            "power_signs": list(POWER_SIGNS),
            "protected_minimum_scopes": list(PROTECTED_MINIMUM_SCOPES),
            "global_defaults": dict(GLOBAL_DEFAULTS),
            "device_defaults": {
                "controllable": dict(CONTROLLABLE_FALLBACK_DEFAULTS),
                "binary": dict(BINARY_FALLBACK_DEFAULTS),
                "battery": {
                    **{key: None for key in BATTERY_POWER_FIELDS},
                    **BATTERY_STATIC_DEFAULTS,
                },
            },
        }

    def entities(self, domains: Optional[List[str]] = None) -> List[Dict[str, str]]:
        """Reduzierte Entitätsliste für die Suchauswahl der Oberfläche.

        Bewusst ohne die vollständigen Attribute: die Auswahl braucht Name und
        Zustand, nicht jeden Messwert der Anlage.
        """
        erlaubt = tuple(domains or DEFAULT_ENTITY_DOMAINS)
        ergebnis = []
        for entity_id, entry in (self._entity_snapshot() or {}).items():
            domain = entity_id.split(".", 1)[0]
            if domain not in erlaubt:
                continue
            attributes = entry.get("attributes") or {}
            ergebnis.append({
                "entity_id": entity_id,
                "domain": domain,
                "state": str(entry.get("state") or ""),
                "friendly_name": str(attributes.get("friendly_name") or ""),
            })
        ergebnis.sort(key=lambda item: item["entity_id"])
        return ergebnis

    # ------------------------------------------------------------------
    # Validieren und Speichern
    # ------------------------------------------------------------------

    @staticmethod
    def validate(draft: Dict[str, Any]) -> Dict[str, Any]:
        """Prüft einen Entwurf, ohne ihn zu speichern."""
        validated = validate_options(draft)
        return {
            "valid": validated.valid,
            "errors": validated.errors,
            "field_errors": validated.field_errors,
            "inactive_devices": [asdict(issue) for issue in validated.inactive_devices],
        }

    def test_formula(self, kind: str, variables: List[Dict[str, str]],
                     code: str) -> Dict[str, Any]:
        """Führt einen Formel-Entwurf (D-045) live gegen den aktuellen
        HA-Schnappschuss aus – ohne zu speichern. Nutzt denselben Schnappschuss
        wie `entities()`, deshalb immer den Stand des letzten Regelzyklus, nie
        einen eigenen HA-Abruf.

        `kind` ist "residual" oder "battery_residual" und bestimmt nur, welche
        Ausgabevariable erwartet wird – das ist ein reines Diagnosewerkzeug wie
        `validate()`, daher kein Fehlschlag bei ungültiger Formel: das Ergebnis
        trägt `valid: false` mit Begründung statt eine Exception zu werfen.
        """
        output_name = "hausbilanz" if kind == "battery_residual" else "ueberschuss"
        st = StateProxy(self._entity_snapshot() or {})
        namespace, diagnostics = st.resolve_formula_namespace(variables)
        result = run_formula(code, namespace, output_name)
        return {
            "valid": result.valid,
            "value": result.value,
            "error": result.error,
            "error_line": result.error_line,
            "variables": diagnostics,
        }

    async def save(self, draft: Dict[str, Any], stored_revision: str) -> Dict[str, Any]:
        """Validiert, prüft die Revision und speichert – ohne Neustart."""
        self._require_supervisor()

        validated = validate_options(draft)
        if not validated.valid:
            raise ConfigInvalid("Die Konfiguration ist noch nicht vollständig.", {
                "errors": validated.errors,
                "field_errors": validated.field_errors,
            })

        # Erst die frisch gelesenen rohen Optionen holen: sie sind zugleich die
        # Revisionsbasis und die Grundlage für den Merge unbekannter Felder.
        aktuell = await self._call_supervisor(self.stored_options())
        if revision(aktuell) != stored_revision:
            raise ConfigConflict(
                "Die Add-on-Konfiguration wurde zwischenzeitlich an anderer Stelle "
                "geändert. Bitte neu laden und die Änderung erneut eintragen.",
                {"stored_revision": revision(aktuell)},
            )

        merged = merge_known_fields(aktuell, draft)

        gueltig, meldung = await self._call_supervisor(
            self._supervisor.validate_self_options(merged))
        if not gueltig:
            raise ConfigInvalid(
                f"Der Supervisor hat die Konfiguration abgelehnt: {meldung}"
                if meldung else "Der Supervisor hat die Konfiguration abgelehnt.")

        await self._call_supervisor(self._supervisor.save_self_options(merged))
        neue_revision = revision(merged)
        log.info("Add-on-Optionen gespeichert (Revision %s). Wirksam wird die "
                 "Änderung erst nach einem Neustart.", neue_revision[:12])
        return {
            "stored_revision": neue_revision,
            "loaded_revision": self._loaded_revision,
            "restart_required": neue_revision != self._loaded_revision,
        }

    # ------------------------------------------------------------------
    # Sichere Deaktivierung und Neustart
    # ------------------------------------------------------------------

    async def deactivate_old_devices(self, target_options: Dict[str, Any]) -> List[str]:
        """Setzt die Ausgänge geänderter oder gelöschter Altgeräte sicher.

        Maßgeblich ist die laufende Alt-Konfiguration, nicht der Entwurf: nur
        deren Schreibziele existieren gerade. Gibt die Geräte-IDs zurück, deren
        Deaktivierung fehlgeschlagen ist.
        """
        betroffen = devices_needing_shutdown(self._loaded_options, target_options)
        if not betroffen:
            return []

        ops = [op for device in betroffen for op in safe_shutdown_ops(device)]
        results = await self._write_ops(ops)
        fehlgeschlagen = sorted({result.op.owner for result in results if not result.ok})
        if fehlgeschlagen:
            log.error("Sichere Deaktivierung fehlgeschlagen für: %s – kein Neustart.",
                      ", ".join(fehlgeschlagen))
        else:
            log.info("%d Altgerät(e) vor dem Neustart sicher deaktiviert.", len(betroffen))
        return fehlgeschlagen

    async def restart(self) -> Dict[str, Any]:
        """Deaktiviert betroffene Altgeräte und startet danach neu.

        Verwirft niemals still einen Browser-Entwurf: die Oberfläche bestätigt
        ungespeicherte Änderungen vorher. Gearbeitet wird ausschließlich mit den
        bereits gespeicherten Optionen.
        """
        self._require_supervisor()
        gespeichert = await self._call_supervisor(self.stored_options())
        fehlgeschlagen = await self.deactivate_old_devices(gespeichert)
        if fehlgeschlagen:
            raise ConfigReadOnly(
                "Der Neustart wurde nicht ausgelöst: diese Geräte ließen sich nicht "
                "sicher abschalten: " + ", ".join(fehlgeschlagen) + ".",
                {"deactivation_failed": fehlgeschlagen},
            )
        self._schedule_restart()
        return {
            "restarting": True,
            "instance_id": self._instance_id,
            "stored_revision": revision(gespeichert),
        }

    async def save_and_restart(self, draft: Dict[str, Any],
                               stored_revision: str) -> Dict[str, Any]:
        """Speichert zuerst, deaktiviert dann, startet zuletzt neu.

        Schlägt die Deaktivierung fehl, bleibt die Konfiguration gespeichert und
        der Neustart unterbleibt. Dieser Teilstatus wird ausdrücklich benannt –
        „gespeichert, aber nicht neu gestartet" ist etwas anderes als ein Fehler.
        """
        gespeichert = await self.save(draft, stored_revision)
        fehlgeschlagen = await self.deactivate_old_devices(normalize_options(draft))
        if fehlgeschlagen:
            return {
                **gespeichert,
                "restarting": False,
                "deactivation_failed": fehlgeschlagen,
                "message": (
                    "Die Konfiguration ist gespeichert, der Neustart wurde aber nicht "
                    "ausgelöst: diese Geräte ließen sich nicht sicher abschalten: "
                    + ", ".join(fehlgeschlagen) + "."
                ),
            }
        self._schedule_restart()
        return {**gespeichert, "restarting": True, "instance_id": self._instance_id}

    # ------------------------------------------------------------------
    # Interne Helfer
    # ------------------------------------------------------------------

    def _require_supervisor(self) -> None:
        if not self._supervisor.available:
            raise ConfigReadOnly(
                "Ohne Supervisor-Zugang ist die Konfiguration schreibgeschützt. "
                "Das Add-on läuft gerade außerhalb von Home Assistant."
            )

    @staticmethod
    async def _call_supervisor(awaitable):
        """Übersetzt Supervisor-Fehler in fachliche Fehler mit passendem Status."""
        try:
            return await awaitable
        except SupervisorPermissionDenied as exc:
            raise ConfigPermissionDenied(str(exc)) from exc
        except SupervisorUnavailable as exc:
            raise ConfigUnavailable(str(exc)) from exc
        except SupervisorRejected as exc:
            raise ConfigInvalid(str(exc)) from exc

    def _schedule_restart(self) -> None:
        """Stößt den Neustart erst NACH der ausgelieferten Antwort an."""
        hook = self._restart_hook or self._supervisor.restart_self

        async def _spaeter() -> None:
            await asyncio.sleep(self._restart_delay_s)
            try:
                await hook()
            except Exception as exc:
                log.error("Neustart konnte nicht ausgelöst werden: %s", exc)

        self.restart_task = asyncio.get_running_loop().create_task(_spaeter())
