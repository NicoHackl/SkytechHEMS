import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'
import { PageHeader } from './Layout'
import type { HaEntities } from '../types'

/* Gemeinsame Bausteine der Unterseiten „Energy Pilot“ (Übersicht, Vorschläge).

   Der Energy Pilot schreibt seine Vorschläge und Statuswerte als
   sensor.ep_*-Entitäten nach Home Assistant; HEMS liest sie über /api/ep und
   spiegelt sie hier. Die eigentliche Übernahme passiert im Regelzyklus
   (Regelmodus = auto), nicht auf diesen Seiten. */

const REFRESH_MS = 10000

export function useEnergyPilot() {
  const [states, setStates] = useState<HaEntities | null>(null)
  const [loadError, setLoadError] = useState('')
  const [updatedAt, setUpdatedAt] = useState('')
  /* Sekündlich hochgezählt, damit die Restgültigkeit des Plans tickt, statt
     bis zum nächsten Abruf einzufrieren. */
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(async () => {
    try {
      setStates(await api.energyPilot())
      setUpdatedAt(new Date().toLocaleTimeString('de-DE'))
      setLoadError('')
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [load])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  return { states, loadError, updatedAt, now }
}

/** Kopfzeile, Lade- und Fehlerzustand, gleich für alle Unterseiten des Bereichs.
    Der Inhalt wird erst gerendert, wenn Daten vorliegen. */
export function EnergyPilotPage({ subtitle, states, loadError, updatedAt, children }: {
  subtitle: string
  states: HaEntities | null
  loadError: string
  updatedAt: string
  children: (states: HaEntities) => ReactNode
}) {
  return (
    <>
      <PageHeader title="Energy Pilot" subtitle={subtitle} />
      <div className="content">
        {!states ? (
          loadError
            ? <div className="alert">Energy-Pilot-Daten nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>
        ) : (
          <>
            {loadError ? <div className="alert">Aktualisierung fehlgeschlagen: {loadError}</div> : null}
            {children(states)}
            <div className="meta-line">{updatedAt ? `Aktualisiert: ${updatedAt}` : 'Warte auf Daten…'}</div>
          </>
        )}
      </div>
    </>
  )
}
