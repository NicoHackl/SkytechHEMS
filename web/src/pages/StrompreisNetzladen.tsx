import { Icon } from '../components/Icon'
import { KeyValue } from '../components/DeviceCard'
import { TariffPage, useTariffStatus } from '../components/TariffShared'
import type { TariffGridCharging } from '../types'

/* Netzlade-Freigabe des dynamischen Strompreises (D-065, P5) – nur Anzeige. */

export function StrompreisNetzladen() {
  const { status, statusError } = useTariffStatus()

  return (
    <TariffPage subtitle="Netzladen – Freigabe, nur Anzeige" statusError={statusError}>
      {!status && !statusError ? <div className="center"><div className="spinner" /></div> : null}

      {status?.aktiv && status.netzladen ? <GridChargingCard grid={status.netzladen} /> : null}

      {status && !(status.aktiv && status.netzladen) ? (
        <div className="card">
          <div className="empty">
            <Icon name="plug" size={40} />
            <p>Keine Netzlade-Daten.</p>
            <span>{status.aktiv ? 'Das Modul liefert noch keine Freigabe.' : 'Das Modul ist ausgeschaltet.'}</span>
          </div>
        </div>
      ) : null}
    </TariffPage>
  )
}

function SwitchRow({ label, entity, on, present }: { label: string; entity: string; on: boolean; present: boolean }) {
  return (
    <KeyValue
      label={label}
      value={present ? <>{on ? 'an' : 'aus'} · <span className="mono">{entity}</span></>
        : <>Helfer fehlt · <span className="mono">{entity}</span></>}
      tone={present ? (on ? 'ok' : 'muted') : 'warn'}
    />
  )
}

function GridChargingCard({ grid }: { grid: TariffGridCharging }) {
  return (
    <section className="card">
      <div className="card-head">
        <h2>Netzladen</h2>
        <div className="spacer" />
        {grid.zulaessig ? <span className="pill ok">Zulässig</span> : <span className="pill muted">Gesperrt</span>}
      </div>
      <div className="card-body">
        <p className="hint-box">
          Nur Anzeige: Zulässig = Freigabe und (manuell angefordert oder PV reicht nicht). Das PV-Kriterium folgt
          mit der Steuerungslogik. Das HEMS lädt derzeit nie aus dem Netz. Die Schalter sind HA-Helfer
          (input_boolean), die du selbst anlegst.
        </p>
        <KeyValue label="Ergebnis" value={grid.grund} tone={grid.zulaessig ? 'ok' : 'muted'} />
        <SwitchRow label="Freigabe" entity={grid.freigabe_entity} on={grid.freigabe} present={grid.freigabe_vorhanden} />
        <SwitchRow label="Manuell" entity={grid.manuell_entity} on={grid.manuell} present={grid.manuell_vorhanden} />
        <KeyValue label="PV reicht nicht" value={grid.pv_zu_wenig === null ? 'noch nicht festgelegt' : (grid.pv_zu_wenig ? 'ja' : 'nein')} tone="muted" />
        {grid.je_speicher.map((battery) => (
          <SwitchRow
            key={battery.name}
            label={`${battery.label} erlaubt`}
            entity={battery.entity}
            on={battery.erlaubt}
            present={battery.vorhanden}
          />
        ))}
      </div>
    </section>
  )
}
