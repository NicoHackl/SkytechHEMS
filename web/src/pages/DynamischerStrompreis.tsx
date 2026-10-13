import { useEffect, useState } from 'react'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { ConfigActions, RestartOverlay } from '../components/ConfigActions'
import { useConfigDraft } from '../components/ConfigDraft'
import { EntityField, Field, NumberField, SelectField, TextField } from '../components/ConfigFields'
import { KeyValue } from '../components/DeviceCard'
import type {
  ConfigDevice, TariffEnergy, TariffFigures, TariffGridCharging, TariffInsight, TariffLoad, TariffSlot,
  TariffStatus, TariffStorage, TariffWindow,
} from '../types'

/* Dynamischer Strompreis (D-065, Phasen P3 bis P5): Quellen einstellen und prüfen,
   Speicherung in Skytech Data Insight (Vertrag contract_hems_data_insight 0.2),
   Verbrauchsprognose, Reichweite, Kennzahlen und Netzlade-Freigabe.

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

function windowText(window: TariffWindow | null | undefined): string {
  return window ? `${window.von}–${window.bis} · ${formatPrice(window.preis_mittel)}` : '–'
}

function formatHours(value: number | null | undefined): string {
  return value === null || value === undefined
    ? '–'
    : `${value.toLocaleString('de-DE', { maximumFractionDigits: 1 })} h`
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
  const passwordSet = data.secrets_set?.insight_password ?? false
  const batteries = draft.devices
    .map((device, index) => ({ device, index }))
    .filter(({ device }) => device.class === 'battery')
  const setDeviceField = (index: number, changes: Partial<ConfigDevice>) => patch({
    devices: draft.devices.map((device: ConfigDevice, i) => (i === index ? { ...device, ...changes } : device)),
  })

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

        {status?.aktiv && status.verbrauch && status.speicher ? (
          <ReachCard load={status.verbrauch} storage={status.speicher} figures={status.kennzahlen ?? {}} />
        ) : null}

        {status?.aktiv && status.netzladen ? <GridChargingCard grid={status.netzladen} /> : null}

        {status?.aktiv && status.insight ? <InsightCard insight={status.insight} /> : null}

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
              <EntityField
                label="PV-Leistung (Ist)"
                value={draft.pv_actual_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.pv_actual_entity}
                hint="Gemessene PV-Leistung in W – Vergleich mit der Prognose in Data Insight."
                onChange={(next) => patch({ pv_actual_entity: next })}
              />
              <EntityField
                label="Hausverbrauch (Leistung)"
                value={draft.tariff_house_load_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.tariff_house_load_entity}
                hint="Gesamter Hausverbrauch in W, z. B. sensor.e3dc_leistung_haus_modbus. Grundlage der Grundlast."
                onChange={(next) => patch({ tariff_house_load_entity: next })}
              />
            </div>

            <div className="section-title">Grundlast</div>
            <p className="hint-box">
              Grundlast = Hausverbrauch − Istleistung aller HEMS-Verbraucher − Leistung der Speicher, die im
              Hausverbrauch-Sensor stecken (Laden erhöht ihn, Entladen senkt ihn). Das HEMS rechnet sie je
              Viertelstunde aus den in Data Insight aufgezeichneten Werten.
            </p>
            {batteries.length === 0 ? <p className="muted">Keine Speicher konfiguriert.</p> : null}
            {batteries.map(({ device, index }) => (
              <label className="switch" key={device.name}>
                <input
                  type="checkbox"
                  checked={device.tariff_in_house_load ?? false}
                  onChange={(event) => setDeviceField(index, { tariff_in_house_load: event.target.checked })}
                />
                <span className="track" />
                <span className="switch-label">{device.label || device.name}: steckt im Hausverbrauch-Sensor</span>
              </label>
            ))}

            <div className="section-title">Wirkungsgrade der Speicher</div>
            <p className="hint-box">
              Für die Reichweite: Wie viel der gespeicherten Energie kommt im Haus an (Entladen) und wie viel
              Überschuss landet im Speicher (Laden). Startwert 0,92. Kapazität und SoC-Grenzen kommen aus den
              Speichereinstellungen.
            </p>
            {batteries.map(({ device, index }) => (
              <div className="form-grid" key={`eta-${device.name}`}>
                <NumberField
                  label={`${device.label || device.name}: Laden`} min={0.5} max={1} step={0.01}
                  value={device.tariff_efficiency_charge ?? 0.92}
                  error={fieldErrors[`devices[${index}].tariff_efficiency_charge`]}
                  onChange={(next) => setDeviceField(index, { tariff_efficiency_charge: next })}
                />
                <NumberField
                  label={`${device.label || device.name}: Entladen`} min={0.5} max={1} step={0.01}
                  value={device.tariff_efficiency_discharge ?? 0.92}
                  error={fieldErrors[`devices[${index}].tariff_efficiency_discharge`]}
                  onChange={(next) => setDeviceField(index, { tariff_efficiency_discharge: next })}
                />
              </div>
            ))}
          </div>
        </section>

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

function reachText(reach: TariffStorage['median']): string {
  if (!reach) return '–'
  return reach.ueber_horizont ? `über ${reach.horizont_bis ?? 'den Horizont'} hinaus` : (reach.bis ?? '–')
}

function ReachCard({ load, storage, figures }: { load: TariffLoad; storage: TariffStorage; figures: TariffFigures }) {
  return (
    <section className="card">
      <div className="card-head">
        <h2>Verbrauch und Reichweite</h2>
        <div className="spacer" />
        {storage.grund ? <span className="pill muted">Keine Reichweite</span> : <span className="pill ok">Berechnet</span>}
      </div>
      <div className="card-body">
        <p className="hint-box">
          Reine Anzeige zur Vorbereitung der Steuerung. Verbrauchsprognose aus der Grundlast der letzten 28 Tage
          (Werktag, Samstag, Sonntag; jüngere Tage zählen mehr). Reichweite aller Speicher zusammen mit PV- und
          Verbrauchsprognose – vorsichtig heißt hoher Verbrauch und wenig PV.
        </p>
        {load.gueltig ? (
          <>
            <KeyValue label="Verbrauch bis Ende morgen" value={formatKwh(load.bis_ende_morgen_kwh ?? null)} />
            <KeyValue
              label="Nächste 24 h"
              value={`${formatKwh(load.naechste_24h_kwh ?? null)} (Band ${formatKwh(load.naechste_24h_p10_kwh ?? null)}`
                + ` bis ${formatKwh(load.naechste_24h_p90_kwh ?? null)})`}
            />
            <KeyValue label="Historie" value={`${load.historie_tage ?? 0} Tage · ${load.methode ?? ''}`} tone="muted" />
          </>
        ) : <KeyValue label="Verbrauchsprognose" value={load.grund ?? 'nicht verfügbar'} tone="warn" />}

        <KeyValue label="Nutzbar jetzt" value={`${formatKwh(storage.nutzbar_kwh)} von ${formatKwh(storage.nutzbar_max_kwh)}`} />
        {storage.je_speicher.map((battery) => (
          <KeyValue
            key={battery.name}
            label={battery.label}
            value={battery.gueltig
              ? `${battery.soc_prozent?.toLocaleString('de-DE') ?? '–'} % · ${formatKwh(battery.nutzbar_kwh)} nutzbar`
              : (battery.grund ?? 'ungültig')}
            tone={battery.gueltig ? 'muted' : 'warn'}
          />
        ))}
        {storage.grund ? <KeyValue label="Reichweite" value={storage.grund} tone="warn" /> : (
          <>
            <KeyValue label="Reichweite" value={reachText(storage.median)} />
            <KeyValue label="Vorsichtig" value={reachText(storage.vorsichtig)} tone="muted" />
            <KeyValue label="Zuversichtlich" value={reachText(storage.zuversichtlich)} tone="muted" />
          </>
        )}
        {figures.ladeblock_slots !== undefined ? (
          <>
            <div className="section-title">Kennzahlen</div>
            <KeyValue label="Reichweite in Stunden" value={formatHours(figures.reichweite_h)} />
            <KeyValue label="PV bis zur Reichweite" value={formatKwh(figures.pv_im_fenster_kwh ?? null)} />
            <KeyValue label="Netzbezug danach bis zum PV-Überschuss" value={formatKwh(figures.defizit_bis_pv_kwh ?? null)} />
            <KeyValue label="Nächster PV-Überschuss" value={figures.naechster_ueberschuss_ab ?? 'nicht im Horizont'} />
            <KeyValue label="Günstigstes Fenster in der Reichweite" value={windowText(figures.guenstigstes_fenster_reichweite)} />
            <KeyValue label="Günstigstes Fenster gesamt" value={windowText(figures.guenstigstes_fenster_gesamt)} />
            <KeyValue
              label="Preise reichen bis Reichweitenende"
              value={figures.horizont_reicht ? 'ja' : 'nein'}
              tone={figures.horizont_reicht ? 'ok' : 'warn'}
            />
          </>
        ) : null}
        {figures.preis_rang_jetzt_prozent !== undefined ? (
          <KeyValue
            label="Preis jetzt"
            value={`günstiger als ${(100 - figures.preis_rang_jetzt_prozent).toLocaleString('de-DE')} % der kommenden Slots`}
            tone="muted"
          />
        ) : null}
      </div>
    </section>
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
