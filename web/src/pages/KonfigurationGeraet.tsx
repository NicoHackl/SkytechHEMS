import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { Icon } from '../components/Icon'
import { RestartOverlay } from '../components/ConfigActions'
import { useConfigDraft } from '../components/ConfigDraft'
import { HelferStatus } from '../components/HelferStatus'
import { ModeChecks, SelectField, TextField } from '../components/ConfigFields'
import { DeviceFieldsControllable, DeviceFieldsBinary, DeviceFieldsBattery }
  from '../components/DeviceFields'
import type {
  ConfigDevice, ConfigSupported, ControlGroup, DeviceClass, EntityDiagnostic,
} from '../types'

/* Anlegen und Bearbeiten teilen sich dieses Formular. Der Index in der Adresse
   ist nur die Entwurfsposition — die fachliche Identität bleibt `name`. */

const KLASSEN_LABEL: Record<DeviceClass, string> = {
  controllable: 'Regelbar (Heizstab, Wallbox)',
  binary: 'Binär (AN/AUS)',
  battery: 'AC-Speicher',
}

export function neuesGeraet(klasse: DeviceClass, supported: ConfigSupported): ConfigDevice {
  const defaults = supported.device_defaults[klasse] ?? {}
  const basis: ConfigDevice = {
    name: '', class: klasse, label: '', entity_prefix: '',
    allowed_modes: supported.modes.join(','),
  }
  if (klasse === 'controllable') {
    return {
      ...basis, ...defaults,
      actual_power_entity: '', output_unit: 'watt', phases: '1',
      phase_switch_delay_s: 300,
      voltage_l1_entity: '', voltage_l2_entity: '', voltage_l3_entity: '',
    }
  }
  if (klasse === 'binary') {
    return { ...basis, ...defaults, switch_entity: '' }
  }
  return {
    ...basis, ...defaults,
    soc_entity: '', charge_power_entity: '', discharge_power_entity: '',
    power_entity: '', power_sign: 'positiv_laden',
    capacity_kwh: 0,
  }
}

export function KonfigurationGeraet({ mode }: { mode: 'create' | 'edit' }) {
  const { data, draft, entities, loadError, fieldErrors, restarting, ensureLoaded, setDevices }
    = useConfigDraft()
  const { index } = useParams()
  const navigate = useNavigate()
  const [schema, setSchema] = useState<ControlGroup[] | null>(null)
  const [diagnostics, setDiagnostics] =
    useState<Record<string, Record<string, EntityDiagnostic>>>({})
  const [writeErrors, setWriteErrors] = useState<Record<string, string | null>>({})

  useEffect(ensureLoaded, [ensureLoaded])

  /* Steuerschema und Zyklusdiagnose sind reine Anzeige: sie sagen, wie es den
     abgeleiteten Helfern des laufenden Geräts gerade geht. */
  useEffect(() => {
    void (async () => {
      try {
        const [gruppen, status] = await Promise.all([api.controlsSchema(), api.status()])
        setSchema(gruppen)
        const devices = 'devices' in status.status ? status.status.devices : []
        setDiagnostics(Object.fromEntries(devices.map((d) => [d.id, d.entity_diagnostics])))
        setWriteErrors(Object.fromEntries(devices.map((d) => [d.id, d.write_error])))
      } catch {
        /* Ohne Diagnose bleibt das Formular vollständig bedienbar. */
        setSchema([])
      }
    })()
  }, [])

  const position = mode === 'edit' ? Number.parseInt(index ?? '', 10) : -1
  const gespeichert = mode === 'edit' && draft ? draft.devices[position] : undefined
  const [device, setDevice] = useState<ConfigDevice | null>(null)
  const [lokaleFehler, setLokaleFehler] = useState<Record<string, string>>({})
  const [geaenderteFelder, setGeaenderteFelder] = useState<Set<string>>(new Set())
  const validationRun = useRef(0)

  useEffect(() => {
    if (!data || !draft || device) return
    const initial = mode === 'edit'
      ? (gespeichert ? structuredClone(gespeichert) : null)
      : neuesGeraet('controllable', data.supported)
    setDevice(initial)
    if (mode === 'edit') {
      const prefix = `devices[${position}].`
      setLokaleFehler(Object.fromEntries(Object.entries(fieldErrors)
        .filter(([path]) => path.startsWith(prefix))
        .map(([path, text]) => [path.slice(prefix.length), text])))
    }
  }, [data, draft, device, fieldErrors, gespeichert, mode, position])

  /* Das lokal bearbeitete Gerät liegt bis „Übernehmen" noch nicht im
     gemeinsamen Entwurf. Deshalb prüfen wir hier einen temporären
     Gesamtentwurf. So verschwinden behobene Fehler direkt und Abhängigkeiten
     zwischen zwei Feldern (z. B. Minimum/Maximum) bleiben korrekt. */
  useEffect(() => {
    if (!draft || !device) return
    const target = mode === 'edit' ? position : draft.devices.length
    const devices = [...draft.devices]
    if (mode === 'edit') devices[target] = device
    else devices.push(device)
    const run = ++validationRun.current
    const timer = window.setTimeout(() => {
      void api.validateConfig({ ...draft, devices }).then((result) => {
        if (validationRun.current !== run) return
        const prefix = `devices[${target}].`
        setLokaleFehler(Object.fromEntries(Object.entries(result.field_errors)
          .filter(([path]) => path.startsWith(prefix))
          .map(([path, text]) => [path.slice(prefix.length), text])))
        setGeaenderteFelder(new Set())
      }).catch(() => {
        /* Ein Transportfehler darf das lokale Formular nicht blockieren. Der
           Speichervorgang meldet ihn später sichtbar. */
      })
    }, 200)
    return () => {
      window.clearTimeout(timer)
      if (validationRun.current === run) validationRun.current += 1
    }
  }, [device, draft, mode, position])

  const patch = useCallback((partial: Partial<ConfigDevice>) => {
    setDevice((current) => (current ? { ...current, ...partial } : current))
    setGeaenderteFelder((current) => {
      const next = new Set(current)
      Object.keys(partial).forEach((key) => next.add(key))
      return next
    })
  }, [])

  if (!data || !draft) {
    return (
      <>
        <PageHeader title="Gerät" />
        <div className="content form-content">
          {loadError
            ? <div className="alert">Konfiguration nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  if (mode === 'edit' && !gespeichert) {
    return (
      <>
        <PageHeader title="Gerät" />
        <div className="content form-content">
          <div className="alert">Dieses Gerät gibt es im Entwurf nicht (mehr).</div>
        </div>
      </>
    )
  }

  if (!device) return null

  const fehler = (feld: string) => (geaenderteFelder.has(feld)
    ? undefined
    : lokaleFehler[feld])

  const uebernehmen = () => {
    const devices = [...draft.devices]
    if (mode === 'edit') devices[position] = device
    else devices.push(device)
    setDevices(devices)
    navigate('/konfiguration/geraete')
  }

  const abbrechen = () => {
    const geaendert = JSON.stringify(device) !== JSON.stringify(gespeichert ?? null)
    if (geaendert && !window.confirm('Die Änderungen an diesem Gerät verwerfen?')) return
    navigate('/konfiguration/geraete')
  }

  const wechsleKlasse = (klasse: string) => {
    const neu = neuesGeraet(klasse as DeviceClass, data.supported)
    // Gemeinsame Felder bleiben erhalten – nur die klassenspezifischen wechseln.
    patch({
      ...neu,
      name: device.name,
      label: device.label,
      entity_prefix: device.entity_prefix,
      allowed_modes: device.allowed_modes,
    })
  }

  const modi = device.allowed_modes.split(',').map((m) => m.trim()).filter(Boolean)
  const gruppe = schema?.find((group) => group.name === device.name)

  return (
    <>
      <PageHeader
        title={mode === 'create' ? 'Gerät anlegen' : (device.label || device.name || 'Gerät')}
        subtitle={mode === 'create' ? 'Neuer Eintrag im Entwurf' : 'Eintrag im Entwurf bearbeiten'}
      />
      {restarting ? <RestartOverlay /> : null}

      <div className="content form-content">
        <button type="button" className="btn btn-ghost btn-sm" onClick={abbrechen}>
          <Icon name="arrowLeft" size={16} />Zur Geräteliste
        </button>

        <section className="card section-card">
          <div className="card-head">
            <h2>Identität</h2>
            <div className="spacer" />
            {modi.length === 0 ? <span className="pill primary">Nur Energy Pilot</span> : null}
          </div>
          <div className="card-body form-grid">
            <SelectField
              label="Geräteklasse" required wide
              value={device.class} options={data.supported.device_classes}
              labels={KLASSEN_LABEL} error={fehler('class')}
              hint="Bestimmt, welche Felder und HA-Helfer dieses Gerät braucht."
              onChange={wechsleKlasse}
            />
            <TextField
              label="Name" required mono
              value={device.name} error={fehler('name')}
              placeholder="heizstab"
              hint="Technische ID und Standard-Präfix der HA-Helfer. Kleinbuchstaben, Ziffern,
                    Unterstriche; je Anlage eindeutig."
              onChange={(value) => patch({ name: value })}
            />
            <TextField
              label="Anzeigename"
              value={device.label} error={fehler('label')}
              placeholder={device.name}
              hint="Nur Anzeige. Darf Leerzeichen und Umlaute enthalten."
              onChange={(value) => patch({ label: value })}
            />
            <TextField
              label="Entitätspräfix" mono wide
              value={device.entity_prefix} error={fehler('entity_prefix')}
              placeholder={device.name}
              hint="Nur nötig, wenn die HA-Helfer bereits mit einem anderen Präfix angelegt wurden."
              onChange={(value) => patch({ entity_prefix: value })}
            />
            <div className="wide">
              <ModeChecks
                legend="Regelmodi, in denen normale Nutzerregeln wirken"
                value={device.allowed_modes}
                options={data.supported.modes}
                error={fehler('allowed_modes')}
                hint={'Leere Auswahl ist gültig und bedeutet „nur Energy Pilot": normale '
                      + 'Nutzerregeln aktivieren das Gerät dann nie.'}
                disabledHint={(modus) => data.supported.modes.includes(modus)
                  && !draft.available_modes.split(',').map((m) => m.trim()).includes(modus)
                  ? 'Dieser Modus ist global nicht aktiviert.'
                  : undefined}
                onChange={(value) => patch({ allowed_modes: value })}
              />
            </div>
          </div>
        </section>

        {device.class === 'controllable' ? (
          <DeviceFieldsControllable device={device} patch={patch} entities={entities}
                                    supported={data.supported} error={fehler} />
        ) : device.class === 'binary' ? (
          <DeviceFieldsBinary device={device} patch={patch} entities={entities} error={fehler} />
        ) : (
          <DeviceFieldsBattery device={device} patch={patch} entities={entities}
                               supported={data.supported} error={fehler} />
        )}

        <section className="card section-card">
          <div className="card-head"><h2>Abgeleitete HA-Helfer</h2></div>
          <div className="card-body helper-body">
            <HelferStatus group={gruppe} diagnostics={diagnostics[device.name]}
                          writeError={writeErrors[device.name]} />
          </div>
        </section>

        <div className="form-footer">
          <div className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={abbrechen}>Abbrechen</button>
          <button type="button" className="btn btn-primary" onClick={uebernehmen}>
            {mode === 'create' ? 'Gerät übernehmen' : 'Änderungen übernehmen'}
          </button>
        </div>

        <p className="meta-line">
          „Übernehmen" schreibt das Gerät nur in den Entwurf. Gespeichert wird es in der
          Geräteliste — und wirksam nach einem Neustart.
        </p>
      </div>
    </>
  )
}
