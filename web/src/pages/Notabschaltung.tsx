import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { ConfigActions, RestartOverlay } from '../components/ConfigActions'
import { useConfigDraft } from '../components/ConfigDraft'
import { EntityField, SelectField, TextField } from '../components/ConfigFields'
import { EmergencyTargetsField } from '../components/EmergencyTargetsField'
import { KeyValue } from '../components/DeviceCard'
import type { EmergencyCondition, EmergencyStatus } from '../types'

/* Notabschaltung (D-059): Auslösebedingung und Zielzustände.

   Teilt den Entwurf der Konfigurationsseiten — gespeichert wird über die
   Add-on-Optionen und wirksam nach „Speichern und neu starten". Die
   Live-Prüfung arbeitet dagegen auf dem ENTWURF: sie zeigt schon vor dem
   Speichern, ob die eingetragene Bedingung gerade zutreffen würde. */

const POLL_MS = 5000
const DEBOUNCE_MS = 400

/** Domains, deren Zustand sich als Bedingung eignet. */
const CONDITION_DOMAINS = [
  'binary_sensor', 'sensor', 'switch', 'input_boolean', 'input_select', 'select',
  'input_number', 'number', 'light', 'fan',
]

const CONDITION_LABELS: Record<EmergencyCondition['state'], string> = {
  met: 'trifft zu – würde auslösen',
  not_met: 'trifft nicht zu',
  invalid: 'nicht prüfbar – löst nicht aus',
}
const CONDITION_TONES = { met: 'err', not_met: 'ok', invalid: 'warn' } as const

export function Notabschaltung() {
  const { data, draft, entities, loadError, fieldErrors, restarting, ensureLoaded, patch }
    = useConfigDraft()
  const [status, setStatus] = useState<EmergencyStatus | null>(null)
  const [live, setLive] = useState<EmergencyCondition | null>(null)
  const [liveError, setLiveError] = useState('')

  useEffect(ensureLoaded, [ensureLoaded])

  // Laufender Zustand der GESPEICHERTEN Konfiguration.
  useEffect(() => {
    const load = async () => {
      try {
        setStatus((await api.status()).emergency ?? null)
      } catch {
        /* Ohne Status bleibt das Formular vollständig bedienbar. */
      }
    }
    void load()
    const timer = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(timer)
  }, [])

  // Live-Prüfung des Entwurfs: entprellt nach jeder Änderung, danach im Takt.
  const entity = draft?.emergency_condition_entity ?? ''
  const operator = draft?.emergency_condition_operator ?? ''
  const value = draft?.emergency_condition_value ?? ''
  useEffect(() => {
    if (!entity) {
      setLive(null)
      setLiveError('')
      return
    }
    let cancelled = false
    const check = async () => {
      try {
        const result = await api.emergencyTest(entity, operator, value)
        if (!cancelled) { setLive(result); setLiveError('') }
      } catch (error) {
        if (!cancelled) { setLive(null); setLiveError((error as Error).message) }
      }
    }
    const first = window.setTimeout(() => void check(), DEBOUNCE_MS)
    const timer = window.setInterval(() => void check(), POLL_MS)
    return () => {
      cancelled = true
      window.clearTimeout(first)
      window.clearInterval(timer)
    }
  }, [entity, operator, value])

  if (!data || !draft) {
    return (
      <>
        <PageHeader title="Notabschaltung" subtitle="Auslösebedingung und Zielzustände" />
        <div className="content form-content">
          {loadError
            ? <div className="alert">Konfiguration nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  const operators = data.supported.emergency_operators
  const operatorLabels = Object.fromEntries(operators.map((op) => [op.value, op.label]))

  return (
    <>
      <PageHeader title="Notabschaltung" subtitle="Auslösebedingung und Zielzustände" />
      {restarting ? <RestartOverlay /> : null}

      <div className="content form-content">
        {status?.config_error ? <div className="alert">{status.config_error}</div> : null}
        {status?.file_error ? <div className="alert">{status.file_error}</div> : null}

        <section className="card">
          <div className="card-head">
            <h2>Zustand</h2>
            <div className="spacer" />
            {status ? <ZustandPill status={status} /> : null}
          </div>
          <div className="card-body">
            {status?.active ? (
              <p className="hint-box">
                Aktiv seit {status.since || 'unbekannt'}. Quittiert wird im Tab{' '}
                <Link to="/">Status</Link>, sobald die Bedingung nicht mehr zutrifft.
              </p>
            ) : null}
            <KeyValue
              label="Wirksame Bedingung"
              value={status?.configured
                ? <span className="mono">{status.condition_entity} {status.condition_operator_label} {status.condition_value}</span>
                : 'keine – Notabschaltung aus'}
              tone={status?.configured ? 'plain' : 'muted'}
            />
            {status?.configured && status.condition ? (
              <KeyValue
                label="Letzte Prüfung"
                value={`${CONDITION_LABELS[status.condition.state]} · ${status.condition.reason}`}
                tone={CONDITION_TONES[status.condition.state]}
              />
            ) : null}
            <KeyValue label="Anzeige-Sensor" value={<span className="mono">{status?.sensor_entity ?? ''}</span>} tone="muted" />
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Auslösebedingung</h2></div>
          <div className="card-body">
            <div className="form-grid">
              <EntityField
                label="Entität" wide
                value={entity} entities={entities} domains={CONDITION_DOMAINS}
                error={fieldErrors.emergency_condition_entity}
                hint="Wird jede Sekunde geprüft. Leer lassen = Notabschaltung aus."
                onChange={(next) => patch({ emergency_condition_entity: next })}
              />
              <SelectField
                label="Operator" required
                value={operator} options={operators.map((op) => op.value)} labels={operatorLabels}
                error={fieldErrors.emergency_condition_operator}
                hint="≥, >, ≤ und < vergleichen nur Zahlen."
                onChange={(next) => patch({ emergency_condition_operator: next })}
              />
              <TextField
                label="Sollwert" required mono
                value={value} placeholder="z. B. off"
                error={fieldErrors.emergency_condition_value}
                hint="Text ohne Groß-/Kleinschreibung, Zahlen numerisch."
                onChange={(next) => patch({ emergency_condition_value: next })}
              />
            </div>

            {entity ? (
              <>
                {liveError ? <div className="alert">Live-Prüfung fehlgeschlagen: {liveError}</div> : null}
                {live ? (
                  <>
                    <KeyValue label="Aktueller Wert" value={live.current ?? '–'} />
                    <KeyValue label="Ergebnis (Entwurf)" value={CONDITION_LABELS[live.state]}
                              tone={CONDITION_TONES[live.state]} />
                    {live.state === 'invalid' ? <KeyValue label="Grund" value={live.reason} tone="warn" /> : null}
                  </>
                ) : null}
              </>
            ) : null}

            <p className="hint-box">
              Meldet die Entität <span className="mono">unavailable</span> oder{' '}
              <span className="mono">unknown</span> oder fehlt sie, löst die Notabschaltung bewusst
              nicht aus — sonst stünde sie nach jedem Neustart von Home Assistant an.
            </p>
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Zielzustände bei Notabschaltung</h2></div>
          <div className="card-body">
            <p className="hint-box">
              Beim Auslösen gehen zuerst alle HEMS-Geräte sofort auf 0 W bzw. aus, ohne Zeitschutz
              und ohne Ausnahme. Danach läuft das Post-Cycle-Skript, danach diese Zeilen von oben
              nach unten — hier gehört hin, was Geräte zurück in ihre eigene Automatik schickt.
              Automationen, die HEMS-Helfer an echte Geräte weiterreichen, sollten{' '}
              <span className="mono">{status?.sensor_entity ?? 'sensor.ems_notabschaltung_aktiv'}</span>{' '}
              als Bedingung prüfen.
            </p>
            <EmergencyTargetsField
              targets={draft.emergency_targets} entities={entities}
              kinds={data.supported.emergency_target_kinds} fieldErrors={fieldErrors}
              onChange={(next) => patch({ emergency_targets: next })}
            />
          </div>
        </section>

        <ConfigActions />
      </div>
    </>
  )
}

function ZustandPill({ status }: { status: EmergencyStatus }) {
  if (status.active) return <span className="pill err">Notabschaltung aktiv</span>
  if (!status.configured) return <span className="pill muted">Aus</span>
  if (status.condition?.state === 'invalid') return <span className="pill warn">Bedingung nicht prüfbar</span>
  return <span className="pill ok">Überwachung aktiv</span>
}
