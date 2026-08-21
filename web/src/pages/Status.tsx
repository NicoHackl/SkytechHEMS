import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { DeviceCard, KeyValue, type CardState } from '../components/DeviceCard'
import { Icon } from '../components/Icon'
import { fmtDur, fmtW, modeLabel } from '../format'
import type {
  BatteryDevice, BinaryDevice, ControllableDevice, CycleStatus, Device,
  InactiveDeviceIssue, StatusResponse,
} from '../types'

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
  const batteries = devices.filter((d): d is BatteryDevice => d.type === 'battery')

  // Kapazitaetsgewichteter SoC-Schnitt. Ohne hinterlegte Kapazitaet zaehlt jeder
  // Speicher gleich - besser als gar keine Anzeige.
  const socGewicht = batteries.reduce((sum, b) => sum + (b.capacity_kwh || 1), 0)
  const socMittel = socGewicht > 0
    ? batteries.reduce((sum, b) => sum + b.soc_prozent * (b.capacity_kwh || 1), 0) / socGewicht
    : 0
  const speicherNettoW = batteries.reduce((sum, b) => sum + b.netto_w, 0)
  // Weicht die gemessene von der angeforderten HEMS-Last ab, laeuft mindestens
  // ein Geraet fremdgesteuert. Dann ist das Hausdefizit kleiner als der
  // sichtbare Netzbezug - ohne Hinweis sieht das wie ein Regelfehler aus.
  const fremdlastW = cycle ? cycle.hems_last_gemessen_w - cycle.hems_last_w : 0

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
              <span className={cycle.global_mode_configured ? 'pill primary' : 'pill err'}>
                Modus: {modeLabel(cycle.global_mode)}
              </span>
              {!cycle.global_mode_configured ? (
                <span className="pill err">
                  Modus global nicht aktiviert – Zyklus sicher inaktiv
                </span>
              ) : null}
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
                <p>
                  {batteries.length
                    ? `Netzeinspeisung laut Sensor · bereinigt ${fmtW(cycle.residual_bereinigt_w)}`
                    : 'Netzeinspeisung laut Sensor'}
                </p>
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
              {batteries.length ? (
                <>
                  <div className="tile static">
                    <div className="tile-icon"><Icon name="battery" /></div>
                    <h3>Speicher netto</h3>
                    <div className={speicherNettoW < 0 ? 'num ok' : 'num'}>{fmtW(speicherNettoW)}</div>
                    <p>{speicherNettoW < 0 ? 'Speicher liefert' : speicherNettoW > 0 ? 'Speicher lädt' : 'Standby'}</p>
                  </div>
                  <div className="tile static">
                    <div className="tile-icon"><Icon name="battery" /></div>
                    <h3>SoC ⌀</h3>
                    <div className="num">{Math.round(socMittel)} %</div>
                    <p>Kapazitätsgewichtet</p>
                  </div>
                  <div className="tile static">
                    <div className="tile-icon"><Icon name="warning" /></div>
                    <h3>Hausdefizit</h3>
                    <div className={cycle.hausdefizit_w > 0 ? 'num warn' : 'num'}>{fmtW(cycle.hausdefizit_w)}</div>
                    <p>
                      {fremdlastW > 50
                        ? `Ohne ${fmtW(fremdlastW)} fremdgesteuerte HEMS-Last`
                        : 'Hausverbrauch, den der Speicher deckt'}
                    </p>
                  </div>
                </>
              ) : null}
            </div>
          </>
        ) : null}

        {/* Der Speicher steht bewusst zuerst: er beeinflusst die Pool-Rechnung,
            beim Debuggen will man ihn als Erstes sehen. */}
        {batteries.length ? (
          <>
            <div className="section-title"><Icon name="battery" size={14} />Speicher</div>
            <div className="device-grid">
              {batteries.map((device) => <BatteryCard key={device.id} device={device} elapsed={elapsed} />)}
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

        {cycle?.inactive_devices?.length ? (
          <>
            <div className="section-title"><Icon name="warning" size={14} />Beim Start übersprungen</div>
            <div className="device-grid">
              {cycle.inactive_devices.map((issue) => (
                <UebersprungenCard key={`${issue.name}-${issue.index}`} issue={issue} />
              ))}
            </div>
          </>
        ) : null}

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

/* Warum ein Gerät technisch nicht regelbar ist. Das ist etwas anderes als
   „gerade nicht freigegeben" — deshalb eigene Texte und eine eigene Zeile. */
const RUNTIME_LABELS: Record<string, string> = {
  schreibziel_fehlt: 'Schreibziel fehlt in Home Assistant',
  schreibziel_nicht_verfuegbar: 'Schreibziel ist nicht verfügbar',
  schreibziel_ungueltig: 'Schreibziel ist falsch angelegt',
  schreiben_fehlgeschlagen: 'Letzter Schreibversuch fehlgeschlagen',
}

/** Zeile mit dem Laufzeitgrund, sofern das Gerät gerade nicht regelbar ist. */
function RuntimeRow({ device }: { device: Device }) {
  if (device.runtime_active) return null
  const gruende = device.inactive_reasons.map((grund) => RUNTIME_LABELS[grund] ?? grund)
  return (
    <>
      <KeyValue label="Nicht regelbar" value={gruende.join(' · ') || 'unbekannt'} tone="err" />
      {device.write_error ? (
        <KeyValue label="Schreibfehler" value={device.write_error} tone="err" />
      ) : null}
    </>
  )
}

/** Ein Geräteeintrag, der beim Start nicht instanziiert wurde.

    Bewusst ohne Ist-, SoC- oder Schaltwerte: es gibt keine, und erfundene
    Nullwerte sähen aus wie ein laufendes Gerät. */
function UebersprungenCard({ issue }: { issue: InactiveDeviceIssue }) {
  return (
    <DeviceCard
      title={issue.label || issue.name || `Position ${issue.index + 1}`}
      badge={<span className="pill err">Nicht registriert</span>}
      state="off"
    >
      <KeyValue label="Klasse" value={issue.device_class || 'unbekannt'} tone="muted" />
      {Object.entries(issue.errors).map(([feld, text]) => (
        <KeyValue key={feld} label={feld} value={text} tone="err" />
      ))}
    </DeviceCard>
  )
}

function ControllableCard({ device, elapsed }: { device: ControllableDevice; elapsed: number }) {
  const state: CardState = !device.eligible || !device.runtime_active
    ? 'off' : device.new_w > 0 ? 'active' : 'idle'
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
      <RuntimeRow device={device} />
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
  const state: CardState = !device.eligible || !device.runtime_active
    ? 'off' : device.final_on ? 'active' : 'idle'
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
      <RuntimeRow device={device} />
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

/* Sperrgründe des Speichers als deutscher Klartext. Bei sechs Sperrmechanismen
   ist „lädt gerade nicht" sonst nur über die Add-on-Logs erklärbar. */
const BLOCK_LABELS: Record<string, string> = {
  nicht_freigegeben: 'keine Freigabe',
  sensor_ungueltig: 'Sensor liefert nichts',
  betriebsart: 'Betriebsart',
  laden_gesperrt: 'Laden gesperrt',
  entladen_gesperrt: 'Entladen gesperrt',
  soc_min: 'SoC-Minimum erreicht',
  soc_max: 'SoC-Maximum erreicht',
  wr_derating: 'Verfügbare Leistung ist auf 0 W gesetzt',
  netzladen: 'Netzladen aktiv',
  hausdefizit: 'Hausdefizit – Laden gesperrt',
  umschaltsperre: 'Umschaltsperre',
  totzone: 'Totzone um Null',
}

function blockLabel(grund: string | null): string | null {
  return grund ? BLOCK_LABELS[grund] ?? grund : null
}

const BETRIEBSART_LABELS: Record<string, string> = {
  auto: 'Automatik',
  nur_laden: 'Nur Laden',
  nur_entladen: 'Nur Entladen',
  standby: 'Standby',
  laden: 'Laden',
  entladen: 'Entladen',
}

/** Die statischen Speichergrenzen sind nach der Konfigurationsvalidierung immer gültig. */
function limitText(value: number, gueltig: boolean): string {
  return gueltig ? fmtW(value) : 'Konfiguration ungültig'
}

function BatteryCard({ device, elapsed }: { device: BatteryDevice; elapsed: number }) {
  const state: CardState = !device.eligible || !device.runtime_active || !device.sensoren_gueltig
    ? 'off'
    : device.new_lade_w > 0
      ? 'charge'
      : device.new_entlade_w > 0
        ? 'discharge'
        : 'idle'

  // Ein Sollwert, zwei Richtungen: verglichen wird die Nettogroesse.
  const altNetto = device.lade_anforderung_w - device.entlade_anforderung_w
  const changed = Math.round(device.netto_w) !== Math.round(altNetto)
  const istNetto = device.lade_ist_w - device.entlade_ist_w
  const sperre = Math.max(0, device.umschaltsperre_rest_s - elapsed)
  const grund = blockLabel(device.blockiert_grund)
    ?? (device.new_lade_w === 0 && device.new_entlade_w === 0
      ? blockLabel(device.entlade_blockiert_grund) ?? blockLabel(device.lade_blockiert_grund)
      : null)

  return (
    <DeviceCard
      title={device.label || device.id}
      badge={
        <>
          {device.source === 'ep' ? <span className="pill primary">Energy Pilot</span> : null}
          <span className="pill">Laden {device.priority}</span>
          <span className="pill">Entladen {device.entlade_prioritat}</span>
          <span className={device.soc_prozent > device.soc_min_prozent ? 'pill ok' : 'pill warn'}>
            {Math.round(device.soc_prozent)} %
          </span>
        </>
      }
      state={state}
    >
      <SocBar device={device} />
      <KeyValue label="Freigabe" value={device.eligible ? 'ja' : 'nein'} tone={device.eligible ? 'ok' : 'err'} />
      <RuntimeRow device={device} />
      {!device.sensoren_gueltig ? (
        <KeyValue label="Messwerte" value="unvollständig – aus der Regelung" tone="err" />
      ) : null}
      <KeyValue
        label="Betriebsart"
        value={`${BETRIEBSART_LABELS[device.betriebsart] ?? device.betriebsart} → ${
          BETRIEBSART_LABELS[device.betriebsart_effektiv] ?? device.betriebsart_effektiv}`}
      />
      <KeyValue
        label="Ist"
        value={istNetto === 0 ? 'Standby' : `${fmtW(Math.abs(istNetto))} (${istNetto > 0 ? 'Laden' : 'Entladen'})`}
        tone={istNetto < 0 ? 'ok' : 'plain'}
      />
      <KeyValue
        label="Anforderung"
        value={altNetto === 0 ? '0 W' : `${fmtW(Math.abs(altNetto))} (${altNetto > 0 ? 'Laden' : 'Entladen'})`}
      />
      {device.hausdefizit_anteil_w > 0 ? (
        <KeyValue label="Anteil am Hausdefizit" value={fmtW(device.hausdefizit_anteil_w)} />
      ) : null}
      <KeyValue
        label="Limits"
        value={`Laden ≤ ${limitText(device.lade_limit_w, device.lade_limit_gueltig)} · `
               + `Entladen ≤ ${limitText(device.entlade_limit_w, device.entlade_limit_gueltig)}`}
        tone={device.lade_limit_gueltig && device.entlade_limit_gueltig ? 'muted' : 'warn'}
      />
      {device.energie_kwh != null ? (
        <KeyValue
          label="Energie"
          value={`${device.energie_kwh.toLocaleString('de-DE')} von ${device.capacity_kwh.toLocaleString('de-DE')} kWh`}
          tone="muted"
        />
      ) : null}
      {sperre > 0 ? <KeyValue label="Umschaltsperre" value={`noch ${fmtDur(sperre)}`} tone="muted" /> : null}
      {grund ? <KeyValue label="Grund" value={grund} tone="warn" /> : null}
      <KeyValue
        label="Neu an HA"
        value={device.netto_w === 0
          ? 'Standby'
          : `${fmtW(Math.abs(device.netto_w))} (${device.netto_w > 0 ? 'Laden' : 'Entladen'})`}
        tone={changed ? 'warn' : 'plain'}
      />
    </DeviceCard>
  )
}

/** Ladezustand mit Markern für Minimum und Ladeschluss.

    Die Notstromreserve ist ersatzlos entfallen — der Entladeboden ist allein
    soc_min_prozent. */
function SocBar({ device }: { device: BatteryDevice }) {
  const clamp = (value: number) => Math.min(100, Math.max(0, value))
  return (
    <div
      className="soc-bar"
      role="img"
      aria-label={`Ladezustand ${Math.round(device.soc_prozent)} Prozent`}
    >
      <span className="fill" style={{ width: `${clamp(device.soc_prozent)}%` }} />
      <span className="mark limit" style={{ left: `${clamp(device.soc_min_prozent)}%` }} />
      <span className="mark" style={{ left: `${clamp(device.soc_max_prozent)}%` }} />
    </div>
  )
}
