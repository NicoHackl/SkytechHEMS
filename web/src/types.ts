/* Datenverträge zum Add-on. Sie spiegeln docs/api-referenz.md und
   docs/datenmodell.md wider — weicht der Server ab, wird hier nachgezogen und
   nicht mit `any` umgangen. Die deutschen Feldnamen sind Absicht (D-034): sie
   sind Datenvertrag zu bestehenden Anlagen und zum Energy Pilot. */

/** Gemeinsame Felder beider Gerätetypen. */
interface DeviceBase {
  id: string
  label: string | null
  priority: number
  eligible: boolean
  /** Woher die wirksamen Werte stammen: aus, Nutzer-Helfer oder Energy Pilot. */
  source: 'aus' | 'user' | 'ep'
}

export interface ControllableDevice extends DeviceBase {
  type: 'controllable'
  actual_w: number
  /** Aktuell in HA stehender Sollwert, immer in Watt. */
  anforderung_current_w: number
  alloc_w: number
  new_w: number
  /** Effektiver Schutz = Sockel + Reserve + globaler Puffer, geklemmt. */
  schutz_w: number
  /** Roher Sockel, wie der Nutzer ihn gepflegt hat — nicht schutz_w. */
  geschuetzte_mindestleistung_w: number
  output_unit: 'watt' | 'ampere'
  /* Nur bei output_unit === 'ampere' vorhanden: */
  current_phases?: number
  allowed_phases?: number[]
  voltage_l1?: number
  voltage_l2?: number
  voltage_l3?: number
  new_a?: number
  schutz_a?: number
  geschuetzte_mindestleistung_a?: number
  /** Nur solange die Phasenwechsel-Sperre läuft. */
  phase_lock_remaining_s?: number
}

export interface BinaryDevice extends DeviceBase {
  type: 'binary'
  power_w: number
  actual_on: boolean
  /** Vom EMS geschriebene Anforderung. Schalter an ohne Anforderung = Fremdsteuerung. */
  anforderung_an: boolean
  desired_on: boolean
  candidate_on: boolean
  final_on: boolean
  in_min_runtime: boolean
  switch_age_s: number
  min_runtime_s: number
  min_offtime_s: number
  /** null heißt „keine Abschaltverzögerung aktiv" — 0 heißt „läuft gerade ab". */
  off_delay_remaining_s: number | null
}

export type Device = ControllableDevice | BinaryDevice

export interface CycleStatus {
  timestamp: string
  ems_enabled: boolean
  global_mode: string
  hard_lockout: boolean
  residual_sensor_valid: boolean
  residual_w: number
  pool_w: number
  current_deficit_w: number
  binary_immediate_off: boolean
  binary_total_w: number
  devices: Device[]
}

export interface StatusResponse {
  status: CycleStatus | Record<string, never>
  /** Bereits als TT.MM.JJJJ hh:mm:ss in Berliner Zeit (eiserne Regel 9). */
  last_cycle_at: string
  cycle_count: number
  error: string
  interval_s: number
}

/** Zustand einer HA-Entität, so wie /api/controls und /api/ep sie liefern. */
export interface HaEntity {
  state: string
  attributes: {
    unit_of_measurement?: string
    friendly_name?: string
    min?: number
    max?: number
    step?: number
    options?: string[]
    /* Attribute der Energy-Pilot-Sensoren: */
    label?: string
    valid_until?: string
    in_window?: boolean
    abweichungen?: string[]
    last_cycle_at?: string
    cycle_count?: number
    global_mode?: string
    error?: string
  }
  last_changed: string | null
}

export type HaEntities = Record<string, HaEntity>

export interface ControlItem {
  entity: string
  label: string
}

export interface ControlGroup {
  /** Technische Geräte-ID; fehlt bei der Gruppe „Global". */
  name?: string
  label: string
  items: ControlItem[]
}
