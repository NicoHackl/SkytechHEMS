import { useId, type ReactNode } from 'react'
import { Icon } from './Icon'
import type { EntityOption } from '../types'

/* Bausteine der Konfigurationsformulare. Sie liegen hier und nicht in einer
   Seite, weil globale Seite und Geräteformular dieselben Muster brauchen:
   ein Feld mit Pflichtmarkierung und Serverfehler, eine Entitätsauswahl und
   eine Modus-Checkboxgruppe. */

/** Ein Formularfeld mit Label, Pflichtmarkierung, Hilfetext und Feldfehler. */
export function Field({
  label, required, hint, error, wide, children,
}: {
  label: string
  required?: boolean
  hint?: string
  error?: string
  wide?: boolean
  children: ReactNode
}) {
  return (
    <label className={`field${error ? ' invalid' : ''}${wide ? ' wide' : ''}`}>
      <span>{label}{required ? <em> *</em> : null}</span>
      {children}
      {error ? <small className="field-error">{error}</small> : hint ? <small>{hint}</small> : null}
    </label>
  )
}

/** Zahlenfeld. Ein leeres Feld ist `null` — das ist etwas anderes als `0`. */
export function NumberField({
  label, value, onChange, required, hint, error, unit, min, step, wide,
}: {
  label: string
  value: number | null | undefined
  onChange: (value: number | null) => void
  required?: boolean
  hint?: string
  error?: string
  unit?: string
  min?: number
  step?: number
  wide?: boolean
}) {
  return (
    <Field label={unit ? `${label} (${unit})` : label}
           required={required} hint={hint} error={error} wide={wide}>
      <input
        type="number"
        value={value ?? ''}
        min={min}
        step={step ?? 'any'}
        onChange={(event) => {
          const raw = event.target.value
          onChange(raw === '' ? null : Number.parseFloat(raw))
        }}
      />
    </Field>
  )
}

/** Textfeld für einen freien Wert (Name, Präfix, Anzeigename). */
export function TextField({
  label, value, onChange, required, hint, error, placeholder, mono, wide,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  hint?: string
  error?: string
  placeholder?: string
  mono?: boolean
  wide?: boolean
}) {
  return (
    <Field label={label} required={required} hint={hint} error={error} wide={wide}>
      <input
        type="text"
        className={mono ? 'mono' : undefined}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  )
}

/** Auswahlfeld aus einer festen Werteliste. */
export function SelectField({
  label, value, options, onChange, required, hint, error, labels, wide,
}: {
  label: string
  value: string
  options: string[]
  onChange: (value: string) => void
  required?: boolean
  hint?: string
  error?: string
  labels?: Record<string, string>
  wide?: boolean
}) {
  return (
    <Field label={label} required={required} hint={hint} error={error} wide={wide}>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option value={option} key={option}>{labels?.[option] ?? option}</option>
        ))}
      </select>
    </Field>
  )
}

/** Entitätsauswahl: freies Textfeld mit Vorschlagsliste aus dem HA-Schnappschuss.

    Bewusst ein `datalist` und keine UI-Bibliothek: die Eingabe bleibt frei, der
    Nutzer kann eine noch nicht vorhandene Entität eintragen, und Tastatur wie
    Screenreader funktionieren ohne eigenes Widget. Ein gespeicherter Wert, den
    es aktuell nicht gibt, wird mit Warnung angezeigt — niemals stillschweigend
    gelöscht. */
export function EntityField({
  label, value, onChange, entities, domains, required, hint, error, wide,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  entities: EntityOption[]
  domains: string[]
  required?: boolean
  hint?: string
  error?: string
  wide?: boolean
}) {
  const listId = useId()
  const passend = entities.filter((entity) => domains.includes(entity.domain))
  const bekannt = value === '' || passend.some((entity) => entity.entity_id === value)
  const unbekannt = value !== '' && !bekannt && entities.length > 0

  return (
    <Field label={label} required={required} hint={hint} error={error} wide={wide}>
      <input
        type="text"
        className="mono"
        list={listId}
        value={value}
        placeholder={`${domains[0]}.beispiel`}
        onChange={(event) => onChange(event.target.value.trim())}
      />
      <datalist id={listId}>
        {passend.map((entity) => (
          <option value={entity.entity_id} key={entity.entity_id}>
            {entity.friendly_name || entity.entity_id}
          </option>
        ))}
      </datalist>
      {unbekannt ? (
        <small className="entity-warn">
          <Icon name="warning" size={14} />
          Diese Entität gibt es in Home Assistant gerade nicht. Der Wert bleibt erhalten.
        </small>
      ) : null}
    </Field>
  )
}

/** Checkbox-Gruppe für Regelmodi. Leere Auswahl ist gültig. */
export function ModeChecks({
  legend, value, options, onChange, hint, error, disabledHint,
}: {
  legend: string
  value: string
  options: string[]
  onChange: (value: string) => void
  hint?: string
  error?: string
  disabledHint?: (mode: string) => string | undefined
}) {
  const selected = value.split(',').map((mode) => mode.trim()).filter(Boolean)
  const toggle = (mode: string) => {
    const next = selected.includes(mode)
      ? selected.filter((entry) => entry !== mode)
      : [...selected, mode]
    // Stabile Reihenfolge: sonst wechselt der Revisions-Hash ohne Grund.
    onChange(options.filter((entry) => next.includes(entry)).join(','))
  }

  return (
    <fieldset className={`field mode-checks${error ? ' invalid' : ''}`}>
      <legend><span>{legend}</span></legend>
      <div className="mode-check-row">
        {options.map((mode) => {
          const gesperrt = disabledHint?.(mode)
          return (
            <label className="mode-check" key={mode} title={gesperrt}>
              <input
                type="checkbox"
                checked={selected.includes(mode)}
                disabled={Boolean(gesperrt)}
                onChange={() => toggle(mode)}
              />
              <span>{MODE_LABELS[mode] ?? mode}</span>
            </label>
          )
        })}
      </div>
      {error ? <small className="field-error">{error}</small> : hint ? <small>{hint}</small> : null}
    </fieldset>
  )
}

const MODE_LABELS: Record<string, string> = {
  manuell: 'Manuell',
  nur_heizen: 'Nur Heizen',
  nur_laden: 'Nur Laden',
}
