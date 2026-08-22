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
  /** Je gelesener Entität: welcher Wert wirkt gerade, und warum nicht der aus HA. */
  entity_diagnostics: Record<string, EntityDiagnostic>
  /** false heißt „technisch nicht regelbar" — nicht dasselbe wie eligible: false. */
  runtime_active: boolean
  inactive_reasons: string[]
  /** Bereinigte Meldung des letzten fehlgeschlagenen Schreibversuchs. */
  write_error: string | null
}

/** Ursache und Quelle eines gelesenen HA-States. */
export interface EntityDiagnostic {
  role: string
  state: 'valid' | 'missing' | 'unavailable' | 'invalid' | 'write_failed'
  source: 'ha' | 'addon' | 'internal'
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

/** AC-gekoppelter Speicher. Einziges Gerät, das Leistung auch abgeben kann. */
export interface BatteryDevice extends DeviceBase {
  type: 'battery'
  /** Reihenfolge beim Entladen, unabhängig von priority (= Reihenfolge beim Laden). */
  entlade_prioritat: number
  /** false heißt: SoC- oder Leistungssensor liefert nichts — Speicher fällt aus der Regelung. */
  sensoren_gueltig: boolean
  /** false heißt: Die globale Hausleistungsbilanz liefert keinen brauchbaren Wert. */
  battery_residual_sensor_valid: boolean
  soc_prozent: number
  /** 0 heißt „nicht konfiguriert"; dann fehlt auch energie_kwh. */
  capacity_kwh: number
  energie_kwh?: number
  /** Vom Nutzer bzw. Energy Pilot gewünscht. */
  betriebsart: 'auto' | 'nur_laden' | 'nur_entladen' | 'standby'
  /** Was das HEMS diesen Zyklus tatsächlich schreibt. */
  betriebsart_effektiv: 'laden' | 'entladen' | 'standby'
  lade_ist_w: number
  entlade_ist_w: number
  /** Lade- und Entladeanteil des EINEN signierten Sollwerts, der in HA steht. */
  lade_anforderung_w: number
  entlade_anforderung_w: number
  new_lade_w: number
  new_entlade_w: number
  /** + laden / − entladen, so wie der Sollwert nach HA geschrieben wird. */
  netto_w: number
  /** Statischer available_*_w-Wert aus der Add-on-Konfiguration: die einzige
      physische Grenze. `0` sperrt die jeweilige Richtung bewusst. */
  max_ladeleistung_w: number
  max_entladeleistung_w: number
  lade_limit_gueltig: boolean
  entlade_limit_gueltig: boolean
  /** Derselbe Wert nach Freigaben und SoC-Grenzen. */
  lade_limit_w: number
  entlade_limit_w: number
  /** Vom Controller zugeteilter Anteil am Hausdefizit. */
  hausdefizit_anteil_w: number
  schutz_w: number
  geschuetzte_mindestleistung_w: number
  laden_erlaubt: boolean
  entladen_erlaubt: boolean
  netzladen_aktiv: boolean
  soc_min_prozent: number
  soc_max_prozent: number
  /** Ersetzen die entfallenen HA-Helfer; stehen in der Add-on-Konfiguration. */
  soc_max_hysteresis_percent: number
  direction_switch_delay_s: number
  umschaltsperre_rest_s: number
  /** Warum gerade nicht geladen wird. */
  lade_blockiert_grund: string | null
  /** Warum gerade nicht entladen wird. */
  entlade_blockiert_grund: string | null
  /** Grund auf Auflösungsebene: umschaltsperre oder totzone. */
  blockiert_grund: string | null
}

export type Device = ControllableDevice | BinaryDevice | BatteryDevice

export interface CycleStatus {
  timestamp: string
  ems_enabled: boolean
  global_mode: string
  hard_lockout: boolean
  residual_sensor_valid: boolean
  residual_w: number
  /** residual_w abzüglich der gemessenen Speicherentladung (netz_support_w). */
  residual_bereinigt_w: number
  /** Separate Hausleistungsbilanz für die Entladeplanung der AC-Speicher. */
  battery_residual_sensor_valid: boolean
  /** Negativ = Netzbezug/Unterdeckung, positiv = Einspeisung. */
  battery_residual_w: number
  /** battery_residual_w abzüglich der gemessenen AC-Entladung. */
  battery_residual_bereinigt_w: number
  /** "formula", wenn eine Formel (D-045) residual_w liefert, sonst "ha". */
  residual_source: 'ha' | 'formula'
  /** "formula", "ha", "addon" oder "internal" — siehe Resolve-Vertrag. */
  battery_residual_source: 'ha' | 'addon' | 'internal' | 'formula'
  /** Summe der gemessenen Entladeleistung aller Speicher. */
  netz_support_w: number
  /** Σ current_w — nur vom HEMS angeforderte Last, Force-Modus gefiltert. */
  hems_last_w: number
  /** Σ gemessene_last_w — roher Messwert, Force-Modus enthalten. */
  hems_last_gemessen_w: number
  /** Ungeklemmter Pool: positiv = Überschuss, negativ = Entladebedarf. */
  pool_roh_w: number
  pool_w: number
  /** Basis der Entladeplanung; weicht bei Fremdsteuerung von pool_roh_w ab. */
  entlade_basis_w: number
  /** Hausverbrauchs-Fehlbetrag, den die Speicher decken sollen. */
  hausdefizit_w: number
  current_deficit_w: number
  binary_immediate_off: boolean
  binary_total_w: number
  /** false: der gemeldete Modus ist global nicht aktiviert — Zyklus sicher inaktiv. */
  global_mode_configured: boolean
  available_modes: string[]
  devices: Device[]
  /** Beim Start übersprungene Einträge — ohne erfundene Ist-, SoC- oder Schaltwerte. */
  inactive_devices: InactiveDeviceIssue[]
  /** Geräte-IDs, die diesen Zyklus technisch nicht regelbar waren. */
  devices_inactive_runtime: string[]
}

export interface StatusResponse {
  status: CycleStatus | Record<string, never>
  /** Bereits als TT.MM.JJJJ hh:mm:ss in Berliner Zeit (eiserne Regel 9). */
  last_cycle_at: string
  cycle_count: number
  error: string
  interval_s: number
  /** Je Prozessstart neu. Erst eine ANDERE Kennung heißt „Neustart fertig". */
  instance_id: string
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
  /** Stabiler Schlüssel ohne Suffix-Raten. */
  key?: string
  kind?: 'bool' | 'number' | 'select' | 'auto'
  role?: string
  unit?: string
  planning_relevant?: boolean
}

export interface ControlGroup {
  /** Technische Geräte-ID; fehlt bei der Gruppe „Global". */
  name?: string
  label: string
  class?: DeviceClass
  entity_prefix?: string
  /** Vom HEMS geschriebene Anforderung. */
  request_entity?: string
  /** Nur beim Speicher: die zusätzlich geschriebene Betriebsart. */
  mode_entity?: string
  items: ControlItem[]
}

/* ---------------------------------------------------------------------------
   Konfiguration der Add-on-Optionen

   Spiegelt die Endpunkte aus docs/api-referenz.md#konfigurations-endpunkte.
   Die Feldnamen sind die der Add-on-Optionen und bleiben deshalb unverändert —
   sie sind Datenvertrag zur nativen Add-on-Seite.
   --------------------------------------------------------------------------- */

export type DeviceClass = 'controllable' | 'binary' | 'battery'

/** Ein Geräteeintrag im Entwurf. Klassenspezifische Felder sind optional,
    weil eine Liste alle drei Klassen gemischt trägt — verpflichtend sind sie
    trotzdem, und zwar je nach `class` (siehe docs/device_classes/). */
export interface ConfigDevice {
  name: string
  class: DeviceClass | ''
  label: string
  entity_prefix: string
  /** Kommagetrennt. Leer heißt „nur Energy Pilot" und ist gültig. */
  allowed_modes: string

  /* controllable */
  actual_power_entity?: string
  output_unit?: 'watt' | 'ampere'
  phases?: string
  phase_switch_delay_s?: number | null
  voltage_l1_entity?: string
  voltage_l2_entity?: string
  voltage_l3_entity?: string
  /** In der zu `output_unit` passenden Einheit, nicht in Watt. */
  technical_minimum?: number | null
  technical_maximum?: number | null
  increase_delay_s?: number | null
  decrease_delay_s?: number | null
  maximum_step_change?: number | null
  minimum_step_change?: number | null

  /* binary */
  switch_entity?: string
  power_w?: number | null
  on_reserve_w?: number | null
  min_runtime_s?: number | null
  min_offtime_s?: number | null
  off_delay_s?: number | null

  /* battery */
  soc_entity?: string
  charge_power_entity?: string
  discharge_power_entity?: string
  power_entity?: string
  power_sign?: 'positiv_laden' | 'positiv_entladen'
  available_charge_power_w?: number | null
  available_discharge_power_w?: number | null
  capacity_kwh?: number | null
  soc_max_hysteresis_percent?: number | null
  direction_switch_delay_s?: number | null
}

/** Eine Formel-Zeile (D-045): benannte HA-Entität für den Code darunter. */
export interface FormulaVariable {
  name: string
  entity: string
}

export interface ConfigOptions {
  interval_s: number
  log_level: string
  post_cycle_script: string
  residual_power_entity: string
  battery_residual_power_entity: string
  speicher_in_residual_enthalten: boolean
  /** Kommagetrennte Teilmenge der normalen Regelmodi. */
  available_modes: string
  /** Formel-basierte Sensorwerte (D-045): liefert der Code einen gültigen Wert,
      ersetzt er die jeweilige Entität oben vollständig. Leer = keine Formel. */
  residual_formula_variables: FormulaVariable[]
  residual_formula_code: string
  battery_residual_formula_variables: FormulaVariable[]
  battery_residual_formula_code: string
  devices: ConfigDevice[]
}

/** Ein Eintrag, der beim Start nicht instanziiert würde. */
export interface InactiveDeviceIssue {
  index: number
  name: string
  device_class: string
  label: string
  /** Feldname ohne Pfadpräfix → deutsche Meldung. */
  errors: Record<string, string>
}

/** Wertebereiche und Formular-Startwerte — eine Quelle für Server und UI. */
export interface ConfigSupported {
  modes: string[]
  special_modes: string[]
  device_classes: DeviceClass[]
  log_levels: string[]
  output_units: string[]
  phases: string[]
  power_signs: string[]
  global_defaults: Record<string, string | number | boolean>
  device_defaults: Record<DeviceClass, Record<string, number | null>>
}

export interface ConfigValidation {
  valid: boolean
  errors: string[]
  /** Feldpfad („devices[2].technical_maximum") → deutsche Meldung. */
  field_errors: Record<string, string>
  inactive_devices: InactiveDeviceIssue[]
}

export interface ConfigResponse extends ConfigValidation {
  options: ConfigOptions
  /** Hash der gespeicherten rohen Optionen — Schutz gegen Paralleländerung. */
  stored_revision: string
  /** Stand, mit dem der laufende Controller instanziiert wurde. */
  loaded_revision: string
  restart_required: boolean
  can_save: boolean
  can_restart: boolean
  supervisor_available: boolean
  supervisor_error: string
  instance_id: string
  supported: ConfigSupported
}

/** Antwort auf Speichern, Neustart und Speichern-und-neu-starten. */
export interface ConfigSaveResult {
  stored_revision: string
  loaded_revision?: string
  restart_required?: boolean
  /** false bei „gespeichert, aber nicht neu gestartet". */
  restarting?: boolean
  instance_id?: string
  deactivation_failed?: string[]
  message?: string
}

/** Eintrag der Entitätssuche — bewusst ohne die vollständigen Attribute. */
export interface EntityOption {
  entity_id: string
  domain: string
  state: string
  friendly_name: string
}

/** Diagnose einer einzelnen Formel-Zeile im Testlauf (D-045). */
export interface FormulaVariableResult extends FormulaVariable {
  value: number | null
  valid: boolean
  state: 'valid' | 'missing' | 'unavailable' | 'invalid'
  source: 'ha' | 'addon' | 'internal'
}

/** Ergebnis von POST /api/config/sensors/test — immer 200, auch bei Fehler. */
export interface FormulaTestResult {
  valid: boolean
  value: number | null
  error: string | null
  error_line: number | null
  variables: FormulaVariableResult[]
}
