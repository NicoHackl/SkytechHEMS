import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { Icon } from '../components/Icon'
import { useToast } from '../components/Toast'
import {
  SOURCE_LABEL, SOURCE_TITLE, useControlData, writeTarget,
  type InternalValue, type WriteTarget,
} from '../components/ControlSource'
import type { ControlItem, EntityDiagnostic, HaEntity } from '../types'

/* Alle EMS-Helfer je Gerät und global, direkt einstellbar.

   Das Schema kommt aus /api/device_controls_schema und wird einmal geladen —
   es ändert sich nur, wenn die Add-on-Konfiguration geändert und das Add-on neu
   gestartet wird. Die Werte kommen aus /api/controls und werden alle 15 s
   aufgefrischt.

   Fehlt ein Helfer, ist er ausgefallen oder ungültig, lässt sich der Wert hier
   direkt im HEMS eingeben (D-061) — ausgenommen Freigaben und Zwang. Wohin eine
   Änderung geht, steht ausführlich im Tab „Steuerung Info". */

const REFRESH_MS = 15000
const DEBOUNCE_MS = 700

export function Steuerung() {
  const { schema, states, diagnostics, internal, loadError, updatedAt, load } = useControlData(REFRESH_MS)
  /* Lokal geänderte, noch nicht bestätigte Werte. Ohne sie würde die
     Auffrischung eine laufende Eingabe überschreiben. */
  const [edits, setEdits] = useState<Record<string, string>>({})
  const timers = useRef<Record<string, number>>({})
  const { toast } = useToast()

  // Offene Debounce-Timer beim Verlassen der Seite abräumen.
  useEffect(() => {
    const pending = timers.current
    return () => Object.values(pending).forEach((id) => window.clearTimeout(id))
  }, [])

  const save = useCallback(async (entityId: string, target: WriteTarget, value: InternalValue) => {
    window.clearTimeout(timers.current[entityId])
    delete timers.current[entityId]
    try {
      if (target === 'hems') await api.setInternalValue(entityId, value)
      else await api.setEntity(entityId, value)
      await load()
      setEdits((current) => {
        const next = { ...current }
        delete next[entityId]
        return next
      })
      toast(target === 'hems' ? 'Im HEMS gespeichert.' : 'Gespeichert.')
    } catch (error) {
      // Der lokale Wert bleibt stehen, damit die Eingabe nicht verlorengeht.
      toast(`Speichern fehlgeschlagen: ${(error as Error).message}`, 'err')
    }
  }, [load, toast])

  const reset = useCallback(async (entityId: string) => {
    try {
      await api.resetInternalValue(entityId)
      await load()
      setEdits((current) => {
        const next = { ...current }
        delete next[entityId]
        return next
      })
      toast('Interner Wert gelöscht.')
    } catch (error) {
      toast(`Zurücksetzen fehlgeschlagen: ${(error as Error).message}`, 'err')
    }
  }, [load, toast])

  const scheduleSave = useCallback((entityId: string, target: WriteTarget, value: string) => {
    setEdits((current) => ({ ...current, [entityId]: value }))
    window.clearTimeout(timers.current[entityId])
    timers.current[entityId] = window.setTimeout(() => {
      const parsed = Number.parseFloat(value)
      if (Number.isNaN(parsed)) return
      void save(entityId, target, parsed)
    }, DEBOUNCE_MS)
  }, [save])

  if (!schema || !states) {
    return (
      <>
        <PageHeader title="Steuerung" subtitle="Helfer-Entitäten des EMS" />
        <div className="content">
          {loadError
            ? <div className="alert">Steuerdaten nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader title="Steuerung" subtitle="Helfer-Entitäten des EMS" />

      <div className="content">
        {loadError ? <div className="alert">Aktualisierung fehlgeschlagen: {loadError}</div> : null}
        {internal.file_error ? <div className="alert">{internal.file_error}</div> : null}

        <div className="info-strip">
          <Icon name="info" size={16} />
          <span>
            Änderungen wirken auf den nächsten Regelzyklus. Vorhandene Home-Assistant-Helfer werden
            dort geschrieben; fehlt ein Helfer, wird der Wert im HEMS gespeichert.
          </span>
        </div>

        {schema.length ? (
          <div className="device-grid">
            {schema.map((group, index) => (
              <details className="card ctrl-group" key={group.name ?? `${group.label}-${index}`} open>
                <summary>{group.label}</summary>
                <div className="card-body">
                  {group.items.map((item) => {
                    const entity = states[item.entity]
                    const diagnostic = diagnostics[item.entity]
                    const target = writeTarget(item, entity, diagnostic)
                    return (
                      <ControlRow
                        key={item.entity}
                        item={item}
                        entity={entity}
                        diagnostic={diagnostic}
                        target={target}
                        internalValue={internal.values[item.entity]}
                        edit={edits[item.entity]}
                        onChange={(value) => void save(item.entity, target, value)}
                        onNumberInput={(value) => scheduleSave(item.entity, target, value)}
                        onReset={() => void reset(item.entity)}
                      />
                    )
                  })}
                </div>
              </details>
            ))}
          </div>
        ) : (
          <div className="card"><div className="empty">Keine Geräte konfiguriert.</div></div>
        )}

        <div className="meta-line">{updatedAt ? `Aktualisiert: ${updatedAt}` : 'Warte auf Daten…'}</div>
      </div>
    </>
  )
}

function ControlRow({
  item,
  entity,
  diagnostic,
  target,
  internalValue,
  edit,
  onChange,
  onNumberInput,
  onReset,
}: {
  item: ControlItem
  entity: HaEntity | undefined
  diagnostic: EntityDiagnostic | undefined
  target: WriteTarget
  internalValue: InternalValue | undefined
  edit: string | undefined
  onChange: (value: InternalValue) => void
  onNumberInput: (value: string) => void
  onReset: () => void
}) {
  const domain = item.entity.split('.')[0]
  const kind = item.kind && item.kind !== 'auto'
    ? item.kind
    : ({ input_boolean: 'bool', input_number: 'number', input_select: 'select' } as const)[domain]

  /* Was der Editor anzeigt: beim Helfer dessen State, sonst der intern
     gespeicherte Wert und ohne ihn der gerade wirksame Ersatzwert. */
  const current: unknown = target === 'hems'
    ? (internalValue ?? diagnostic?.value)
    : entity?.state
  const options = target === 'hems' ? (item.options ?? []) : (entity?.attributes.options ?? [])
  const min = target === 'hems' ? item.min : entity?.attributes.min
  const max = target === 'hems' ? item.max : entity?.attributes.max
  const step = target === 'hems' ? (item.integer ? 1 : item.step) : entity?.attributes.step
  const unit = target === 'hems' ? item.unit : entity?.attributes.unit_of_measurement
  const checked = current === true || current === 'on'
  const numeric = current === null || current === undefined ? '' : String(current)

  return (
    <div className="ctrl-row">
      <span className="k">{item.label}</span>
      <div className="ctrl-value">
        <SourceHint target={target} diagnostic={diagnostic} internalSet={internalValue !== undefined} />
        {target === 'none' ? (
          <span className="ctrl-missing">Helfer nicht gefunden</span>
        ) : kind === 'bool' ? (
          <label className="switch">
            <input
              type="checkbox"
              checked={checked}
              onChange={(event) => onChange(event.target.checked)}
              aria-label={item.label}
            />
            <span className="track" />
            <span className="switch-label">{checked ? 'An' : 'Aus'}</span>
          </label>
        ) : kind === 'number' ? (
          <>
            <input
              type="number"
              value={edit ?? numeric}
              min={min}
              max={max}
              step={step ?? 1}
              onChange={(event) => onNumberInput(event.target.value)}
              onBlur={(event) => {
                // Nur schreiben, wenn sich der Wert wirklich unterscheidet — ein
                // erneuter Write setzt last_changed zurück und stört das Rampen-Timing.
                const next = Number.parseFloat(event.target.value)
                if (!Number.isNaN(next) && next !== Number.parseFloat(numeric)) onChange(next)
              }}
              aria-label={item.label}
            />
            {unit ? <span className="ctrl-unit">{unit}</span> : null}
          </>
        ) : kind === 'select' ? (
          <select value={String(current ?? '')} onChange={(event) => onChange(event.target.value)} aria-label={item.label}>
            {/* Ohne gültigen Wert keine stille Vorauswahl: der leere Eintrag zeigt das. */}
            {options.includes(String(current ?? '')) ? null : <option value="">–</option>}
            {options.map((option) => (
              <option value={option} key={option}>{option}</option>
            ))}
          </select>
        ) : (
          <span className="ctrl-missing">{String(current ?? '–')}</span>
        )}
        {target === 'hems' && internalValue !== undefined ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onReset}
                  title="Internen Wert löschen – danach greift wieder der Add-on-Wert bzw. der Default.">
            Zurücksetzen
          </button>
        ) : null}
      </div>
    </div>
  )
}

/* Woher der wirksame Wert stammt. Der HA-Helfer ist der Normalfall und bleibt
   unbeschriftet — eine Markierung an jedem Helfer wäre nur Rauschen. Der Text
   ist kurz gehalten, damit er neben dem Wert Platz hat; die Erklärung steht im
   title. */
function SourceHint({ target, diagnostic, internalSet }: {
  target: WriteTarget
  diagnostic: EntityDiagnostic | undefined
  internalSet: boolean
}) {
  if (target === 'hems') {
    if (internalSet) {
      return <span className="pill primary" title={SOURCE_TITLE.hems}>{SOURCE_LABEL.hems}</span>
    }
    const source = diagnostic?.source ?? 'internal'
    return (
      <span className="pill warn" title={`${SOURCE_TITLE[source]} Eine Eingabe hier speichert den Wert im HEMS.`}>
        {SOURCE_LABEL[source]}
      </span>
    )
  }
  if (diagnostic && diagnostic.source !== 'ha') {
    return (
      <span className="pill warn" title={`${SOURCE_TITLE[diagnostic.source]} Zustand: ${diagnostic.state}.`}>
        {SOURCE_LABEL[diagnostic.source]}
      </span>
    )
  }
  return null
}
