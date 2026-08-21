import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from 'react'
import { api, ApiError } from '../api'
import { useToast } from './Toast'
import type {
  ConfigDevice, ConfigOptions, ConfigResponse, ConfigSaveResult, EntityOption,
} from '../types'

/* Gemeinsamer Entwurf der Add-on-Optionen für alle Konfigurationsseiten.

   Bewusst React-Context statt eines State-Pakets (docs/frontend.md): der
   Entwurf ist ein Objekt, das drei Seiten teilen — dafür lohnt keine
   Abhängigkeit. Der Provider liegt über dem Layout, damit ein Seitenwechsel
   den Entwurf nicht verwirft und die Navigation ihn vor dem Verlassen
   erkennen kann.

   Geladen wird erst, wenn eine Konfigurationsseite es anfordert. Wer nur den
   Status ansieht, löst keinen zusätzlichen Abruf aus. */

type Busy = '' | 'save' | 'restart' | 'save-restart'

interface ConfigDraftValue {
  data: ConfigResponse | null
  draft: ConfigOptions | null
  entities: EntityOption[]
  loadError: string
  /** Serverseitige Feldfehler des zuletzt geprüften Entwurfs. */
  fieldErrors: Record<string, string>
  dirty: boolean
  busy: Busy
  /** true nach einem 409: der Entwurf bleibt stehen, der Nutzer entscheidet. */
  conflict: boolean
  restarting: boolean
  ensureLoaded: () => void
  reload: () => Promise<void>
  patch: (partial: Partial<ConfigOptions>) => void
  setDevices: (devices: ConfigDevice[]) => void
  discard: () => void
  save: () => Promise<boolean>
  restart: () => Promise<void>
  saveAndRestart: () => Promise<void>
}

const ConfigDraftContext = createContext<ConfigDraftValue | null>(null)

/** Domains, die die Entitätsauswahl anbietet. */
const ENTITY_DOMAINS = ['sensor', 'switch', 'script', 'input_number', 'input_boolean', 'input_select']

const POLL_MS = 1500
const POLL_TIMEOUT_MS = 90000

export function ConfigDraftProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<ConfigResponse | null>(null)
  const [draft, setDraft] = useState<ConfigOptions | null>(null)
  const [entities, setEntities] = useState<EntityOption[]>([])
  const [loadError, setLoadError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState<Busy>('')
  const [conflict, setConflict] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const requested = useRef(false)
  const { toast } = useToast()

  const reload = useCallback(async () => {
    try {
      const next = await api.config()
      setData(next)
      setDraft(structuredClone(next.options))
      setFieldErrors(next.field_errors)
      setDirty(false)
      setConflict(false)
      setLoadError('')
      try {
        setEntities((await api.configEntities(ENTITY_DOMAINS)).entities)
      } catch {
        /* Ohne Entitätsliste bleibt die Auswahl ein freies Textfeld – das ist
           weniger bequem, aber kein Grund, die ganze Seite zu verweigern. */
        setEntities([])
      }
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [])

  const ensureLoaded = useCallback(() => {
    if (requested.current) return
    requested.current = true
    void reload()
  }, [reload])

  /* Neuladen und Schliessen des Tabs: der Browser fragt selbst nach. */
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const patch = useCallback((partial: Partial<ConfigOptions>) => {
    setDraft((current) => (current ? { ...current, ...partial } : current))
    setDirty(true)
  }, [])

  const setDevices = useCallback((devices: ConfigDevice[]) => {
    setDraft((current) => (current ? { ...current, devices } : current))
    setDirty(true)
  }, [])

  const discard = useCallback(() => {
    if (!data) return
    setDraft(structuredClone(data.options))
    setFieldErrors(data.field_errors)
    setDirty(false)
  }, [data])

  /* Nach einem ausgelösten Neustart auf eine NEUE Prozessinstanz warten. Eine
     sehr kurze Unterbrechung sähe sonst wie ein abgeschlossener Neustart aus. */
  const waitForRestart = useCallback(async (previousInstance: string) => {
    setRestarting(true)
    const deadline = Date.now() + POLL_TIMEOUT_MS
    while (Date.now() < deadline) {
      await new Promise((resolve) => window.setTimeout(resolve, POLL_MS))
      try {
        const status = await api.status()
        if (status.instance_id && status.instance_id !== previousInstance) {
          setRestarting(false)
          await reload()
          toast('Add-on neu gestartet, Konfiguration ist wirksam.')
          return
        }
      } catch {
        /* Während des Neustarts ist das Add-on erwartungsgemäss weg. */
      }
    }
    setRestarting(false)
    toast('Der Neustart dauert ungewöhnlich lange. Bitte die Seite neu laden.', 'err')
  }, [reload, toast])

  const handleError = useCallback((error: unknown, fallback: string) => {
    if (error instanceof ApiError && error.status === 409) {
      setConflict(true)
      toast(error.message, 'err')
      return
    }
    if (error instanceof ApiError && error.status === 422) {
      const details = (error.details ?? {}) as { field_errors?: Record<string, string> }
      if (details.field_errors) setFieldErrors(details.field_errors)
      toast(error.message, 'err')
      return
    }
    toast(`${fallback}: ${(error as Error).message}`, 'err')
  }, [toast])

  const save = useCallback(async () => {
    if (!draft || !data) return false
    setBusy('save')
    try {
      const result = await api.saveConfig(draft, data.stored_revision)
      applySaved(result)
      setDirty(false)
      setFieldErrors({})
      setConflict(false)
      toast('Gespeichert. Wirksam wird die Änderung erst nach einem Neustart.')
      return true
    } catch (error) {
      handleError(error, 'Speichern fehlgeschlagen')
      return false
    } finally {
      setBusy('')
    }

    function applySaved(result: ConfigSaveResult) {
      setData((current) => (current ? {
        ...current,
        options: structuredClone(draft!),
        stored_revision: result.stored_revision,
        restart_required: result.restart_required ?? true,
        field_errors: {},
        valid: true,
      } : current))
    }
  }, [data, draft, handleError, toast])

  const restart = useCallback(async () => {
    if (!data) return
    setBusy('restart')
    try {
      await api.restartAddon()
      void waitForRestart(data.instance_id)
    } catch (error) {
      handleError(error, 'Neustart fehlgeschlagen')
    } finally {
      setBusy('')
    }
  }, [data, handleError, waitForRestart])

  const saveAndRestart = useCallback(async () => {
    if (!draft || !data) return
    setBusy('save-restart')
    try {
      const result = await api.saveAndRestartAddon(draft, data.stored_revision)
      setDirty(false)
      setFieldErrors({})
      setConflict(false)
      if (result.restarting) {
        void waitForRestart(data.instance_id)
      } else {
        // Gespeichert, aber nicht neu gestartet: ein eigener Zustand, kein Fehler.
        toast(result.message ?? 'Gespeichert, der Neustart wurde nicht ausgelöst.', 'err')
        await reload()
      }
    } catch (error) {
      handleError(error, 'Speichern und Neustarten fehlgeschlagen')
    } finally {
      setBusy('')
    }
  }, [data, draft, handleError, reload, toast, waitForRestart])

  const value = useMemo<ConfigDraftValue>(() => ({
    data, draft, entities, loadError, fieldErrors, dirty, busy, conflict, restarting,
    ensureLoaded, reload, patch, setDevices, discard, save, restart, saveAndRestart,
  }), [data, draft, entities, loadError, fieldErrors, dirty, busy, conflict, restarting,
      ensureLoaded, reload, patch, setDevices, discard, save, restart, saveAndRestart])

  return <ConfigDraftContext.Provider value={value}>{children}</ConfigDraftContext.Provider>
}

export function useConfigDraft(): ConfigDraftValue {
  const context = useContext(ConfigDraftContext)
  if (!context) throw new Error('useConfigDraft muss innerhalb des ConfigDraftProvider verwendet werden.')
  return context
}
