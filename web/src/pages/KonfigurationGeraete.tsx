import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { PageHeader } from '../components/Layout'
import { Icon } from '../components/Icon'
import { ConfigActions, RestartOverlay } from '../components/ConfigActions'
import { useConfigDraft } from '../components/ConfigDraft'
import { KonfigurationNav } from '../components/KonfigurationNav'
import type { ConfigDevice } from '../types'

/* Geräteliste des Entwurfs: anlegen, bearbeiten, löschen, verschieben.

   Die Reihenfolge ist fachlich relevant — bei gleicher Priorität entscheidet
   sie, wer zuerst bedient wird. Deshalb gibt es Hoch/Runter statt einer
   automatischen Sortierung. */

const KLASSEN: Record<string, string> = {
  controllable: 'Regelbar',
  binary: 'Binär',
  battery: 'AC-Speicher',
}

/** Laufzeitgründe in Klartext. Ein unbekannter Schlüssel bleibt sichtbar. */
const GRUND_TEXT: Record<string, string> = {
  schreibziel_fehlt: 'Ein Schreibziel gibt es in Home Assistant nicht.',
  schreibziel_nicht_verfuegbar: 'Ein Schreibziel ist gerade nicht verfügbar.',
  schreibziel_ungueltig: 'Ein Schreibziel hat die falsche Domain oder fehlende Optionen.',
  schreiben_fehlgeschlagen: 'Der letzte Schreibversuch ist fehlgeschlagen.',
}

export function KonfigurationGeraete() {
  const { data, draft, loadError, fieldErrors, restarting, ensureLoaded, setDevices }
    = useConfigDraft()
  const navigate = useNavigate()
  /* Laufzeitstatus des letzten Zyklus: „gültig konfiguriert" und „regelt gerade
     tatsächlich" sind zwei verschiedene Aussagen. */
  const [nichtRegelbar, setNichtRegelbar] = useState<Record<string, string[]>>({})

  useEffect(ensureLoaded, [ensureLoaded])

  useEffect(() => {
    void (async () => {
      try {
        const status = await api.status()
        if (!('devices' in status.status)) return
        setNichtRegelbar(Object.fromEntries(status.status.devices
          .filter((device) => !device.runtime_active)
          .map((device) => [device.id, device.inactive_reasons])))
      } catch {
        /* Ohne Status bleibt die Liste vollständig bedienbar. */
      }
    })()
  }, [])

  if (!data || !draft) {
    return (
      <>
        <PageHeader title="Konfiguration" subtitle="Geräte" />
        <div className="content">
          {loadError
            ? <div className="alert">Konfiguration nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  const move = (index: number, delta: number) => {
    const ziel = index + delta
    if (ziel < 0 || ziel >= draft.devices.length) return
    const devices = [...draft.devices]
    const [entfernt] = devices.splice(index, 1)
    devices.splice(ziel, 0, entfernt)
    setDevices(devices)
  }

  const remove = (index: number, device: ConfigDevice) => {
    if (!window.confirm(`„${device.label || device.name}" wirklich löschen?`)) return
    setDevices(draft.devices.filter((_, position) => position !== index))
  }

  const fehlerZuGeraet = (index: number) => Object.entries(fieldErrors)
    .filter(([pfad]) => pfad.startsWith(`devices[${index}].`))
    .map(([pfad, text]) => [pfad.split('.').slice(1).join('.'), text] as const)

  const uebersprungen = (name: string) =>
    data.inactive_devices.some((issue) => issue.name === name)

  return (
    <>
      <PageHeader
        title="Konfiguration"
        subtitle="Geräte"
        actions={
          <Link to="/konfiguration/geraete/neu" className="btn btn-primary">
            <Icon name="plus" size={16} />Gerät anlegen
          </Link>
        }
      />
      {restarting ? <RestartOverlay /> : null}

      <div className="content">
        <KonfigurationNav />

        <div className="info-strip">
          <Icon name="info" size={16} />
          <span>
            Die Reihenfolge entscheidet bei gleicher Priorität, wer zuerst bedient wird.
            Änderungen wirken erst nach einem Neustart des Add-ons.
          </span>
        </div>

        {draft.devices.length === 0 ? (
          <div className="card">
            <div className="empty">
              <Icon name="plug" size={40} />
              <p>Noch kein Gerät konfiguriert. Ohne Gerät verteilt das HEMS keinen Überschuss.</p>
              <Link to="/konfiguration/geraete/neu" className="btn btn-primary">
                <Icon name="plus" size={16} />Erstes Gerät anlegen
              </Link>
            </div>
          </div>
        ) : (
          <div className="card">
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Gerät</th>
                    <th>Klasse</th>
                    <th>Präfix</th>
                    <th>Regelmodi</th>
                    <th>Zustand</th>
                    <th aria-label="Aktionen" />
                  </tr>
                </thead>
                <tbody>
                  {draft.devices.map((device, index) => {
                    const fehler = fehlerZuGeraet(index)
                    const modi = device.allowed_modes.split(',').map((m) => m.trim()).filter(Boolean)
                    return (
                      <tr key={`${device.name}-${index}`}>
                        <td>
                          <div className="cell-title">{device.label || device.name}</div>
                          <div className="cell-sub mono">{device.name || '—'}</div>
                        </td>
                        <td>{KLASSEN[device.class] ?? (device.class || '—')}</td>
                        <td className="mono">{device.entity_prefix || device.name || '—'}</td>
                        <td>
                          {modi.length === 0
                            ? <span className="pill primary">Nur Energy Pilot</span>
                            : modi.join(', ')}
                        </td>
                        <td>
                          {fehler.length ? (
                            <span className="pill err" title={fehler.map(([f, t]) => `${f}: ${t}`).join('\n')}>
                              {fehler.length} Feldfehler
                            </span>
                          ) : uebersprungen(device.name) ? (
                            <span className="pill err">Beim Start übersprungen</span>
                          ) : nichtRegelbar[device.name] ? (
                            <span className="pill warn"
                                  title={GRUND_TEXT[nichtRegelbar[device.name][0]]
                                         ?? nichtRegelbar[device.name].join(', ')}>
                              Nicht regelbar
                            </span>
                          ) : (
                            <span className="pill ok">Gültig</span>
                          )}
                        </td>
                        <td>
                          <div className="row-actions">
                            <button type="button" className="icon-btn" aria-label="Nach oben"
                                    disabled={index === 0} onClick={() => move(index, -1)}>
                              <Icon name="up" size={16} />
                            </button>
                            <button type="button" className="icon-btn" aria-label="Nach unten"
                                    disabled={index === draft.devices.length - 1}
                                    onClick={() => move(index, 1)}>
                              <Icon name="down" size={16} />
                            </button>
                            <button type="button" className="icon-btn" aria-label="Bearbeiten"
                                    onClick={() => navigate(`/konfiguration/geraete/${index}`)}>
                              <Icon name="edit" size={16} />
                            </button>
                            <button type="button" className="icon-btn danger-icon" aria-label="Löschen"
                                    onClick={() => remove(index, device)}>
                              <Icon name="trash" size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <ConfigActions />
      </div>
    </>
  )
}
