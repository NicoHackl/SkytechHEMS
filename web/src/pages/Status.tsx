import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { DeviceCard, KeyValue, type CardState } from '../components/DeviceCard'
import { Icon } from '../components/Icon'
import { fmtDur, fmtW, modeLabel } from '../format'
import type { BinaryDevice, ControllableDevice, CycleStatus, StatusResponse } from '../types'

/* Live-Anzeige des letzten Regelzyklus.

   Zwei Takte: alle 5 s wird /api/status geholt, jede Sekunde wird nur neu
   gerendert. Der Regelzyklus laeuft je nach Konfiguration nur alle 30 s —
   ohne den zweiten Takt blieben die Restzeiten dazwischen eingefroren.
   `elapsed` ist die Zeit seit dem Eintreffen des Schnappschusses und wird von
   allen serverseitigen Restzeiten abgezogen. */

const POLL_MS = 5000

export function Status() {
  const [data, setData] = useState<StatusResponse | null>(null)
  const [receivedAt, setReceivedAt] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [connectionError, setConnectionError] = useState('')

  const load = useCallback(async () => {
    try {
      const response = await api.status()
      setData(response)
      setReceivedAt(Date.now())
      setElapsed(0)
      setConnectionError('')
    } catch (error) {
      setConnectionError((error as Error).message)
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(timer)
  }, [load])

  useEffect(() => {
    if (!receivedAt) return
    const timer = window.setInterval(() => setElapsed((Date.now() - receivedAt) / 1000), 1000)
    return () => window.clearInterval(timer)
  }, [receivedAt])

  if (!data) {
    return (
      <>
        <PageHeader title="Status" subtitle="Letzter Regelzyklus" />
        <div className="content">
          {connectionError
            ? <div className="alert">Verbindungsfehler: {connectionError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  // Vor dem ersten abgeschlossenen Zyklus liefert das Add-on ein leeres Objekt.
  const cycle: CycleStatus | null = 'ems_enabled' in data.status ? (data.status as CycleStatus) : null
  const devices = cycle?.devices ?? []
  const controllable = devices.filter((d): d is ControllableDevice => d.type === 'controllable')
  const binary = devices.filter((d): d is BinaryDevice => d.type === 'binary')

  const subtitle = `Letzter Zyklus: ${data.last_cycle_at || '–'} · Zyklen: ${data.cycle_count} · Intervall: ${data.interval_s}s`

  return (
    <>
      <PageHeader
        title="Status"
        subtitle={subtitle}
        actions={connectionError
          ? <span className="pill err">Keine Verbindung</span>
          : <span className="pill ok">Live</span>}
      />

      <div className="content">
        {connectionError ? <div className="alert">Verbindungsfehler: {connectionError}</div> : null}
        {data.error ? <div className="alert">Letzter Zyklus fehlgeschlagen: {data.error}</div> : null}

        {cycle ? (
          <>
            <div className="pill-row">
              <span className={cycle.ems_enabled ? 'pill ok' : 'pill muted'}>
                {cycle.ems_enabled ? 'EMS aktiv' : 'EMS inaktiv'}
              </span>
              <span className="pill primary">Modus: {modeLabel(cycle.global_mode)}</span>
              {cycle.hard_lockout ? <span className="pill err">Sperre – Überschuss-Sensor ungültig</span> : null}
              {cycle.binary_immediate_off ? <span className="pill err">Notabschaltung</span> : null}
              {!cycle.residual_sensor_valid && !cycle.hard_lockout
                ? <span className="pill warn">Überschuss-Sensor liefert keinen Wert</span>
                : null}
            </div>

            <div className="tiles">
              <div className="tile static">
                <div className="tile-icon"><Icon name="sun" /></div>
                <h3>Überschuss</h3>
                <div className={cycle.residual_w < 0 ? 'num warn' : 'num ok'}>{fmtW(cycle.residual_w)}</div>
                <p>Netzeinspeisung laut Sensor</p>
              </div>
              <div className="tile static">
                <div className="tile-icon"><Icon name="spark" /></div>
                <h3>EMS-Pool</h3>
                <div className="num">{fmtW(cycle.pool_w)}</div>
                <p>Verteilbare Leistung</p>
              </div>
              {cycle.current_deficit_w > 0 ? (
                <div className="tile static">
                  <div className="tile-icon"><Icon name="warning" /></div>
                  <h3>Defizit</h3>
                  <div className="num warn">{fmtW(cycle.current_deficit_w)}</div>
                  <p>Netzbezug, wird abgeregelt</p>
                </div>
              ) : null}
              <div className="tile static">
                <div className="tile-icon"><Icon name="plug" /></div>
                <h3>Binär gesamt</h3>
                <div className="num">{fmtW(cycle.binary_total_w)}</div>
                <p>Angeforderte Schaltlast</p>
              </div>
            </div>
          </>
        ) : null}

        <div className="section-title"><Icon name="sliders" size={14} />Regelbare Verbraucher</div>
        {controllable.length ? (
          <div className="device-grid">
            {controllable.map((device) => <ControllableCard key={device.id} device={device} elapsed={elapsed} />)}
          </div>
        ) : (
          <div className="card"><div className="empty">Keine regelbaren Verbraucher konfiguriert.</div></div>
        )}

        <div className="section-title"><Icon name="plug" size={14} />Binäre Verbraucher</div>
        {binary.length ? (
          <div className="device-grid">
            {binary.map((device) => <BinaryCard key={device.id} device={device} elapsed={elapsed} />)}
          </div>
        ) : (
          <div className="card"><div className="empty">Keine binären Verbraucher konfiguriert.</div></div>
        )}
      </div>
    </>
  )
}

function PriorityBadge({ device }: { device: { priority: number; source: string } }) {
  return (
    <>
      {device.source === 'ep' ? <span className="pill primary">Energy Pilot</span> : null}
      <span className="pill">Prio {device.priority}</span>
    </>
  )
}

function ControllableCard({ device, elapsed }: { device: ControllableDevice; elapsed: number }) {
  const state: CardState = !device.eligible ? 'off' : device.new_w > 0 ? 'active' : 'idle'
  const changed = Math.round(device.new_w) !== Math.round(device.anforderung_current_w)
  const isAmpere = device.output_unit === 'ampere'

  // Der aktuelle Sollwert steht immer in Watt; fuer die Anzeige in Ampere wird
  // ueber Phasen x Spannung zurueckgerechnet, genau wie beim Schreiben.
  const phases = isAmpere ? device.current_phases ?? 1 : 1
  const voltageL1 = device.voltage_l1 ?? 230
  const voltageL2 = device.voltage_l2 ?? 230
  const voltageL3 = device.voltage_l3 ?? 230
  const effectiveVoltage = isAmpere ? (phases === 1 ? voltageL1 : voltageL1 + voltageL2 + voltageL3) : 1

  const currentLabel = isAmpere && effectiveVoltage > 0
    ? `${Math.floor(device.anforderung_current_w / effectiveVoltage)} A (${fmtW(device.anforderung_current_w)})`
    : fmtW(device.anforderung_current_w)
  const targetLabel = isAmpere
    ? (device.new_a != null ? `${device.new_a} A (${fmtW(device.new_w)})` : '–')
    : fmtW(device.new_w)

  const multiPhase = isAmpere && (device.allowed_phases?.length ?? 0) > 1
  const phaseLock = multiPhase ? Math.max(0, (device.phase_lock_remaining_s ?? 0) - elapsed) : 0

  return (
    <DeviceCard title={device.label || device.id} badge={<PriorityBadge device={device} />} state={state}>
      <KeyValue label="Freigabe" value={device.eligible ? 'ja' : 'nein'} tone={device.eligible ? 'ok' : 'err'} />
      <KeyValue label="Ist" value={fmtW(device.actual_w)} />
      <KeyValue label="Anforderung" value={currentLabel} />
      <KeyValue label="Zuteilung" value={fmtW(device.alloc_w)} />
      <KeyValue label="Schutz (effektiv)" value={fmtW(device.schutz_w)} tone="muted" />
      {isAmpere ? (
        <KeyValue
          label="Spannung"
          value={phases === 1 ? `L1 ${voltageL1} V` : `L1/L2/L3 ${voltageL1}/${voltageL2}/${voltageL3} V`}
          tone="muted"
        />
      ) : null}
      {multiPhase ? (
        <KeyValue
          label="Phasen"
          value={phaseLock > 0 ? `${phases}-phasig (Sperre ${fmtDur(phaseLock)})` : `${phases}-phasig`}
          tone={phaseLock > 0 ? 'muted' : 'plain'}
        />
      ) : null}
      <KeyValue label="Neu an HA" value={targetLabel} tone={changed ? 'warn' : 'plain'} />
    </DeviceCard>
  )
}

function BinaryCard({ device, elapsed }: { device: BinaryDevice; elapsed: number }) {
  const state: CardState = !device.eligible ? 'off' : device.final_on ? 'active' : 'idle'
  const changed = device.actual_on !== device.final_on
  // Schalter extern an, ohne HEMS-Anforderung: Fremdsteuerung ("Force-Modus").
  const externallyOn = device.actual_on && !device.anforderung_an

  const runtimeRow = device.actual_on && device.min_runtime_s > 0
    ? remainingRow('Mindestlaufzeit', device.min_runtime_s - device.switch_age_s - elapsed)
    : !device.actual_on && device.min_offtime_s > 0
      ? remainingRow('Mindestauszeit', device.min_offtime_s - device.switch_age_s - elapsed)
      : null

  const offDelay = device.off_delay_remaining_s

  return (
    <DeviceCard title={device.label || device.id} badge={<PriorityBadge device={device} />} state={state}>
      <KeyValue label="Freigabe" value={device.eligible ? 'ja' : 'nein'} tone={device.eligible ? 'ok' : 'err'} />
      <KeyValue label="Leistung" value={fmtW(device.power_w)} />
      <KeyValue label="Ist" value={device.actual_on ? 'AN' : 'AUS'} tone={device.actual_on ? 'ok' : 'err'} />
      {externallyOn ? (
        <KeyValue label="Fremdsteuerung" value="extern AN – zählt nicht zum Pool" tone="warn" />
      ) : null}
      <KeyValue label="Gewünscht" value={device.desired_on ? 'AN' : 'AUS'} tone={device.desired_on ? 'ok' : 'muted'} />
      <KeyValue label="Kandidat" value={device.candidate_on ? 'AN' : 'AUS'} tone={device.candidate_on ? 'ok' : 'muted'} />
      <KeyValue
        label="Final an HA"
        value={device.final_on ? 'AN' : 'AUS'}
        tone={changed ? 'warn' : device.final_on ? 'ok' : 'err'}
      />
      {runtimeRow}
      {offDelay != null ? remainingRow('Abschaltverzögerung', offDelay - elapsed, 'abschalten') : null}
    </DeviceCard>
  )
}

/** Zeile mit herunterlaufender Restzeit; ist sie abgelaufen, steht dort der Folgezustand. */
function remainingRow(label: string, remaining: number, doneLabel = 'erfüllt') {
  return remaining > 0
    ? <KeyValue label={label} value={`noch ${fmtDur(remaining)}`} tone="muted" />
    : <KeyValue label={label} value={doneLabel} tone="ok" />
}
