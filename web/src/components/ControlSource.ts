import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type {
  ControlGroup, ControlItem, EntityDiagnostic, HaEntities, HaEntity, InternalValues, StatusResponse,
} from '../types'

/* Gemeinsame Sicht von „Steuerung" und „Steuerung Info" auf die Frage, woher
   ein Helferwert kommt und wohin eine Änderung geschrieben wird (D-061).

   Reihenfolge im Regelzyklus: gültiger HA-Helfer → HEMS-interner Wert →
   Add-on-Feld → Default. Beide Seiten leiten das Schreibziel hier ab, damit
   die Info-Seite nie etwas anderes behauptet, als die Steuerung tut. */

export type HelperState = 'valid' | 'missing' | 'unavailable' | 'invalid'
export type WriteTarget = 'ha' | 'hems' | 'none'
export type InternalValue = boolean | number | string

const UNAVAILABLE_STATES = ['unknown', 'unavailable', 'none', '']

export const HELPER_STATE_LABEL: Record<HelperState, string> = {
  valid: 'vorhanden',
  missing: 'fehlt',
  unavailable: 'nicht verfügbar',
  invalid: 'ungültig',
}

export const SOURCE_LABEL: Record<EntityDiagnostic['source'], string> = {
  ha: 'HA-Helfer',
  hems: 'HEMS-intern',
  addon: 'Add-on-Wert',
  internal: 'Default',
}

export const SOURCE_TITLE: Record<EntityDiagnostic['source'], string> = {
  ha: 'Der Wert kommt aus dem HA-Helfer.',
  hems: 'Der HA-Helfer wirkt gerade nicht – der im HEMS eingegebene Wert greift.',
  addon: 'Der HA-Helfer wirkt gerade nicht – der Wert aus der Add-on-Konfiguration greift.',
  internal: 'Der HA-Helfer wirkt gerade nicht – ein interner Sicherheitsdefault greift.',
}

/** Zustand des HA-Helfers. Ohne Zyklusdiagnose zählt nur, ob HA ihn liefert. */
export function helperState(entity: HaEntity | undefined, diagnostic: EntityDiagnostic | undefined): HelperState {
  if (!entity) return 'missing'
  if (UNAVAILABLE_STATES.includes(String(entity.state ?? '').toLowerCase())) return 'unavailable'
  if (diagnostic?.state === 'invalid') return 'invalid'
  return 'valid'
}

/** Wohin die Steuerung eine Änderung schreibt.
    Gültiger Helfer → HA. Sonst, wenn erlaubt, der HEMS-interne Wert.
    Freigaben und Zwang (nicht intern einstellbar) bleiben beim Helfer, sofern
    es ihn gibt — sonst lässt sich nichts einstellen. */
export function writeTarget(
  item: ControlItem,
  entity: HaEntity | undefined,
  diagnostic: EntityDiagnostic | undefined,
): WriteTarget {
  if (helperState(entity, diagnostic) === 'valid') return 'ha'
  if (item.internal_editable) return 'hems'
  return entity ? 'ha' : 'none'
}

/** Diagnosen aller Geräte und der globalen Helfer aus dem letzten Zyklus. */
export function collectDiagnostics(response: StatusResponse): Record<string, EntityDiagnostic> {
  if (!('devices' in response.status)) return {}
  return Object.assign(
    {},
    response.status.global_entity_diagnostics ?? {},
    ...response.status.devices.map((device) => device.entity_diagnostics),
  )
}

/** Anzeigeform eines Helferwerts – An/Aus, Zahl mit Einheit oder Auswahl. */
export function formatControlValue(item: ControlItem, value: unknown): string {
  if (value === null || value === undefined || value === '') return '–'
  if (item.kind === 'bool') return value === true || value === 'on' ? 'An' : 'Aus'
  if (item.kind === 'number') {
    const number = typeof value === 'number' ? value : Number.parseFloat(String(value))
    if (Number.isNaN(number)) return String(value)
    const text = number.toLocaleString('de-DE', { maximumFractionDigits: 2 })
    return item.unit ? `${text} ${item.unit}` : text
  }
  return String(value)
}

/** Lädt Schema, HA-Zustände, Zyklusdiagnosen und interne Werte und frischt sie
    regelmäßig auf. Das Schema ändert sich nur mit einem Add-on-Neustart und wird
    deshalb einmal geladen. */
export function useControlData(refreshMs: number) {
  const [schema, setSchema] = useState<ControlGroup[] | null>(null)
  const [states, setStates] = useState<HaEntities | null>(null)
  const [diagnostics, setDiagnostics] = useState<Record<string, EntityDiagnostic>>({})
  const [internal, setInternal] = useState<InternalValues>({ values: {}, file_error: '' })
  const [loadError, setLoadError] = useState('')
  const [updatedAt, setUpdatedAt] = useState('')

  const load = useCallback(async () => {
    try {
      const [nextSchema, nextStates, status, nextInternal] = await Promise.all([
        schema ? Promise.resolve(schema) : api.controlsSchema(),
        api.controls(),
        api.status(),
        api.internalValues(),
      ])
      setSchema(nextSchema)
      setStates(nextStates)
      setDiagnostics(collectDiagnostics(status))
      setInternal(nextInternal)
      setUpdatedAt(new Date().toLocaleTimeString('de-DE', { timeZone: 'Europe/Berlin' }))
      setLoadError('')
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [schema])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), refreshMs)
    return () => window.clearInterval(timer)
  }, [load, refreshMs])

  return { schema, states, diagnostics, internal, loadError, updatedAt, load }
}
