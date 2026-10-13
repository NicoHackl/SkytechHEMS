import { useEffect, useState } from 'react'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { ConfigActions, RestartOverlay } from '../components/ConfigActions'
import { useConfigDraft } from '../components/ConfigDraft'
import { EntityField, SelectField, TextField } from '../components/ConfigFields'
import { KeyValue } from '../components/DeviceCard'
import type { TariffEnergy, TariffSlot, TariffStatus } from '../types'

/* Dynamischer Strompreis (D-065, Phase P3): Quellen einstellen und prüfen.

   Das Modul erhebt nur Daten und zeigt sie an – es schaltet nichts. Der obere
   Teil zeigt den Zustand der GESPEICHERTEN Konfiguration (api/tariff/status),
   der untere Teil ist Teil des gemeinsamen Konfigurationsentwurfs und wirkt nach
   „Speichern und neu starten“. Kurven zeichnet später Grafana (Data Insight). */

const POLL_MS = 30000
const SHOWN_SLOTS = 24

const INTERVAL_LABELS: Record<string, string> = {
  auto: 'automatisch aus der Kurve',
  '15': '15 Minuten',
  '60': '60 Minuten',
}

function formatPrice(price: number): string {
  return `${(price * 100).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ct/kWh`
}

function formatKwh(value: number | null): string {
  return value === null ? '–' : `${value.toLocaleString('de-DE', { maximumFractionDigits: 2 })} kWh`
}

function slotText(slot: TariffSlot | undefined): string {
  return slot ? `${slot.tag} ${slot.von}–${slot.bis} · ${formatPrice(slot.preis)}` : '–'
}

export function DynamischerStrompreis() {
  const { data, draft, entities, loadError, fieldErrors, restarting, ensureLoaded, patch } = useConfigDraft()
  const [status, setStatus] = useState<TariffStatus | null>(null)
  const [statusError, setStatusError] = useState('')

  useEffect(ensureLoaded, [ensureLoaded])

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

  if (!data || !draft) {
    return (
      <>
        <PageHeader title="Dynamischer Strompreis" subtitle="Preis und PV-Prognose" />
        <div className="content form-content">
          {loadError
            ? <div className="alert">Konfiguration nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  const price = status?.preis ?? null
  const pv = status?.pv ?? null

  return (
    <>
      <PageHeader title="Dynamischer Strompreis" subtitle="Preis und PV-Prognose – Datenerhebung, schaltet nichts" />
      {restarting ? <RestartOverlay /> : null}

      <div className="content form-content">
        {statusError ? <div className="alert">Zustand nicht abrufbar: {statusError}</div> : null}

        <section className="card">
          <div className="card-head">
            <h2>Strompreis</h2>
            <div className="spacer" />
            <StatePill active={status?.aktiv ?? false} valid={price?.gueltig ?? false} />
          </div>
          <div className="card-body">
            {!status?.aktiv ? (
              <p className="hint-box">Ausgeschaltet. Unten einschalten, Preissensor wählen und speichern.</p>
            ) : null}
            {status?.aktiv && price ? (
              <>
                {price.gueltig ? null : <KeyValue label="Grund" value={price.grund ?? 'unbekannt'} tone="err" />}
                {price.warnung ? <KeyValue label="Hinweis" value={price.warnung} tone="warn" /> : null}
                <KeyValue label="Aktueller Preis" value={price.aktuell ? formatPrice(price.aktuell.preis) : '–'} />
                <KeyValue
                  label="Raster"
                  value={price.raster_erkannt_min
                    ? `${price.raster_erkannt_min} min erkannt · Einstellung ${INTERVAL_LABELS[price.raster_einstellung] ?? price.raster_einstellung}`
                    : `Einstellung ${INTERVAL_LABELS[price.raster_einstellung] ?? price.raster_einstellung}`}
                />
                <KeyValue
                  label="Preise bekannt bis"
                  value={price.horizont_bis ? `${price.horizont_bis} (noch ${price.stunden_voraus?.toLocaleString('de-DE')} h)` : '–'}
                />
                <KeyValue
                  label="Preise für morgen"
                  value={price.morgen_vorhanden ? 'vollständig' : 'noch nicht veröffentlicht'}
                  tone={price.morgen_vorhanden ? 'ok' : 'muted'}
                />
                <KeyValue label="Günstigster Slot" value={slotText(price.guenstigster)} tone="ok" />
                <KeyValue label="Teuerster Slot" value={slotText(price.teuerster)} tone="warn" />
                <KeyValue label="Sensor" value={<span className="mono">{price.entity || '–'}</span>} tone="muted" />
                <KeyValue label="Stand" value={status.stand ?? '–'} tone="muted" />
              </>
            ) : null}
          </div>
        </section>

        {price?.gueltig && price.kommend?.length ? (
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

        {status?.aktiv && pv ? (
          <section className="card">
            <div className="card-head"><h2>PV-Prognose</h2></div>
            <div className="card-body">
              <EnergyRow label="Heute" value={pv.heute} />
              <EnergyRow label="Morgen" value={pv.morgen} />
              <EnergyRow label="Rest heute" value={pv.rest_heute} />
              <KeyValue
                label="Prognosekurve"
                value={pv.kurve.gueltig
                  ? `${pv.kurve.raster_min} min, bis ${pv.kurve.bis}`
                  : (pv.kurve.grund ?? 'ungültig')}
                tone={pv.kurve.gueltig ? 'ok' : (pv.kurve.entity ? 'err' : 'muted')}
              />
              {pv.kurve.gueltig && pv.kurve.tage?.length ? (
                <KeyValue
                  label="Kurve je Tag"
                  value={pv.kurve.tage.slice(0, 3).map((day) => `${day.tag}: ${formatKwh(day.kwh)}`).join(' · ')}
                  tone="muted"
                />
              ) : null}
            </div>
          </section>
        ) : null}

        <section className="card">
          <div className="card-head"><h2>Quellen</h2></div>
          <div className="card-body">
            <label className="switch">
              <input
                type="checkbox"
                checked={draft.tariff_enabled}
                onChange={(event) => patch({ tariff_enabled: event.target.checked })}
              />
              <span className="track" />
              <span className="switch-label">Dynamischen Strompreis auswerten</span>
            </label>
            <p className="hint-box">
              Das Modul liest Preis und PV-Prognose im eigenen Minutentakt aus dem Zustand, den der
              Regelzyklus ohnehin holt, und schreibt die Anzeige-Sensoren{' '}
              <span className="mono">sensor.ems_dyn_preis</span> und{' '}
              <span className="mono">sensor.ems_dyn_pv_prognose</span>. Es schaltet kein Gerät.
            </p>
            <div className="form-grid">
              <EntityField
                label="Preissensor" wide required={draft.tariff_enabled}
                value={draft.tariff_price_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.tariff_price_entity}
                hint="Endpreis in €/kWh, Kurve im Attribut data – Format wie sensor.epex_spot_data_total_price_2."
                onChange={(next) => patch({ tariff_price_entity: next })}
              />
              <SelectField
                label="Preisraster" required
                value={draft.tariff_price_interval} options={['auto', '15', '60']} labels={INTERVAL_LABELS}
                error={fieldErrors.tariff_price_interval}
                hint="Weicht der Sensor von einem festen Raster ab, gilt die Kurve als ungültig."
                onChange={(next) => patch({ tariff_price_interval: next })}
              />
              <TextField
                label="Warnung ab" required mono
                value={draft.tariff_tomorrow_warning_time} placeholder="15:00"
                error={fieldErrors.tariff_tomorrow_warning_time}
                hint="Ab dieser Uhrzeit warnen, wenn die Preise für morgen noch fehlen."
                onChange={(next) => patch({ tariff_tomorrow_warning_time: next })}
              />
              <EntityField
                label="PV-Prognose heute"
                value={draft.pv_today_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.pv_today_entity} hint="kWh, z. B. sensor.helios_hausdach_energy_day_1"
                onChange={(next) => patch({ pv_today_entity: next })}
              />
              <EntityField
                label="PV-Prognose morgen"
                value={draft.pv_tomorrow_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.pv_tomorrow_entity} hint="kWh, z. B. sensor.helios_hausdach_energy_day_2"
                onChange={(next) => patch({ pv_tomorrow_entity: next })}
              />
              <EntityField
                label="PV-Prognose Rest heute"
                value={draft.pv_today_remaining_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.pv_today_remaining_entity}
                hint="kWh, z. B. sensor.helios_hausdach_energy_today_remaining"
                onChange={(next) => patch({ pv_today_remaining_entity: next })}
              />
              <EntityField
                label="PV-Prognosekurve"
                value={draft.pv_curve_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.pv_curve_entity}
                hint="Sensor mit der Kurve im Attribut, z. B. sensor.helios_hausdach_power_now"
                onChange={(next) => patch({ pv_curve_entity: next })}
              />
              <TextField
                label="Attribut der Kurve" required mono
                value={draft.pv_curve_attribute} placeholder="forecast"
                error={fieldErrors.pv_curve_attribute}
                hint="Liste von datetime, watts, p10, p90."
                onChange={(next) => patch({ pv_curve_attribute: next })}
              />
            </div>
          </div>
        </section>

        <ConfigActions />
      </div>
    </>
  )
}

function StatePill({ active, valid }: { active: boolean; valid: boolean }) {
  if (!active) return <span className="pill muted">Aus</span>
  return valid ? <span className="pill ok">Preise gültig</span> : <span className="pill err">Preise ungültig</span>
}

function EnergyRow({ label, value }: { label: string; value: TariffEnergy }) {
  if (!value.entity) return <KeyValue label={label} value="nicht konfiguriert" tone="muted" />
  return value.gueltig
    ? <KeyValue label={label} value={formatKwh(value.wert_kwh)} />
    : <KeyValue label={label} value={value.grund ?? 'ungültig'} tone="err" />
}
