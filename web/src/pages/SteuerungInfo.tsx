import { useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { Icon } from '../components/Icon'
import { useToast } from '../components/Toast'
import {
  HELPER_STATE_LABEL, SOURCE_LABEL, SOURCE_TITLE, formatControlValue, helperState, useControlData, writeTarget,
  type HelperState, type WriteTarget,
} from '../components/ControlSource'
import type { ControlGroup, ControlItem, EntityDiagnostic, HaEntities } from '../types'

/* Steuerung Info (D-061): je Helferwert, ob er wirklich aus Home Assistant kommt
   und dorthin geschrieben wird, oder ob er nur im HEMS existiert.

   Reine Anzeige; eingestellt wird im Tab „Steuerung". Einzige Aktion ist das
   Löschen verwaister interner Werte, die zu keinem konfigurierten Helfer mehr
   gehören — sie wirken nicht, wären aber sonst nirgends mehr sichtbar. */

const REFRESH_MS = 15000

const HELPER_PILL: Record<HelperState, string> = {
  valid: 'ok',
  missing: 'muted',
  unavailable: 'warn',
  invalid: 'warn',
}

const SOURCE_PILL: Record<EntityDiagnostic['source'], string> = {
  ha: 'ok',
  hems: 'primary',
  addon: 'warn',
  internal: 'warn',
}

const TARGET_LABEL: Record<WriteTarget, string> = {
  ha: 'HA-Helfer',
  hems: 'HEMS-intern',
  none: 'nicht einstellbar',
}

interface Row {
  item: ControlItem
  helper: HelperState
  source: EntityDiagnostic['source']
  value: unknown
  target: WriteTarget
  internalValue: unknown
}

function buildRows(group: ControlGroup, states: HaEntities, diagnostics: Record<string, EntityDiagnostic>,
                   internalValues: Record<string, unknown>): Row[] {
  return group.items.map((item) => {
    const entity = states[item.entity]
    const diagnostic = diagnostics[item.entity]
    const helper = helperState(entity, diagnostic)
    // Ohne Zyklusdiagnose (z. B. direkt nach dem Start) zählt der Helferzustand.
    const source = diagnostic?.source ?? (helper === 'valid' ? 'ha' : 'internal')
    const value = diagnostic && 'value' in diagnostic ? diagnostic.value : entity?.state
    return {
      item, helper, source, value,
      target: writeTarget(item, entity, diagnostic),
      internalValue: internalValues[item.entity],
    }
  })
}

export function SteuerungInfo() {
  const { schema, states, diagnostics, internal, loadError, updatedAt, load } = useControlData(REFRESH_MS)
  const { toast } = useToast()

  const reset = useCallback(async (entityId: string) => {
    try {
      await api.resetInternalValue(entityId)
      await load()
      toast('Interner Wert gelöscht.')
    } catch (error) {
      toast(`Löschen fehlgeschlagen: ${(error as Error).message}`, 'err')
    }
  }, [load, toast])

  const header = <PageHeader title="Steuerung Info" subtitle="Woher die Steuerwerte kommen und wohin sie geschrieben werden" />

  if (!schema || !states) {
    return (
      <>
        {header}
        <div className="content">
          {loadError
            ? <div className="alert">Steuerdaten nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  const groups = schema.map((group) => ({ group, rows: buildRows(group, states, diagnostics, internal.values) }))
  const allRows = groups.flatMap(({ rows }) => rows)
  const fromHa = allRows.filter((row) => row.source === 'ha').length
  const fromHems = allRows.filter((row) => row.source === 'hems').length
  const fallback = allRows.length - fromHa - fromHems
  const known = new Set(allRows.map((row) => row.item.entity))
  const orphaned = Object.entries(internal.values).filter(([entityId]) => !known.has(entityId))

  return (
    <>
      {header}

      <div className="content">
        {loadError ? <div className="alert">Aktualisierung fehlgeschlagen: {loadError}</div> : null}
        {internal.file_error ? <div className="alert">{internal.file_error}</div> : null}

        <div className="info-strip">
          <Icon name="info" size={16} />
          <span>
            Reihenfolge: gültiger HA-Helfer → im HEMS eingegebener Wert → Add-on-Wert → Default.
            Freigaben und Zwang gibt es nur als HA-Helfer. Eingestellt wird unter <Link to="/steuerung">Steuerung</Link>.
          </span>
        </div>

        <div className="pill-row">
          <span className="pill ok">{fromHa} aus HA-Helfern</span>
          <span className="pill primary">{fromHems} nur HEMS-intern</span>
          <span className={`pill ${fallback ? 'warn' : 'muted'}`}>{fallback} Add-on-Wert oder Default</span>
        </div>

        {groups.map(({ group, rows }, index) => (
          <div className="card" key={group.name ?? `${group.label}-${index}`}>
            <div className="card-head"><h2>{group.label}</h2></div>
            <div className="table-wrap">
              <table className="data readonly">
                <thead>
                  <tr>
                    <th>Wert</th>
                    <th>HA-Helfer</th>
                    <th>Wirksame Quelle</th>
                    <th>Wirksamer Wert</th>
                    <th>Steuerung schreibt nach</th>
                    <th>Im HEMS gespeichert</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.item.entity}>
                      <td>
                        <span className="cell-title">{row.item.label}</span>
                        <span className="cell-sub mono">{row.item.entity}</span>
                      </td>
                      <td><span className={`pill ${HELPER_PILL[row.helper]}`}>{HELPER_STATE_LABEL[row.helper]}</span></td>
                      <td>
                        <span className={`pill ${SOURCE_PILL[row.source]}`} title={SOURCE_TITLE[row.source]}>
                          {SOURCE_LABEL[row.source]}
                        </span>
                      </td>
                      <td>{formatControlValue(row.item, row.value)}</td>
                      <td>
                        {TARGET_LABEL[row.target]}
                        {row.item.internal_editable ? null : <span className="cell-sub">nur über HA-Helfer</span>}
                      </td>
                      <td>{row.internalValue === undefined ? '–' : formatControlValue(row.item, row.internalValue)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}

        {orphaned.length ? (
          <div className="card">
            <div className="card-head">
              <h2>Verwaiste interne Werte</h2>
              <div className="sub">Gehören zu keinem konfigurierten Helfer mehr und wirken nicht.</div>
            </div>
            <div className="table-wrap">
              <table className="data readonly">
                <thead><tr><th>Entität</th><th>Wert</th><th /></tr></thead>
                <tbody>
                  {orphaned.map(([entityId, value]) => (
                    <tr key={entityId}>
                      <td className="mono">{entityId}</td>
                      <td>{String(value)}</td>
                      <td>
                        <div className="row-actions">
                          <button type="button" className="btn btn-danger btn-sm" onClick={() => void reset(entityId)}>
                            Löschen
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        <div className="meta-line">{updatedAt ? `Aktualisiert: ${updatedAt}` : 'Warte auf Daten…'}</div>
      </div>
    </>
  )
}
