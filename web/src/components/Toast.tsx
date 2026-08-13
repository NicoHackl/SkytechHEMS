import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

/* Kurzrückmeldung nach einer Aktion. Fehler, die stehen bleiben müssen,
   gehören stattdessen in .alert oder an das betroffene Feld. */

type ToastKind = 'ok' | 'err'
interface ToastItem { id: number; message: string; kind: ToastKind }
interface ToastContextValue { toast: (message: string, kind?: ToastKind) => void }

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const toast = useCallback((message: string, kind: ToastKind = 'ok') => {
    const id = Date.now() + Math.random()
    setItems((current) => [...current, { id, message, kind }])
    window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 4200)
  }, [])

  const value = useMemo(() => ({ toast }), [toast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((item) => <div className={`toast ${item.kind}`} key={item.id}>{item.message}</div>)}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast muss innerhalb des ToastProvider verwendet werden.')
  return context
}
