import type { ReactNode } from 'react'

/* Gemeinsame Darstellung einer Gerätekarte. Status- und Energy-Pilot-Seite
   zeigen dieselbe Form: Titel, optionaler Prioritäts-Pill, darunter
   Kennzahlzeilen. Die Farbe des linken Rands sagt, ob das Gerät läuft. */

export type CardState = 'active' | 'idle' | 'off'
export type ValueTone = 'ok' | 'warn' | 'err' | 'muted' | 'plain'

/** Eine Kennzahlzeile: Bezeichnung links, Wert rechts. */
export function KeyValue({ label, value, tone = 'plain' }: { label: string; value: ReactNode; tone?: ValueTone }) {
  return (
    <div className="kv-row">
      <span className="k">{label}</span>
      <span className={tone === 'plain' ? 'v' : `v ${tone}`}>{value}</span>
    </div>
  )
}

export function DeviceCard({
  title,
  badge,
  state,
  children,
}: {
  title: string
  badge?: ReactNode
  state: CardState
  children: ReactNode
}) {
  return (
    <article className={`card device-card ${state}`}>
      <div className="card-head">
        <h2>{title}</h2>
        <div className="spacer" />
        {badge}
      </div>
      <div className="card-body">{children}</div>
    </article>
  )
}
