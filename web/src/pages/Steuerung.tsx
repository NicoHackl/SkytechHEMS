import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { Icon } from '../components/Icon'
import { useToast } from '../components/Toast'
import type { ControlGroup, ControlItem, HaEntities, HaEntity } from '../types'

/* Alle EMS-Helfer je Gerät und global, direkt einstellbar.

   Das Schema kommt aus /api/device_controls_schema und wird einmal geladen —
   es ändert sich nur, wenn die Add-on-Konfiguration geändert und das Add-on neu
   gestartet wird. Die Werte kommen aus /api/controls und werden alle 15 s
   aufgefrischt. */

const REFRESH_MS = 15000
const DEBOUNCE_MS = 700

export function Steuerung() {
  const [schema, setSchema] = useState<ControlGroup[] | null>(null)
  const [states, setStates] = useState<HaEntities | null>(null)
  const [loadError, setLoadError] = useState('')
  const [updatedAt, setUpdatedAt] = useState('')
  /* Lokal geänderte, noch nicht bestätigte Werte. Ohne sie würde die
     Auffrischung eine laufende Eingabe überschreiben. */
  const [edits, setEdits] = useState<Record<string, string>>({})
  const timers = useRef<Record<string, number>>({})
  const { toast } = useToast()

  const load = useCallback(async () => {
    try {
      const [nextSchema, nextStates] = await Promise.all([
        schema ? Promise.resolve(schema) : api.controlsSchema(),
        api.controls(),
      ])
      setSchema(nextSchema)
      setStates(nextStates)
      setUpdatedAt(new Date().toLocaleTimeString('de-DE'))
      setLoadError('')
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [schema])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [load])

  // Offene Debounce-Timer beim Verlassen der Seite abräumen.
  useEffect(() => {
    const pending = timers.current
    return () => Object.values(pending).forEach((id) => window.clearTimeout(id))
  }, [])

  const save = useCallback(async (entityId: string, value: boolean | number | string) => {
    window.clearTimeout(timers.current[entityId])
    delete timers.current[entityId]
    try {
      await api.setEntity(entityId, value)
      await load()
      setEdits((current) => {
        const next = { ...current }
        delete next[entityId]
        return next
      })
      toast('Gespeichert.')
    } catch (error) {
      // Der lokale Wert bleibt stehen, damit die Eingabe nicht verlorengeht.
      toast(`Speichern fehlgeschlagen: ${(error as Error).message}`, 'err')
    }
  }, [load, toast])

  const scheduleSave = useCallback((entityId: string, value: string) => {
    setEdits((current) => ({ ...current, [entityId]: value }))
    window.clearTimeout(timers.current[entityId])
    timers.current[entityId] = window.setTimeout(() => {
      const parsed = Number.parseFloat(value)
      if (Number.isNaN(parsed)) return
      void save(entityId, parsed)
    }, DEBOUNCE_MS)
  }, [save])

  const saveNow = useCallback((entityId: string, value: string) => {
    const parsed = Number.parseFloat(value)
    if (Number.isNaN(parsed)) return
    void save(entityId, parsed)
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

        <div className="info-strip">
          <Icon name="info" size={16} />
          <span>Änderungen wirken sofort auf die Home-Assistant-Helfer und damit auf den nächsten Regelzyklus.</span>
        </div>

        {schema.length ? (
          <div className="device-grid">
            {schema.map((group, index) => (
              <details className="card ctrl-group" key={group.name ?? `${group.label}-${index}`} open>
                <summary>{group.label}</summary>
                <div className="card-body">
                  {group.items.map((item) => (
                    <ControlRow
                      key={item.entity}
                      item={item}
                      entity={states[item.entity]}
                      edit={edits[item.entity]}
                      onToggle={(value) => void save(item.entity, value)}
                      onSelect={(value) => void save(item.entity, value)}
                      onNumberInput={(value) => scheduleSave(item.entity, value)}
                      onNumberCommit={(value) => saveNow(item.entity, value)}
                    />
                  ))}
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
  edit,
  onToggle,
  onSelect,
  onNumberInput,
  onNumberCommit,
}: {
  item: ControlItem
  entity: HaEntity | undefined
  edit: string | undefined
  onToggle: (value: boolean) => void
  onSelect: (value: string) => void
  onNumberInput: (value: string) => void
  onNumberCommit: (value: string) => void
}) {
  const domain = item.entity.split('.')[0]

  return (
    <div className="ctrl-row">
      <span className="k">{item.label}</span>
      <div className="ctrl-value">
        {!entity ? (
          <span className="ctrl-missing">Helfer nicht gefunden</span>
        ) : domain === 'input_boolean' ? (
          <label className="switch">
            <input
              type="checkbox"
              checked={entity.state === 'on'}
              onChange={(event) => onToggle(event.target.checked)}
              aria-label={item.label}
            />
            <span className="track" />
            <span className="switch-label">{entity.state === 'on' ? 'An' : 'Aus'}</span>
          </label>
        ) : domain === 'input_number' ? (
          <>
            <input
              type="number"
              value={edit ?? entity.state}
              min={entity.attributes.min}
              max={entity.attributes.max}
              step={entity.attributes.step ?? 1}
              onChange={(event) => onNumberInput(event.target.value)}
              onBlur={(event) => {
                // Nur schreiben, wenn sich der Wert wirklich unterscheidet — ein
                // erneuter Write setzt last_changed zurück und stört das Rampen-Timing.
                const next = Number.parseFloat(event.target.value)
                if (!Number.isNaN(next) && next !== Number.parseFloat(entity.state)) {
                  onNumberCommit(event.target.value)
                }
              }}
              aria-label={item.label}
            />
            {entity.attributes.unit_of_measurement
              ? <span className="ctrl-unit">{entity.attributes.unit_of_measurement}</span>
              : null}
          </>
        ) : domain === 'input_select' ? (
          <select value={entity.state} onChange={(event) => onSelect(event.target.value)} aria-label={item.label}>
            {(entity.attributes.options ?? []).map((option) => (
              <option value={option} key={option}>{option}</option>
            ))}
          </select>
        ) : (
          <span className="ctrl-missing">{entity.state}</span>
        )}
      </div>
    </div>
  )
}
