import { useEffect, type ReactNode } from 'react'
import { ConfigActions, RestartOverlay } from '../components/ConfigActions'
import { useConfigDraft } from '../components/ConfigDraft'
import { Field, NumberField, TextField } from '../components/ConfigFields'
import { KeyValue } from '../components/DeviceCard'
import { TariffPage, useTariffStatus } from '../components/TariffShared'
import type { TariffInsight } from '../types'

/* Speicherung in Skytech Data Insight (D-065, Vertrag contract_hems_data_insight 0.2):
   oben der Zustand der gespeicherten Konfiguration, unten die Verbindung als Teil
   des gemeinsamen Konfigurationsentwurfs – wirkt nach „Speichern und neu starten“. */

export function StrompreisDataInsight() {
  const { data, draft, loadError, fieldErrors, restarting, ensureLoaded, patch } = useConfigDraft()
  const { status, statusError } = useTariffStatus()

  useEffect(ensureLoaded, [ensureLoaded])

  let form: ReactNode
  if (!data || !draft) {
    form = loadError
      ? <div className="alert">Konfiguration nicht verfügbar: {loadError}</div>
      : <div className="center"><div className="spinner" /></div>
  } else {
    const passwordSet = data.secrets_set?.insight_password ?? false
    form = (
      <>
        <section className="card">
          <div className="card-head"><h2>Skytech Data Insight</h2></div>
          <div className="card-body">
            <p className="hint-box">
              Speichert Preise, Prognosen und die Grundlast über den Datenbankbenutzer{' '}
              <span className="mono">skytech_hems</span>. Das Passwort erzeugt Data Insight auf der Seite
              „Zugänge“ (Karte „Skytech HEMS – Datenbank (intern)“). Ohne Passwort bleibt die Speicherung aus.
            </p>
            <div className="form-grid">
              <TextField
                label="Host" required mono
                value={draft.insight_host} placeholder="auto"
                error={fieldErrors.insight_host}
                hint="auto sucht das Add-on über den Supervisor."
                onChange={(next) => patch({ insight_host: next })}
              />
              <NumberField
                label="Port" required
                value={draft.insight_port} min={1} max={65535} step={1}
                error={fieldErrors.insight_port}
                onChange={(next) => patch({ insight_port: next ?? 5432 })}
              />
              <Field
                label="Passwort" wide error={fieldErrors.insight_password}
                hint={draft.insight_password === null
                  ? 'Wird beim Speichern entfernt.'
                  : (passwordSet ? 'Gespeichert. Leer lassen, um es zu behalten.' : 'Noch nicht gesetzt.')}
              >
                <div className="inline-actions">
                  <input
                    type="password" className="mono" autoComplete="new-password"
                    value={draft.insight_password ?? ''}
                    placeholder={passwordSet ? '•••••••• (gespeichert)' : ''}
                    disabled={draft.insight_password === null}
                    onChange={(event) => patch({ insight_password: event.target.value })}
                  />
                  {passwordSet && draft.insight_password !== null ? (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => patch({ insight_password: null })}>
                      Entfernen
                    </button>
                  ) : null}
                  {draft.insight_password === null ? (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => patch({ insight_password: '' })}>
                      Rückgängig
                    </button>
                  ) : null}
                </div>
              </Field>
            </div>
          </div>
        </section>

        <ConfigActions />
      </>
    )
  }

  return (
    <TariffPage subtitle="Speicherung in Data Insight" statusError={statusError}>
      {restarting ? <RestartOverlay /> : null}
      {status?.aktiv && status.insight ? <InsightCard insight={status.insight} /> : null}
      {form}
    </TariffPage>
  )
}

function InsightCard({ insight }: { insight: TariffInsight }) {
  const pill = !insight.konfiguriert
    ? <span className="pill muted">Aus</span>
    : (insight.verbunden ? <span className="pill ok">Verbunden</span> : <span className="pill err">Nicht verbunden</span>)
  return (
    <section className="card">
      <div className="card-head">
        <h2>Speicherung in Data Insight</h2>
        <div className="spacer" />
        {pill}
      </div>
      <div className="card-body">
        {insight.grund ? <KeyValue label="Grund" value={insight.grund} tone={insight.konfiguriert ? 'err' : 'muted'} /> : null}
        {insight.host ? <KeyValue label="Host" value={<span className="mono">{insight.host}</span>} tone="muted" /> : null}
        <KeyValue label="Letzter Abgleich" value={insight.letzter_abgleich ?? '–'} tone="muted" />
        <KeyValue label="Letzter Preislauf" value={insight.letzter_preislauf ?? '–'} />
        <KeyValue label="Letzter PV-Lauf" value={insight.letzter_pv_lauf ?? '–'} />
        <KeyValue label="Letzte Verbrauchsprognose" value={insight.letzter_verbrauchslauf ?? '–'} />
        <KeyValue label="Letzte Auswertung" value={insight.letzte_auswertung ?? '–'} />
        <KeyValue
          label="Grundlast bis"
          value={insight.grundlast_grund ?? insight.grundlast_bis ?? '–'}
          tone={insight.grundlast_grund ? 'warn' : 'plain'}
        />
        {insight.hinweise.map((hint) => <KeyValue key={hint} label="Hinweis" value={hint} tone="warn" />)}
      </div>
      {insight.rollen.length ? (
        <div className="table-wrap">
          <table className="data readonly">
            <thead><tr><th>Rolle</th><th>Entität</th><th>Sensor-ID</th></tr></thead>
            <tbody>
              {insight.rollen.map((role) => (
                <tr key={role.rolle}>
                  <td className="mono">{role.rolle}</td>
                  <td className="mono">{role.entity}</td>
                  <td>{role.sensor_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
