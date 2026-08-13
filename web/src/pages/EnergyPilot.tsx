import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { DeviceCard, KeyValue, type CardState, type ValueTone } from '../components/DeviceCard'
import { Icon } from '../components/Icon'
import { modeLabel, untilLabel } from '../format'
import type { HaEntities, HaEntity } from '../types'

/* Reine Anzeige der Energy-Pilot-Daten.

   Der Energy Pilot schreibt seine Vorschläge und Statuswerte als
   sensor.ep_*-Entitäten nach Home Assistant; HEMS liest sie über /api/ep und
   spiegelt sie hier. Die eigentliche Übernahme passiert im Regelzyklus
   (Regelmodus = auto), nicht auf dieser Seite. */

const REFRESH_MS = 10000

export function EnergyPilot() {
  const [states, setStates] = useState<HaEntities | null>(null)
  const [loadError, setLoadError] = useState('')
  const [updatedAt, setUpdatedAt] = useState('')
  /* Sekündlich hochgezählt, damit die Restgültigkeit des Plans tickt, statt
     bis zum nächsten Abruf einzufrieren. */
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(async () => {
    try {
      setStates(await api.energyPilot())
      setUpdatedAt(new Date().toLocaleTimeString('de-DE'))
      setLoadError('')
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [load])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  if (!states) {
    return (
      <>
        <PageHeader title="Energy Pilot" subtitle="Vorschläge und Plan-Status" />
        <div className="content">
          {loadError
            ? <div className="alert">Energy-Pilot-Daten nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  const plan = states['sensor.ep_plan_status']
  const connection = states['sensor.ep_hems_verbindung']
  const groups = groupSuggestions(states, now)

  return (
    <>
      <PageHeader title="Energy Pilot" subtitle="Vorschläge und Plan-Status" />

      <div className="content">
        {loadError ? <div className="alert">Aktualisierung fehlgeschlagen: {loadError}</div> : null}

        <div className="info-strip">
          <Icon name="info" size={16} />
          <span>Reine Anzeige. Ob die Vorschläge wirken, entscheidet der Regelmodus — siehe Steuerung.</span>
        </div>

        <div className="section-title"><Icon name="spark" size={14} />Plan-Status</div>
        <div className="pill-row">{planPills(plan, now)}</div>

        <div className="section-title"><Icon name="refresh" size={14} />Energy Pilot ↔ HEMS</div>
        <div className="pill-row">{connectionPills(connection)}</div>

        <div className="section-title"><Icon name="sliders" size={14} />Vorschläge je Gerät</div>
        {groups.length ? (
          <div className="device-grid">
            {groups.map((group) => {
              const release = group.fields.find((field) => field.label.toLowerCase().includes('freigabe'))
              const state: CardState = !release ? 'idle' : release.state === 'on' ? 'active' : 'off'
              return (
                <DeviceCard key={group.device} title={group.device} state={state}>
                  {group.fields.map((field) => {
                    const shown = displayValue(field.state, field.unit)
                    return <KeyValue key={field.label} label={field.label} value={shown.text} tone={shown.tone} />
                  })}
                </DeviceCard>
              )
            })}
          </div>
        ) : (
          <div className="card">
            <div className="empty">
              <Icon name="spark" size={40} />
              <p>Keine gültigen Vorschläge gefunden.</p>
              <span>Der Energy Pilot veröffentlicht sie als <code>sensor.ep_…_vorschlag</code>.</span>
            </div>
          </div>
        )}

        <div className="meta-line">{updatedAt ? `Aktualisiert: ${updatedAt}` : 'Warte auf Daten…'}</div>
      </div>
    </>
  )
}

const PLAN_LABELS: Record<string, string> = {
  kein_plan: 'Kein Plan',
  unbekannt: 'Unbekannt',
  beobachtet_konform: 'Beobachtet konform',
  beobachtet_abweichend: 'Beobachtet abweichend',
}

function planTone(state: string): string {
  if (state === 'beobachtet_konform') return 'ok'
  if (state === 'beobachtet_abweichend') return 'warn'
  return 'muted'
}

function planPills(plan: HaEntity | undefined, now: number) {
  if (!plan) return <span className="pill muted">Kein Plan-Status</span>

  const attributes = plan.attributes
  const label = attributes.label || PLAN_LABELS[plan.state] || plan.state || 'Unbekannt'
  const deviations = Array.isArray(attributes.abweichungen) ? attributes.abweichungen : []

  return (
    <>
      <span className={`pill ${planTone(plan.state)}`}>Plan: {label}</span>
      {attributes.valid_until
        ? <span className="pill primary">Gültig {untilLabel(attributes.valid_until, now)}</span>
        : null}
      <span className={attributes.in_window ? 'pill ok' : 'pill muted'}>
        {attributes.in_window ? 'Im Zeitfenster' : 'Außerhalb Zeitfenster'}
      </span>
      {deviations.length
        ? deviations.map((deviation) => <span className="pill warn" key={deviation}>Abweichung: {deviation}</span>)
        : <span className="pill ok">Keine Abweichungen</span>}
    </>
  )
}

function connectionPills(connection: HaEntity | undefined) {
  if (!connection) return <span className="pill muted">Keine Verbindungsdaten</span>

  const attributes = connection.attributes
  const online = connection.state === 'online'

  return (
    <>
      <span className={online ? 'pill ok' : 'pill err'}>{online ? 'Energy Pilot online' : 'Energy Pilot offline'}</span>
      {attributes.last_cycle_at ? <span className="pill">Letzter Zyklus: {attributes.last_cycle_at}</span> : null}
      {attributes.cycle_count != null ? <span className="pill">Zyklen: {attributes.cycle_count}</span> : null}
      {attributes.global_mode ? <span className="pill primary">Modus: {modeLabel(attributes.global_mode)}</span> : null}
      {attributes.error ? <span className="pill err">Fehler: {attributes.error}</span> : null}
    </>
  )
}

function displayValue(state: string, unit: string | undefined): { text: string; tone: ValueTone } {
  if (!state || state === 'unavailable' || state === 'unknown') return { text: '–', tone: 'muted' }
  if (state === 'on') return { text: 'Ja', tone: 'ok' }
  if (state === 'off') return { text: 'Nein', tone: 'err' }
  return { text: unit ? `${state} ${unit}` : state, tone: 'plain' }
}

interface SuggestionField {
  label: string
  state: string
  unit?: string
  validUntil: number
}

interface SuggestionGroup {
  device: string
  fields: SuggestionField[]
}

/** Reihenfolge der Felder: Freigabe zuerst, dann Priorität, dann alphabetisch. */
function fieldWeight(label: string): number {
  const lower = label.toLowerCase()
  if (lower.includes('freigabe')) return 0
  if (lower.includes('priorität')) return 1
  return 2
}

/**
 * Gruppiert die Vorschlags-Sensoren je Gerät über den Anzeigenamen-Präfix
 * („Gerät – Feld (Vorschlag)"), statt die entity_id zu zerlegen.
 *
 * Verwaiste Vorschläge: HEMS spiegelt nur und löscht keine HA-Entitäten. Wird im
 * Energy Pilot ein Quellsensor getauscht, entsteht eine NEUE entity_id, während
 * die alte mit eingefrorenem Wert stehen bleibt (gleicher Anzeigename, doppeltes
 * Feld). Zwei Filter, ohne Kopplung an die Publish-Reihenfolge:
 *   1. abgelaufene Vorschläge (valid_until in der Vergangenheit) ausblenden —
 *      die verwaiste Entität friert ihr valid_until ein und läuft dauerhaft ab;
 *   2. bei doppeltem Feld je Gerät nur den frischeren behalten (späteres
 *      valid_until) — das dedupliziert einen Sensortausch sofort.
 */
function groupSuggestions(states: HaEntities, now: number): SuggestionGroup[] {
  const grouped: Record<string, Record<string, SuggestionField>> = {}

  for (const [entityId, entity] of Object.entries(states)) {
    if (!entityId.endsWith('_vorschlag')) continue

    const validUntil = Date.parse(entity.attributes.valid_until ?? '')
    if (!Number.isNaN(validUntil) && validUntil < now) continue // (1) abgelaufen/verwaist

    const friendlyName = entity.attributes.friendly_name || entityId
    const separator = friendlyName.indexOf(' – ')
    const device = separator >= 0 ? friendlyName.slice(0, separator) : friendlyName
    const field = (separator >= 0 ? friendlyName.slice(separator + 3) : friendlyName)
      .replace(/\s*\(Vorschlag\)\s*$/, '')

    const candidate: SuggestionField = {
      label: field,
      state: entity.state,
      unit: entity.attributes.unit_of_measurement,
      validUntil: Number.isNaN(validUntil) ? 0 : validUntil,
    }

    const fields = grouped[device] ?? (grouped[device] = {})
    const existing = fields[field]
    if (!existing || candidate.validUntil >= existing.validUntil) fields[field] = candidate // (2)
  }

  return Object.keys(grouped)
    .sort((a, b) => a.localeCompare(b, 'de'))
    .map((device) => ({
      device,
      fields: Object.values(grouped[device]).sort(
        (a, b) => fieldWeight(a.label) - fieldWeight(b.label) || a.label.localeCompare(b.label, 'de'),
      ),
    }))
}
