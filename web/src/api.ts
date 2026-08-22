import type {
  ConfigOptions, ConfigResponse, ConfigSaveResult, ConfigValidation,
  ControlGroup, EntityOption, FormulaTestResult, FormulaVariable, HaEntities, StatusResponse,
} from './types'

/* Einziger Ort im Frontend, an dem fetch aufgerufen wird. Basis-Pfad, Header und
   Fehlerbehandlung liegen damit an genau einer Stelle.

   Die Pfade sind relativ und beginnen bewusst OHNE Schrägstrich: Unter dem
   HA-Ingress läuft die Oberfläche unter /api/hassio_ingress/<token>/, und
   „/api/status" würde bei Home Assistant selbst landen statt beim Add-on
   (D-036, siehe docs/frontend.md). */

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details?: unknown,
  ) {
    super(message)
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  const response = await fetch(`api${path}`, { ...options, headers })
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    // Das Add-on meldet Fehler als {"error": "…"}; Fremdschichten (Ingress) als Text.
    const errorBody = isJson && typeof body === 'object' && body !== null
      ? body as Record<string, unknown>
      : undefined
    const errorText = errorBody?.error ?? body
    const message = typeof errorText === 'string' && errorText
      ? errorText
      : `Anfrage fehlgeschlagen (${response.status}).`
    // Der vollständige JSON-Rumpf enthält bei 422 die Feldfehler. Nur den
    // Fehlertext weiterzugeben ließ die UI genau diese Information verlieren.
    throw new ApiError(message, response.status, errorBody ?? body)
  }
  return body as T
}

/* Jeder Aufruf ist ein benannter Eintrag — kein roher Pfad in einer Seite. */
export const api = {
  status: () => request<StatusResponse>('/status'),
  controls: () => request<HaEntities>('/controls'),
  controlsSchema: () => request<ControlGroup[]>('/device_controls_schema'),
  energyPilot: () => request<HaEntities>('/ep'),
  setEntity: (entityId: string, value: boolean | number | string) =>
    request<{ ok: boolean }>('/set', {
      method: 'POST',
      body: JSON.stringify({ entity_id: entityId, value }),
    }),

  /* Konfiguration der Add-on-Optionen. Geschrieben wird serverseitig über die
     Supervisor-API — dieselbe Quelle wie die native Add-on-Seite. */
  config: () => request<ConfigResponse>('/config'),
  configEntities: (domains?: string[]) =>
    request<{ entities: EntityOption[] }>(
      domains?.length ? `/config/entities?domains=${domains.join(',')}` : '/config/entities',
    ),
  validateConfig: (options: ConfigOptions) =>
    request<ConfigValidation>('/config/validate', {
      method: 'POST',
      body: JSON.stringify({ options }),
    }),
  saveConfig: (options: ConfigOptions, storedRevision: string) =>
    request<ConfigSaveResult>('/config', {
      method: 'PUT',
      body: JSON.stringify({ options, stored_revision: storedRevision }),
    }),
  restartAddon: () =>
    request<ConfigSaveResult>('/config/restart', { method: 'POST' }),
  saveAndRestartAddon: (options: ConfigOptions, storedRevision: string) =>
    request<ConfigSaveResult>('/config/save-and-restart', {
      method: 'POST',
      body: JSON.stringify({ options, stored_revision: storedRevision }),
    }),

  /* Formel-basierte Sensorwerte (D-045): Testlauf gegen den aktuellen
     HA-Schnappschuss, ohne zu speichern. */
  testSensorFormula: (kind: 'residual' | 'battery_residual', variables: FormulaVariable[], code: string) =>
    request<FormulaTestResult>('/config/sensors/test', {
      method: 'POST',
      body: JSON.stringify({ kind, variables, code }),
    }),
}
