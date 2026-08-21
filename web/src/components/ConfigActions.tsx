import { Icon } from './Icon'
import { useConfigDraft } from './ConfigDraft'

/* Klebrige Aktionsleiste der Konfigurationsseiten.

   Genau eine Primäraktion: „Speichern und neu starten" — das ist der Weg, den
   der Nutzer meint, wenn er etwas geändert hat. Die beiden Teilschritte bleiben
   als klar sichtbare Nebenaktionen erreichbar, weil sie verschiedene Wirkungen
   haben und die Trennung sonst nicht bedienbar wäre. */

export function ConfigActions() {
  const { data, dirty, busy, conflict, save, restart, saveAndRestart, discard, reload }
    = useConfigDraft()
  if (!data) return null

  const gesperrt = busy !== ''
  const nurLesen = !data.can_save

  const bestaetigeVerwerfen = () => {
    if (!dirty) return true
    return window.confirm(
      'Es gibt ungespeicherte Änderungen. Ein Neustart verwirft sie. Trotzdem neu starten?',
    )
  }

  return (
    <>
      {conflict ? (
        <div className="alert">
          Die Add-on-Konfiguration wurde zwischenzeitlich an anderer Stelle geändert — etwa über
          die native Add-on-Seite. Der Entwurf bleibt erhalten.{' '}
          <button type="button" onClick={() => void reload()}>Gespeicherten Stand laden</button>{' '}
          verwirft ihn und zeigt den aktuellen Stand.
        </div>
      ) : null}

      {nurLesen ? (
        <div className="hint-box">
          {data.supervisor_available
            ? `Der Supervisor antwortet gerade nicht: ${data.supervisor_error} Speichern und
               Neustarten sind deshalb deaktiviert.`
            : `Das Add-on läuft außerhalb von Home Assistant. Ohne Supervisor-Zugang ist die
               Konfiguration schreibgeschützt — angezeigt wird der zuletzt gelesene Stand.`}
        </div>
      ) : null}

      <div className="form-footer">
        <div className="config-state">
          {dirty ? (
            <span className="pill warn"><Icon name="edit" size={13} />Ungespeicherte Änderungen</span>
          ) : data.restart_required ? (
            <span className="pill warn"><Icon name="refresh" size={13} />Neustart ausstehend</span>
          ) : (
            <span className="pill ok"><Icon name="check" size={13} />Gespeicherter Stand ist aktiv</span>
          )}
          {dirty ? (
            <button type="button" className="btn btn-ghost btn-sm"
                    disabled={gesperrt} onClick={discard}>
              Änderungen verwerfen
            </button>
          ) : null}
        </div>

        <div className="spacer" />

        <button type="button" className="btn btn-ghost"
                disabled={gesperrt || nurLesen || !dirty}
                onClick={() => void save()}>
          {busy === 'save' ? 'Speichern…' : 'Speichern'}
        </button>
        <button type="button" className="btn btn-ghost"
                disabled={gesperrt || !data.can_restart}
                onClick={() => { if (bestaetigeVerwerfen()) void restart() }}>
          {busy === 'restart' ? 'Neu starten…' : 'Neu starten'}
        </button>
        <button type="button" className="btn btn-primary"
                disabled={gesperrt || nurLesen}
                onClick={() => void saveAndRestart()}>
          {busy === 'save-restart' ? 'Speichern und neu starten…' : 'Speichern und neu starten'}
        </button>
      </div>

      <p className="meta-line">
        Speichern allein ändert die laufende Regelung nicht — sie arbeitet bis zum Neustart mit dem
        Stand, mit dem das Add-on gestartet wurde.
      </p>
    </>
  )
}

/** Nicht interaktiver Neustartzustand. Wartet auf eine neue Prozessinstanz. */
export function RestartOverlay() {
  return (
    <div className="modal-backdrop" role="alertdialog" aria-live="assertive"
         aria-label="Add-on startet neu">
      <div className="modal restart-modal">
        <div className="modal-body">
          <div className="center"><div className="spinner" /></div>
          <h2>Add-on startet neu</h2>
          <p>
            Die betroffenen Geräte wurden vorher sicher abgeschaltet. Sobald sich eine neue
            Prozessinstanz meldet, lädt die Oberfläche den neuen Stand von selbst.
          </p>
        </div>
      </div>
    </div>
  )
}
