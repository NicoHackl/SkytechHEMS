import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'
import { PageHeader } from './Layout'
import type { TariffSlot, TariffStatus, TariffWindow } from '../types'

/* Gemeinsame Bausteine der Unterseiten „Dynamischer Strompreis“ (D-065).

   Der Bereich ist in Übersicht, Preise, Netzladen, Data Insight und Quellen
   aufgeteilt. Die Zustandsseiten lesen api/tariff/status (Zustand der
   GESPEICHERTEN Konfiguration), Data Insight und Quellen schreiben zusätzlich in
   den gemeinsamen Konfigurationsentwurf. Kurven zeichnet Grafana (Data Insight). */

const POLL_MS = 30000

export const INTERVAL_LABELS: Record<string, string> = {
  auto: 'automatisch aus der Kurve',
  '15': '15 Minuten',
  '60': '60 Minuten',
}

export function formatPrice(price: number): string {
  return `${(price * 100).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ct/kWh`
}

export function formatKwh(value: number | null): string {
  return value === null ? '–' : `${value.toLocaleString('de-DE', { maximumFractionDigits: 2 })} kWh`
}

export function windowText(window: TariffWindow | null | undefined): string {
  return window ? `${window.von}–${window.bis} · ${formatPrice(window.preis_mittel)}` : '–'
}

export function formatHours(value: number | null | undefined): string {
  return value === null || value === undefined
    ? '–'
    : `${value.toLocaleString('de-DE', { maximumFractionDigits: 1 })} h`
}

export function slotText(slot: TariffSlot | undefined): string {
  return slot ? `${slot.tag} ${slot.von}–${slot.bis} · ${formatPrice(slot.preis)}` : '–'
}

/** Zustand des Moduls, alle 30 s neu abgerufen. Jede Unterseite pollt selbst –
    es ist immer nur eine montiert. */
export function useTariffStatus() {
  const [status, setStatus] = useState<TariffStatus | null>(null)
  const [statusError, setStatusError] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        setStatus(await api.tariffStatus())
        setStatusError('')
      } catch (error) {
        setStatusError((error as Error).message)
      }
    }
    void load()
    const timer = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(timer)
  }, [])

  return { status, statusError }
}

/** Kopfzeile und Inhaltsspalte, gleich für alle Unterseiten des Bereichs. */
export function TariffPage({ subtitle, statusError, children }: {
  subtitle: string
  statusError?: string
  children: ReactNode
}) {
  return (
    <>
      <PageHeader title="Dynamischer Strompreis" subtitle={subtitle} />
      <div className="content form-content">
        {statusError ? <div className="alert">Zustand nicht abrufbar: {statusError}</div> : null}
        {children}
      </div>
    </>
  )
}

export function StatePill({ active, valid }: { active: boolean; valid: boolean }) {
  if (!active) return <span className="pill muted">Aus</span>
  return valid ? <span className="pill ok">Preise gültig</span> : <span className="pill err">Preise ungültig</span>
}
