import { Icon } from '../components/Icon'
import { TariffPage, formatPrice, useTariffStatus } from '../components/TariffShared'

/* Kommende Preise des dynamischen Strompreises (D-065) als Tabelle. */

const SHOWN_SLOTS = 24

export function StrompreisPreise() {
  const { status, statusError } = useTariffStatus()
  const price = status?.preis ?? null

  return (
    <TariffPage subtitle="Kommende Preise" statusError={statusError}>
      {!status && !statusError ? <div className="center"><div className="spinner" /></div> : null}

      {status && price?.gueltig && price.kommend?.length ? (
        <section className="card">
          <div className="card-head">
            <h2>Kommende Preise</h2>
            <div className="spacer" />
            <span className="pill muted">
              {Math.min(SHOWN_SLOTS, price.kommend.length)} von {price.kommend_gesamt} Slots
            </span>
          </div>
          <div className="table-wrap">
            <table className="data readonly">
              <thead>
                <tr><th>Tag</th><th>Zeit</th><th>Preis</th><th /></tr>
              </thead>
              <tbody>
                {price.kommend.slice(0, SHOWN_SLOTS).map((slot) => (
                  <tr key={slot.von_iso}>
                    <td>{slot.tag}</td>
                    <td className="mono">{slot.von}–{slot.bis}</td>
                    <td>{formatPrice(slot.preis)}</td>
                    <td>
                      {slot.von_iso === price.guenstigster?.von_iso ? <span className="pill ok">günstigster</span> : null}
                      {slot.von_iso === price.teuerster?.von_iso ? <span className="pill warn">teuerster</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {status && !(price?.gueltig && price.kommend?.length) ? (
        <div className="card">
          <div className="empty">
            <Icon name="plug" size={40} />
            <p>Keine gültigen Preise.</p>
            <span>{!status.aktiv ? 'Das Modul ist ausgeschaltet.' : (price?.grund ?? 'Der Preissensor liefert keine kommenden Slots.')}</span>
          </div>
        </div>
      ) : null}
    </TariffPage>
  )
}
