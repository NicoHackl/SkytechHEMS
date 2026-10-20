import { DeviceCard, KeyValue, type CardState, type ValueTone } from '../components/DeviceCard'
import { EnergyPilotPage, useEnergyPilot } from '../components/EnergyPilotShared'
import { Icon } from '../components/Icon'
import type { HaEntities } from '../types'

/* Vorschläge des Energy Pilot je Gerät. Reine Anzeige – ob sie wirken,
   entscheidet der Regelmodus (siehe Steuerung). */

export function EnergyPilotVorschlaege() {
  const { states, loadError, updatedAt, now } = useEnergyPilot()

  return (
    <EnergyPilotPage subtitle="Vorschläge je Gerät" states={states} loadError={loadError} updatedAt={updatedAt}>
      {(loaded) => {
        const groups = groupSuggestions(loaded, now)
        return groups.length ? (
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
              <span>Der Energy Pilot veröffentlicht sie in <code>sensor.energy_pilot_schnittstelle</code>.</span>
            </div>
          </div>
        )
      }}
    </EnergyPilotPage>
  )
}

function displayValue(state: string, unit: string | undefined): { text: string; tone: ValueTone } {
  if (!state || state === 'unavailable' || state === 'unknown') return { text: '–', tone: 'muted' }
  if (state === 'on') return { text: 'Ja', tone: 'ok' }
  if (state === 'off') return { text: 'Nein', tone: 'err' }
  return { text: unit ? `${state} ${unit}` : state, tone: 'plain' }
}

/* Schnittstellen-Entität des Energy Pilot (D-070, Vertrag HEMS ↔ Energy-Pilot 2.0). */
const EP_INTERFACE = 'sensor.energy_pilot_schnittstelle'

/* Feste Vorschlagsfelder: Attribut-Endung → Anzeige. Längere Endungen zuerst, damit
   `_entlade_prio` nicht als `_prio` erkannt wird. */
const INTERFACE_FIELDS: { suffix: string; label: string; unit?: string }[] = [
  { suffix: 'geschutzte_mindestleistung_w', label: 'Geschützte Mindestleistung', unit: 'W' },
  { suffix: 'geschutzte_mindestleistung_a', label: 'Geschützte Mindestleistung', unit: 'A' },
  { suffix: 'soc_ziel_prozent', label: 'SoC-Ziel', unit: '%' },
  { suffix: 'soc_min_prozent', label: 'SoC-Minimum', unit: '%' },
  { suffix: 'entlade_prio', label: 'Entladepriorität' },
  { suffix: 'betriebsart', label: 'Betriebsart' },
  { suffix: 'freigabe', label: 'Freigabe' },
  { suffix: 'prio', label: 'Priorität' },
]

/** Attributwert als Zustandstext wie bei einer HA-Entität (`on`/`off` für Bools). */
function asStateText(value: unknown): string {
  if (typeof value === 'boolean') return value ? 'on' : 'off'
  if (value === null || value === undefined) return ''
  return String(value)
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
/* Vorschlagsfelder, die das HEMS nicht mehr liest. Die HA-Entitäten können in
   einer Bestandsanlage weiterleben; sie hier zu zeigen behauptete aber, sie
   wirkten noch — der Energy Pilot darf die physischen WR-Grenzen des Speichers
   nicht überschreiben. */
const AUSSER_DIENST = ['_lade_max_w_vorschlag', '_entlade_max_w_vorschlag']

function groupSuggestions(states: HaEntities, now: number): SuggestionGroup[] {
  const grouped: Record<string, Record<string, SuggestionField>> = {}

  // Feste Vorschläge je Gerät aus der Schnittstellen-Entität.
  const iface = states[EP_INTERFACE]
  const ifaceUntil = Date.parse(String(iface?.attributes.valid_until ?? ''))
  if (iface && !(ifaceUntil < now)) {
    const attrs = iface.attributes as Record<string, unknown>
    const prefixes = iface.state.split(',').map((p) => p.trim()).filter(Boolean)
    for (const prefix of prefixes) {
      const label = typeof attrs[`${prefix}_label`] === 'string' ? (attrs[`${prefix}_label`] as string) : prefix
      const fields = grouped[label] ?? (grouped[label] = {})
      for (const field of INTERFACE_FIELDS) {
        const value = attrs[`${prefix}_${field.suffix}`]
        if (value === undefined || value === null) continue
        fields[field.label] = {
          label: field.label,
          state: asStateText(value),
          unit: field.unit,
          validUntil: Number.isNaN(ifaceUntil) ? 0 : ifaceUntil,
        }
      }
    }
  }

  // Zusatz-Vorschläge bleiben eigene Sensoren `sensor.ep_<obj>_vorschlag`.
  for (const [entityId, entity] of Object.entries(states)) {
    if (!entityId.endsWith('_vorschlag')) continue
    if (AUSSER_DIENST.some((feld) => entityId.endsWith(feld))) continue // (0) nicht mehr gelesen

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
