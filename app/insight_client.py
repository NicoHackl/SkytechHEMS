"""Einzige Stelle mit Zugriff auf die Datenbank von Skytech Data Insight (D-065).

Vertrag: `contract/contract_hems_data_insight/contract_hems_data_insight.md`
(Version 0.2). Das HEMS schreibt ausschließlich über die Funktionen `hems_*`
und liest nur die Sichten, die der Vertrag freigibt.

Grenzen:

* Keine Fachlogik. Welche Sensoren, Rollen und Werte geschrieben werden,
  entscheidet `tariff/insight_sync.py`.
* Das Passwort erscheint nie in Log, Ausnahme oder Status.
* Jede Datenbankausnahme wird zu `InsightError` mit einer kurzen deutschen
  Meldung; die Verbindung wird danach verworfen und beim nächsten Aufruf neu
  aufgebaut.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import psycopg
from psycopg.types.json import Jsonb

log = logging.getLogger(__name__)

CONTRACT_VERSION = "0.2"
DATABASE = "skytech"
ROLE = "skytech_hems"
CONNECT_TIMEOUT_S = 5
# Kein Aufruf darf den Takt des Moduls länger blockieren.
STATEMENT_TIMEOUT_MS = 20000
# Eingabefehler der hems_*-Funktionen (Vertrag, Abschnitt „Rechte“).
INVALID_INPUT_SQLSTATE = "22023"


class InsightError(RuntimeError):
    """Data Insight nicht nutzbar oder Aufruf abgelehnt; Text für den Status."""


@dataclass(frozen=True)
class InsightSettings:
    host: str
    port: int
    password: str
    database: str = DATABASE


@dataclass(frozen=True)
class RoleValue:
    """Ein 15-min-Wert einer Rolle aus `v_hems_rolle_15min`."""

    mean: Optional[float]
    coverage_s: float
    unit: Optional[str]


class InsightClient:
    def __init__(self, settings: InsightSettings) -> None:
        self.settings = settings
        self._conn: Optional[psycopg.AsyncConnection] = None

    # ------------------------------------------------------------------
    # Verbindung
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Verbindet und prüft die Vertragsversion. Wirft InsightError."""
        if self._conn is not None and not self._conn.closed:
            return
        try:
            self._conn = await psycopg.AsyncConnection.connect(
                host=self.settings.host, port=self.settings.port, dbname=self.settings.database, user=ROLE,
                password=self.settings.password, connect_timeout=CONNECT_TIMEOUT_S, autocommit=True,
                application_name="skytech_hems", options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}")
        except psycopg.OperationalError as exc:
            self._conn = None
            raise InsightError(_connect_reason(exc)) from None
        version = await self._fetchval("SELECT version FROM skytech.v_hems_vertrag")
        if version != CONTRACT_VERSION:
            await self.close()
            raise InsightError(
                f"Vertragsversion von Data Insight ist {version}, das HEMS erwartet {CONTRACT_VERSION}")

    async def close(self) -> None:
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:  # noqa: BLE001 – Schließen darf nie werfen
                pass
        self._conn = None

    @property
    def connected(self) -> bool:
        return self._conn is not None and not self._conn.closed

    # ------------------------------------------------------------------
    # Sensoren und Rollen
    # ------------------------------------------------------------------

    async def ensure_sensor(self, entity_id: str, attribute: Optional[str], name: str, category: str,
                            quantity: str, unit: Optional[str], source: str) -> int:
        return int(await self._fetchval(
            "SELECT skytech.hems_sensor_sichern(%s, %s, %s, %s, %s, %s, %s)",
            (entity_id, attribute, name, category, quantity, unit, source)))

    async def deactivate_sensor(self, sensor_id: int) -> None:
        await self._execute("SELECT skytech.hems_sensor_stilllegen(%s)", (sensor_id,))

    async def assign(self, role: str, sensor_id: int) -> None:
        await self._execute("SELECT skytech.hems_zuordnen(%s, %s)", (role, sensor_id))

    async def current_assignments(self) -> Dict[str, Tuple[int, str]]:
        """Aktuelle Zuordnung je Rolle: (sensor_id, entity_id)."""
        rows = await self._fetch(
            "SELECT rolle, sensor_id, entity_id FROM skytech.v_hems_zuordnung WHERE gueltig_bis IS NULL")
        return {row[0]: (int(row[1]), row[2]) for row in rows}

    async def managed_sensor_ids(self) -> Dict[int, bool]:
        """Vom HEMS verwaltete Sensoren mit ihrem Aktiv-Zustand."""
        rows = await self._fetch("SELECT id, aktiv FROM skytech.sensor WHERE verwaltet_von = 'hems'")
        return {int(row[0]): bool(row[1]) for row in rows}

    # ------------------------------------------------------------------
    # Werte
    # ------------------------------------------------------------------

    async def last_slot(self, role: str) -> Optional[datetime]:
        """Jüngster 15-min-Slot, den es für eine Rolle gibt."""
        return await self._fetchval("SELECT max(zeit) FROM skytech.v_hems_rolle_15min WHERE rolle = %s", (role,))

    async def role_values(self, roles: Sequence[str], start: datetime, end: datetime
                          ) -> Dict[str, Dict[datetime, RoleValue]]:
        """15-min-Werte je Rolle für Slots mit Beginn in [start, end)."""
        rows = await self._fetch(
            "SELECT rolle, zeit, mittel, abdeckung_s, einheit FROM skytech.v_hems_rolle_15min "
            "WHERE rolle = ANY(%s) AND zeit >= %s AND zeit < %s",
            (list(roles), start, end))
        result: Dict[str, Dict[datetime, RoleValue]] = {role: {} for role in roles}
        for role, slot, mean, coverage, unit in rows:
            result[role][slot] = RoleValue(None if mean is None else float(mean), float(coverage or 0.0), unit)
        return result

    async def price_values(self, start: datetime, end: datetime) -> Dict[datetime, float]:
        """Aktuelle Preiskurve aus `v_preis` für Slots mit Beginn in [start, end)."""
        rows = await self._fetch("SELECT zeit, preis_eur_kwh FROM skytech.v_preis WHERE zeit >= %s AND zeit < %s",
                                 (start, end))
        return {row[0]: float(row[1]) for row in rows}

    async def write_values(self, sensor_id: int, times: List[datetime], values: List[Optional[float]]) -> int:
        return int(await self._fetchval(
            "SELECT skytech.hems_messwerte_schreiben(%s, %s::timestamptz[], %s::double precision[])",
            (sensor_id, times, values)))

    async def write_run(self, *, kind: str, source: str, created: datetime, raster_min: int,
                        valid_from: datetime, valid_until: datetime, unit: str, method: Optional[str],
                        details: Dict[str, Any], times: List[datetime], values: List[float],
                        p10: Optional[List[Optional[float]]] = None,
                        p90: Optional[List[Optional[float]]] = None) -> int:
        return int(await self._fetchval(
            "SELECT skytech.hems_lauf_schreiben(%s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s::timestamptz[], %s::double precision[], %s::double precision[], %s::double precision[])",
            (kind, source, created, raster_min, valid_from, valid_until, unit, method, Jsonb(details),
             times, values, p10, p90)))

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    async def _cursor_run(self, sql: str, params: Iterable[Any] = ()) -> psycopg.AsyncCursor:
        if not self.connected:
            await self.connect()
        assert self._conn is not None
        try:
            cursor = self._conn.cursor()
            await cursor.execute(sql, tuple(params))
            return cursor
        except psycopg.Error as exc:
            reason = _query_reason(exc)
            if not isinstance(exc, psycopg.errors.DataError) and exc.sqlstate != INVALID_INPUT_SQLSTATE:
                await self.close()
            raise InsightError(reason) from None

    async def _execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        await self._cursor_run(sql, params)

    async def _fetch(self, sql: str, params: Iterable[Any] = ()) -> List[Tuple[Any, ...]]:
        cursor = await self._cursor_run(sql, params)
        return list(await cursor.fetchall())

    async def _fetchval(self, sql: str, params: Iterable[Any] = ()) -> Any:
        cursor = await self._cursor_run(sql, params)
        row = await cursor.fetchone()
        return None if row is None else row[0]


def _connect_reason(exc: psycopg.OperationalError) -> str:
    text = str(exc)
    if "password authentication failed" in text:
        return "Anmeldung abgelehnt: Passwort für skytech_hems falsch"
    if "no pg_hba.conf entry" in text:
        return "Anmeldung abgelehnt: Verbindung nicht aus dem Add-on-Netz"
    if "does not exist" in text:
        return "Datenbank oder Benutzer skytech_hems fehlt – Data Insight zu alt?"
    return "Data Insight nicht erreichbar"


def _query_reason(exc: psycopg.Error) -> str:
    """Kurze Meldung ohne Parameterwerte; bei Funktionsfehlern deren deutscher Text."""
    primary = getattr(getattr(exc, "diag", None), "message_primary", None)
    if exc.sqlstate == INVALID_INPUT_SQLSTATE and primary:
        return f"Data Insight lehnt ab: {primary}"
    if isinstance(exc, psycopg.errors.InsufficientPrivilege):
        return "Data Insight verweigert den Zugriff – Vertragsversion prüfen"
    if isinstance(exc, psycopg.OperationalError):
        return "Verbindung zu Data Insight unterbrochen"
    return f"Datenbankfehler {exc.sqlstate or ''}".strip()
