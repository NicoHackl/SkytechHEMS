import { Icon } from './Icon'
import { EntityField, TextField } from './ConfigFields'
import type { EntityOption, FormulaVariable } from '../types'

/* Zeilen-Liste für Formel-basierte Sensorwerte (D-045): Variablenname +
   HA-Entität, mit Hinzufügen/Entfernen. Geteilt von beiden Sensoren-Tabs
   (Überschuss, Hausbilanz) — deshalb eigene Datei statt Seiten-lokal.

   Bewusst KEIN <table>: jede Zeile bräuchte sonst entweder eine sichtbare
   Beschriftung je Feld (redundant zu Spaltenköpfen) oder eine leere, nur für
   Screenreader gedachte — dafür gibt es im Katalog kein Sr-only-Dienstprogramm,
   und eines allein für diesen einen Fall einzuführen wäre unverhältnismäßig.
   Ein wiederholter Zeilen-Block mit echten Feld-Labels („Name", „HA-Entität")
   ist stattdessen ohne jede Zusatzarbeit barrierefrei. */

export function FormulaVariablesField({
  variables, entities, fieldErrors, pathPrefix, onChange,
}: {
  variables: FormulaVariable[]
  entities: EntityOption[]
  /** Ungefilterte Feldfehler des Entwurfs — die Zeilen-Pfade werden hier herausgesucht. */
  fieldErrors: Record<string, string>
  /** z. B. "residual_formula_variables" — muss zum Backend-Feldnamen passen. */
  pathPrefix: string
  onChange: (variables: FormulaVariable[]) => void
}) {
  const update = (index: number, partial: Partial<FormulaVariable>) => {
    onChange(variables.map((row, i) => (i === index ? { ...row, ...partial } : row)))
  }
  const remove = (index: number) => {
    onChange(variables.filter((_, i) => i !== index))
  }
  const add = () => {
    onChange([...variables, { name: '', entity: '' }])
  }

  return (
    <div className="formula-vars">
      {variables.length === 0 ? (
        <p className="hint-box">
          Noch keine Variable hinzugefügt. Ohne Variable kann der Code weiter unten keine
          HA-Entität lesen.
        </p>
      ) : variables.map((row, index) => (
        // Zeilen haben keine stabile Id und werden nie umsortiert — der Index reicht.
        <div className="formula-var-row" key={index}>
          <TextField
            label="Name" mono required
            value={row.name}
            error={fieldErrors[`${pathPrefix}[${index}].name`]}
            placeholder="z. B. pv"
            onChange={(value) => update(index, { name: value })}
          />
          <EntityField
            label="HA-Entität" required
            value={row.entity} entities={entities} domains={['sensor']}
            error={fieldErrors[`${pathPrefix}[${index}].entity`]}
            onChange={(value) => update(index, { entity: value })}
          />
          <button type="button" className="icon-btn danger-icon" aria-label={`Zeile ${index + 1} entfernen`}
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
