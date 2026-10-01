import { Icon } from './Icon'
import { EntityField, Field, NumberField, SelectField, TextField } from './ConfigFields'
import type { EmergencyTarget, EmergencyTargetKind, EntityOption } from '../types'

/* Zielzeilen der Notabschaltung (D-059): HA-Entität plus Zustand, der beim
   Auslösen gesetzt wird — typischerweise die Automatik eines Geräts. Welches
   Eingabefeld der Wert bekommt, entscheidet die Domain der Entität; die
   Zuordnung kommt vom Backend (`supported.emergency_target_kinds`), damit
   Formular, Validierung und Ausführung dieselbe Tabelle lesen.

   Zeilenmuster wie FormulaVariablesField: wiederholter Block mit echten
   Feld-Labels statt <table>. */

const ON_OFF_LABELS: Record<string, string> = { '': 'Bitte wählen', on: 'An', off: 'Aus' }

export function EmergencyTargetsField({
  targets, entities, kinds, fieldErrors, onChange,
}: {
  targets: EmergencyTarget[]
  entities: EntityOption[]
  kinds: Record<string, EmergencyTargetKind>
  /** Ungefilterte Feldfehler des Entwurfs — die Zeilen-Pfade werden hier herausgesucht. */
  fieldErrors: Record<string, string>
  onChange: (targets: EmergencyTarget[]) => void
}) {
  const domains = Object.keys(kinds)

  const update = (index: number, partial: Partial<EmergencyTarget>) => {
    onChange(targets.map((row, i) => (i === index ? { ...row, ...partial } : row)))
  }
  const setEntity = (index: number, entity: string) => {
    // Wechselt die Art des Werts (z. B. Schalter → Select), passt der alte Wert nicht mehr.
    const vorher = kinds[targets[index].entity.split('.')[0]]
    const nachher = kinds[entity.split('.')[0]]
    update(index, vorher === nachher ? { entity } : { entity, value: '' })
  }
  const remove = (index: number) => {
    onChange(targets.filter((_, i) => i !== index))
  }
  const add = () => {
    onChange([...targets, { entity: '', value: '' }])
  }

  return (
    <div className="formula-vars">
      {targets.length === 0 ? (
        <p className="hint-box">
          Noch keine Zielzeile. Ohne Zielzeile setzt die Notabschaltung nur die HEMS-Helfer auf
          0 W bzw. aus — Geräte mit eigener Automatik bleiben dann im zuletzt vom HEMS
          gesetzten Zustand.
        </p>
      ) : targets.map((row, index) => (
        // Zeilen haben keine stabile Id und werden nie umsortiert — der Index reicht.
        <div className="formula-var-row ziel-zeile" key={index}>
          <EntityField
            label="HA-Entität" required
            value={row.entity} entities={entities} domains={domains}
            error={fieldErrors[`emergency_targets[${index}].entity`]}
            onChange={(value) => setEntity(index, value)}
          />
          <ValueInput
            row={row}
            kind={kinds[row.entity.split('.')[0]]}
            entity={entities.find((entity) => entity.entity_id === row.entity)}
            error={fieldErrors[`emergency_targets[${index}].value`]}
            onChange={(value) => update(index, { value })}
          />
          <button type="button" className="icon-btn danger-icon" aria-label={`Zielzeile ${index + 1} entfernen`}
                  onClick={() => remove(index)}>
            <Icon name="trash" size={16} />
          </button>
        </div>
      ))}
      <button type="button" className="btn btn-ghost btn-sm" onClick={add}>
        <Icon name="plus" size={16} />Zeile hinzufügen
      </button>
    </div>
  )
}

/** Eingabefeld für den Zielzustand, passend zur Domain der Entität. */
function ValueInput({
  row, kind, entity, error, onChange,
}: {
  row: EmergencyTarget
  kind: EmergencyTargetKind | undefined
  entity: EntityOption | undefined
  error?: string
  onChange: (value: string) => void
}) {
  if (kind === 'on_off') {
    return (
      <SelectField label="Zustand" required value={row.value} options={['', 'on', 'off']}
                   labels={ON_OFF_LABELS} error={error} onChange={onChange} />
    )
  }
  if (kind === 'option' && entity?.options?.length) {
    // Ein gespeicherter Wert, den die Entität gerade nicht anbietet, bleibt
    // sichtbar und wählbar — er wird nie stillschweigend ersetzt.
    const options = ['', ...entity.options]
    if (row.value && !entity.options.includes(row.value)) options.push(row.value)
    return (
      <SelectField label="Option" required value={row.value} options={options}
                   labels={{ '': 'Bitte wählen' }} error={error} onChange={onChange} />
    )
  }
  if (kind === 'option') {
    return (
      <TextField label="Option" required value={row.value} error={error}
                 hint="Optionen der Entität unbekannt — Wert genau wie in HA eintragen."
                 onChange={onChange} />
    )
  }
  if (kind === 'number') {
    const zahl = row.value === '' ? null : Number.parseFloat(row.value.replace(',', '.'))
    return (
      <NumberField label="Wert" required unit={entity?.unit}
                   value={zahl != null && Number.isFinite(zahl) ? zahl : null}
                   min={entity?.min} max={entity?.max} step={entity?.step} error={error}
                   onChange={(value) => onChange(value == null ? '' : String(value))} />
    )
  }
  if (kind === 'press' || kind === 'run') {
    return (
      <Field label="Aktion" hint="Kein Wert nötig.">
        <input type="text" value={kind === 'press' ? 'Wird gedrückt' : 'Wird ausgeführt'} disabled />
      </Field>
    )
  }
  return (
    <TextField label="Wert" value={row.value} error={error}
               hint={row.entity ? 'Diese Domain wird nicht unterstützt.' : 'Erst eine Entität wählen.'}
               onChange={onChange} />
  )
}
