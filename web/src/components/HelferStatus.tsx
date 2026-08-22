import type { ControlGroup, EntityDiagnostic } from '../types'

/* Zeigt die abgeleiteten HA-Helfer eines Geräts mit ihrem tatsächlichen
   Zustand. Die Entity-IDs kommen aus dem Steuerschema des Servers, nicht aus
   einer im Frontend nachgebauten Namenskonvention — zwei Quellen dafür liefen
   auseinander. Der Zustand kommt aus entity_diagnostics des letzten Zyklus. */

const ZUSTAND: Record<string, { text: string; ton: string }> = {
  valid:        { text: 'vorhanden',              ton: 'ok' },
  missing:      { text: 'fehlt',                  ton: 'err' },
  unavailable:  { text: 'nicht verfügbar',        ton: 'warn' },
  invalid:      { text: 'ungültig',               ton: 'warn' },
  write_failed: { text: 'Schreiben fehlgeschlagen', ton: 'err' },
}

const QUELLE: Record<string, string> = {
  ha: 'HA-Wert wirkt',
  addon: 'Add-on-Wert wirkt',
  internal: 'interner Default wirkt',
}

export function HelferStatus({
  group, diagnostics, writeError,
}: {
  group: ControlGroup | undefined
  diagnostics: Record<string, EntityDiagnostic> | undefined
  writeError?: string | null
}) {
  if (!group) {
    return (
      <p className="hint-box">
        Die abgeleiteten HA-Helfer erscheinen hier, sobald das Gerät gespeichert und das Add-on neu
        gestartet wurde.
      </p>
    )
  }

  const schreibziele = [group.request_entity, group.mode_entity].filter(Boolean) as string[]
  const eintraege = [
    ...schreibziele.map((entity) => ({ entity, label: 'Anforderung (Schreibziel)' })),
    ...group.items.map((item) => ({ entity: item.entity, label: item.label })),
  ]

  return (
    <>
      {writeError ? (
        <div className="alert">Letzter Schreibversuch fehlgeschlagen: {writeError}</div>
      ) : null}
      <div className="helper-list">
        {eintraege.map(({ entity, label }) => {
          const diagnose = diagnostics?.[entity]
          const zustand = diagnose ? ZUSTAND[diagnose.state] : null
          return (
            <div className="ctrl-row" key={entity}>
              <span className="k">
                {label}
                <span className="mono helper-entity">{entity}</span>
              </span>
              <div className="ctrl-value">
                {diagnose ? <span className="pill muted">{QUELLE[diagnose.source]}</span> : null}
                <span className={`pill ${zustand?.ton ?? 'muted'}`}>
                  {zustand?.text ?? 'nicht gelesen'}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}
