import { EnergyPilotPage, useEnergyPilot } from '../components/EnergyPilotShared'
import { Icon } from '../components/Icon'
import { modeLabel, untilLabel } from '../format'
import type { HaEntity } from '../types'

/* Übersicht des Energy Pilot: Plan-Status und Verbindung zum HEMS. Reine Anzeige. */

export function EnergyPilotUebersicht() {
  const { states, loadError, updatedAt, now } = useEnergyPilot()

  return (
    <EnergyPilotPage subtitle="Plan-Status und Verbindung" states={states} loadError={loadError} updatedAt={updatedAt}>
      {(loaded) => (
        <>
          <div className="info-strip">
            <Icon name="info" size={16} />
            <span>Reine Anzeige. Ob die Vorschläge wirken, entscheidet der Regelmodus — siehe Steuerung.</span>
          </div>

          <div className="section-title"><Icon name="spark" size={14} />Plan-Status</div>
          <div className="pill-row">{planPills(loaded['sensor.ep_plan_status'], now)}</div>

          <div className="section-title"><Icon name="refresh" size={14} />Energy Pilot ↔ HEMS</div>
          <div className="pill-row">{connectionPills(loaded['sensor.ep_hems_verbindung'])}</div>
        </>
      )}
    </EnergyPilotPage>
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
