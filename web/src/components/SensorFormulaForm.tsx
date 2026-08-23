import { useEffect, useState } from 'react'
import { api } from '../api'
import { fmtW } from '../format'
import { PageHeader } from './Layout'
import { ConfigActions, RestartOverlay } from './ConfigActions'
import { useConfigDraft } from './ConfigDraft'
import { TextAreaField } from './ConfigFields'
import { FormulaVariablesField } from './FormulaVariablesField'
import { SensorenNav } from './SensorenNav'
import { Icon } from './Icon'
import type { CycleStatus, FormulaTestResult, FormulaVariable } from '../types'

/* Formular für einen Sensoren-Tab (D-045): Zeilen (Name + HA-Entität) plus
   Code, der die Variable ueberschuss bzw. hausbilanz berechnet. Überschuss und
   Hausbilanz teilen sich diese Komponente — sie unterscheiden sich nur in
   Feldnamen, Ausgabevariable und Überschrift (dasselbe Muster wie
   KonfigurationGeraet.tsx mit mode: 'create' | 'edit'). */

interface Props {
  kind: 'residual' | 'battery_residual'
  title: string
}

const OUTPUT_NAME: Record<Props['kind'], 'ueberschuss' | 'hausbilanz'> = {
  residual: 'ueberschuss',
  battery_residual: 'hausbilanz',
}

export function SensorFormulaForm({ kind, title }: Props) {
  const { data, draft, entities, loadError, fieldErrors, restarting, ensureLoaded, patch }
    = useConfigDraft()
  const [status, setStatus] = useState<CycleStatus | null>(null)
  const [testing, setTesting] = useState(false)
  const [testError, setTestError] = useState('')
  const [testResult, setTestResult] = useState<FormulaTestResult | null>(null)

  useEffect(ensureLoaded, [ensureLoaded])

  // Einmaliger Schnappschuss, nicht die Live-Kachel der Status-Seite: es geht
  // hier nur darum, welche Quelle beim letzten Zyklus wirkte, nicht um Polling.
  useEffect(() => {
    void (async () => {
      try {
        const response = await api.status()
        if ('ems_enabled' in response.status) setStatus(response.status as CycleStatus)
      } catch {
        /* Ohne Status bleibt das Formular vollständig bedienbar. */
      }
    })()
  }, [])

  if (!data || !draft) {
    return (
      <>
        <PageHeader title="Sensoren" subtitle={title} />
        <div className="content form-content">
          {loadError
            ? <div className="alert">Konfiguration nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  const outputName = OUTPUT_NAME[kind]
  const variables = kind === 'residual' ? draft.residual_formula_variables : draft.battery_residual_formula_variables
  const code = kind === 'residual' ? draft.residual_formula_code : draft.battery_residual_formula_code
  const configuredEntity = kind === 'residual' ? draft.residual_power_entity : draft.battery_residual_power_entity
  const source = kind === 'residual' ? status?.residual_source : status?.battery_residual_source
  const variablesKey = kind === 'residual' ? 'residual_formula_variables' : 'battery_residual_formula_variables'
  const codeKey = kind === 'residual' ? 'residual_formula_code' : 'battery_residual_formula_code'

  const setVariables = (next: FormulaVariable[]) => patch({ [variablesKey]: next })
  const setCode = (next: string) => patch({ [codeKey]: next })

  const runTest = async () => {
    setTesting(true)
    setTestError('')
    try {
      setTestResult(await api.testSensorFormula(kind, variables, code))
    } catch (error) {
      setTestResult(null)
      setTestError((error as Error).message)
    } finally {
      setTesting(false)
    }
  }

  return (
    <>
      <PageHeader title="Sensoren" subtitle={title} />
      {restarting ? <RestartOverlay /> : null}

      <div className="content form-content">
        <SensorenNav />

        <section className="card">
          <div className="card-head"><h2>Variablen</h2></div>
          <div className="card-body">
            <FormulaVariablesField
              variables={variables} entities={entities} fieldErrors={fieldErrors}
              pathPrefix={variablesKey} onChange={setVariables}
            />
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>Formel</h2>
            <div className="spacer" />
            {source ? <QuellenPill quelle={source} entitaet={configuredEntity} /> : null}
          </div>
          <div className="card-body">
            <TextAreaField
              label={`Code (weist "${outputName}" einen Wert zu)`}
              value={code}
              error={fieldErrors[codeKey]}
              hint={variables.length
                ? `Verfügbare Namen: ${variables.map((v) => v.name || '?').join(', ')} `
                  + `(je mit einer Begleitvariable <name>_valid). Leer lassen, um die oben unter `
                  + `Konfiguration eingetragene Entität zu verwenden.`
                : `Ohne Variablen kann der Code nur mit Zahlen rechnen. Leer lassen, um die oben `
                  + `unter Konfiguration eingetragene Entität zu verwenden.`}
              placeholder={`${outputName} = ...`}
              onChange={setCode}
            />

            <button type="button" className="btn btn-ghost btn-sm" disabled={testing || !code.trim()}
                    onClick={() => void runTest()}>
              <Icon name="spark" size={16} />{testing ? 'Testen…' : 'Testen'}
            </button>

            {testError ? <div className="alert">{testError}</div> : null}
            {testResult ? <TestErgebnis ergebnis={testResult} /> : null}
          </div>
        </section>

        <ConfigActions />
      </div>
    </>
  )
}

/** Welche Quelle gerade wirkt (D-041: Vorrang muss sichtbar sein, nicht nur im Log). */
function QuellenPill({ quelle, entitaet }: { quelle: string; entitaet: string }) {
  if (quelle === 'formula') {
    return <span className="pill primary"><Icon name="check" size={13} />Aktuell wirksam: Formel</span>
  }
  if (quelle === 'ha') {
    return <span className="pill">Aktuell wirksam: {entitaet || 'keine Entität konfiguriert'}</span>
  }
  return <span className="pill warn">Aktuell kein gültiger Wert</span>
}

function TestErgebnis({ ergebnis }: { ergebnis: FormulaTestResult }) {
  if (!ergebnis.valid) {
    return (
      <div className="alert">
        {ergebnis.error}
        {ergebnis.error_line != null ? ` (Zeile ${ergebnis.error_line})` : ''}
      </div>
    )
  }
  return (
    <div className="hint-box">
      <p><span className="pill ok">Gültig</span> Ergebnis: <b>{fmtW(ergebnis.value ?? 0)}</b></p>
      {ergebnis.variables.map((variable) => (
        <div className="kv-row" key={variable.name}>
          <span className="k">{variable.name} ({variable.entity})</span>
          <span className={`v ${variable.valid ? 'ok' : 'err'}`}>
            {variable.valid ? fmtW(variable.value ?? 0) : `ungültig (${variable.state})`}
          </span>
        </div>
      ))}
    </div>
  )
}
