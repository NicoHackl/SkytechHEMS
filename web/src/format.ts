/* Anzeigeformate. Alles, was ein Mensch liest, entsteht hier — damit dieselbe
   Zahl auf jeder Seite gleich aussieht. Datums- und Uhrzeitformate liefert das
   Add-on bereits fertig (eiserne Regel 9); hier wird nur noch gerechnet. */

/** Leistung als gerundete Zahl mit deutschem Tausenderpunkt. `null` wird zu „–". */
export function fmtNum(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '–'
  return Math.round(value).toLocaleString('de-DE')
}

/** Watt-Angabe für die Anzeige. */
export function fmtW(value: number | null | undefined): string {
  return value == null ? '–' : `${fmtNum(value)} W`
}

/** Dauer in Sekunden als „2m 5s" bzw. „45s". */
export function fmtDur(seconds: number): string {
  const total = Math.max(0, seconds)
  return total >= 60
    ? `${Math.floor(total / 60)}m ${Math.round(total % 60)}s`
    : `${Math.round(total)}s`
}

const MODE_LABELS: Record<string, string> = {
  aus: 'Aus',
  auto: 'Automatik',
  manuell: 'Manuell',
  nur_heizen: 'Nur Heizen',
  nur_laden: 'Nur Laden',
}

/** Technischer Regelmodus als lesbare deutsche Anzeige. */
export function modeLabel(mode: string | undefined): string {
  if (!mode) return '–'
  return MODE_LABELS[mode] ?? mode
}

/** Restlaufzeit bis zu einem ISO-Zeitpunkt, live tickend. */
export function untilLabel(iso: string | undefined, now: number): string {
  const target = Date.parse(iso ?? '')
  if (Number.isNaN(target)) return '–'
  const remaining = (target - now) / 1000
  return remaining <= 0 ? 'abgelaufen' : `noch ${fmtDur(remaining)}`
}
