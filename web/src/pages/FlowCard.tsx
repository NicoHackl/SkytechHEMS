import { useEffect, useState } from 'react'
import { PageHeader } from '../components/Layout'
import { ConfigActions, RestartOverlay } from '../components/ConfigActions'
import { useConfigDraft } from '../components/ConfigDraft'
import { EntityField, NumberField, SelectField, TextField } from '../components/ConfigFields'
import { Icon } from '../components/Icon'
import { api, ApiError } from '../api'
import type { EntityOption, FlowDashboard, FlowEntityRow, FlowPreview } from '../types'

/* Anlagenwerte und Anzeigeoptionen der Skytech Power Flow Card (D-046).

   Die Geräteliste steht bewusst NICHT hier: sie kommt aus der
   Gerätekonfiguration, und eine zweite Pflegestelle wäre eine zweite Wahrheit.
   Je Gerät lässt sich hier nur die Darstellung ändern.

   Die Seite schreibt in denselben Konfigurationsentwurf wie die
   Konfigurationsseiten — deshalb steht /flow-card in der Ausnahmeliste von
   guard() in Layout.tsx und trägt denselben Punkt in der Navigation. */

const GRID_SIGNS = ['positiv_bezug', 'positiv_einspeisung']
const GRID_SIGN_LABELS: Record<string, string> = {
  positiv_bezug: 'Positiv = Bezug aus dem Netz',
  positiv_einspeisung: 'Positiv = Einspeisung ins Netz',
}
const BATTERY_SIGNS = ['positiv_laden', 'positiv_entladen']
const BATTERY_SIGN_LABELS: Record<string, string> = {
  positiv_laden: 'Positiv = Laden',
  positiv_entladen: 'Positiv = Entladen',
}
const KLASSEN: Record<string, string> = {
  controllable: 'Regelbar', binary: 'Binär', battery: 'AC-Speicher',
}

export function FlowCard() {
  const { data, draft, entities, loadError, fieldErrors, restarting, ensureLoaded, patch, setDevices }
    = useConfigDraft()
  const ziele = useNavigationsziele()

  useEffect(ensureLoaded, [ensureLoaded])

  if (!data || !draft) {
    return (
      <>
        <PageHeader title="Flow Card" subtitle="Leistungsfluss auf dem Dashboard" />
        <div className="content form-content">
          {loadError
            ? <div className="alert">Konfiguration nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  const pvRows = draft.flow_pv_power_entities ?? []
  const setPv = (rows: FlowEntityRow[]) => patch({ flow_pv_power_entities: rows })

  const setDeviceField = (index: number, partial: Record<string, unknown>) => {
    setDevices(draft.devices.map((device, i) => (i === index ? { ...device, ...partial } : device)))
  }

  return (
    <>
      <PageHeader title="Flow Card" subtitle="Leistungsfluss auf dem Dashboard" />
      {restarting ? <RestartOverlay /> : null}

      <div className="content form-content">

        {ziele.warnungen.length > 0 ? (
          <p className="hint-box">
            Nicht jedes Dashboard lässt sich als Ziel auswählen:{' '}
            {ziele.warnungen.join(' ')} Ein Pfad lässt sich dort trotzdem von Hand eintragen.
          </p>
        ) : null}

        <section className="card">
          <div className="card-head"><h2>Veröffentlichung</h2></div>
          <div className="card-body">
            <label className="switch">
              <input
                type="checkbox"
                checked={draft.flow_publish}
                onChange={(event) => patch({ flow_publish: event.target.checked })}
              />
              <span className="track" />
              <span className="switch-label">Kartendaten nach Home Assistant schreiben</span>
            </label>
            {fieldErrors.flow_publish
              ? <div className="alert">{fieldErrors.flow_publish}</div>
              : null}
            <p className="hint-box">
              Nach jedem Regelzyklus entstehen zwei Sensoren, aus denen sich die Karte selbst
              aufbaut:<br />
              <span className="mono">sensor.skytech_hems_flow_config</span><br />
              <span className="mono">sensor.skytech_hems_flow_status</span><br />
              Im Dashboard genügt dann eine Karte mit
              {' '}<span className="mono">type: custom:skytech-power-flow-card</span> — dort wird
              keine einzige Entität eingetragen. Solange keine Historie gewünscht ist, gehören
              beide Sensoren in die Ausschlussliste des Recorders.
            </p>
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Erzeugung</h2></div>
          <div className="card-body">
            <p className="hint-box">
              „In Summe" entscheidet, ob eine Zeile in die Erzeugungsleistung zählt. Hat die
              Anlage einen Sensor für die Systemleistung <em>und</em> je einen für die einzelnen
              Strings, gehört genau eine der beiden Sichten in die Summe — die andere erscheint
              ohne Haken als Aufschlüsselung unter dem Knoten. Beides zu zählen verdoppelte die
              Erzeugung.
            </p>
            <PvRows
              rows={pvRows}
              entities={entities}
              fieldErrors={fieldErrors}
              onChange={setPv}
            />
            <div className="form-grid">
              <TextField
                label="Anzeigename"
                value={draft.flow_pv_label}
                error={fieldErrors.flow_pv_label}
                hint="Beschriftung des Erzeugungsknotens."
                onChange={(value) => patch({ flow_pv_label: value })}
              />
              <ZielFeld
                label="Navigationsziel" ziele={ziele}
                value={draft.flow_nav_pv} error={fieldErrors.flow_nav_pv}
                onChange={(value) => patch({ flow_nav_pv: value })}
              />
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Netz</h2></div>
          <div className="card-body">
            <p className="hint-box">
              Genau ein Weg: entweder ein Sensor, der Bezug und Einspeisung im Vorzeichen
              unterscheidet, oder zwei getrennte, immer positive Sensoren. Beides zugleich ist
              nicht zulässig.
            </p>
            <div className="form-grid">
              <EntityField
                label="Netzleistung (signiert)"
                value={draft.flow_grid_power_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.flow_grid_power_entity}
                onChange={(value) => patch({ flow_grid_power_entity: value })}
              />
              <SelectField
                label="Vorzeichen"
                value={draft.flow_grid_power_sign} options={GRID_SIGNS}
                labels={GRID_SIGN_LABELS}
                error={fieldErrors.flow_grid_power_sign}
                onChange={(value) => patch({ flow_grid_power_sign: value })}
              />
              <EntityField
                label="Netzbezug (getrennt)"
                value={draft.flow_grid_import_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.flow_grid_import_entity}
                onChange={(value) => patch({ flow_grid_import_entity: value })}
              />
              <EntityField
                label="Netzeinspeisung (getrennt)"
                value={draft.flow_grid_export_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.flow_grid_export_entity}
                onChange={(value) => patch({ flow_grid_export_entity: value })}
              />
              <TextField
                label="Anzeigename"
                value={draft.flow_grid_label}
                error={fieldErrors.flow_grid_label}
                onChange={(value) => patch({ flow_grid_label: value })}
              />
              <ZielFeld
                label="Navigationsziel" ziele={ziele}
                value={draft.flow_nav_grid} error={fieldErrors.flow_nav_grid}
                onChange={(value) => patch({ flow_nav_grid: value })}
              />
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Haus</h2></div>
          <div className="card-body form-grid">
            <EntityField
              label="Hausleistung"
              value={draft.flow_house_power_entity} entities={entities} domains={['sensor']}
              error={fieldErrors.flow_house_power_entity}
              hint="Leer lassen heißt: die Karte rechnet die Hausleistung aus Erzeugung, Netz und Speicher aus."
              onChange={(value) => patch({ flow_house_power_entity: value })}
            />
            <TextField
              label="Anzeigename"
              value={draft.flow_house_label}
              error={fieldErrors.flow_house_label}
              onChange={(value) => patch({ flow_house_label: value })}
            />
            <ZielFeld
              label="Navigationsziel Haus" ziele={ziele}
              value={draft.flow_nav_house} error={fieldErrors.flow_nav_house}
              onChange={(value) => patch({ flow_nav_house: value })}
            />
            <ZielFeld
              label="Navigationsziel „Übriges Haus“" ziele={ziele}
              value={draft.flow_nav_rest} error={fieldErrors.flow_nav_rest}
              hint="Der Knoten für den Verbrauch, den kein HEMS-Gerät erklärt."
              onChange={(value) => patch({ flow_nav_rest: value })}
            />
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Batterie</h2></div>
          <div className="card-body">
            <p className="hint-box">
              Gemeint ist der Hausspeicher der Anlage — auch dann, wenn das HEMS ihn gar nicht
              regelt. Ein selbstregelnder Speicher gehört genau hierher und nicht in die
              Geräteliste. Vom HEMS geregelte AC-Speicher stehen dagegen unten bei den Geräten.
              Ohne Anzeigename und ohne Ladestand gibt es keinen Batterieknoten.
            </p>
            <div className="form-grid">
              <TextField
                label="Anzeigename"
                value={draft.flow_battery_label}
                error={fieldErrors.flow_battery_label}
                onChange={(value) => patch({ flow_battery_label: value })}
              />
              <EntityField
                label="Ladestand"
                value={draft.flow_battery_soc_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.flow_battery_soc_entity}
                onChange={(value) => patch({ flow_battery_soc_entity: value })}
              />
              <EntityField
                label="Batterieleistung (signiert)"
                value={draft.flow_battery_power_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.flow_battery_power_entity}
                onChange={(value) => patch({ flow_battery_power_entity: value })}
              />
              <SelectField
                label="Vorzeichen"
                value={draft.flow_battery_power_sign} options={BATTERY_SIGNS}
                labels={BATTERY_SIGN_LABELS}
                error={fieldErrors.flow_battery_power_sign}
                onChange={(value) => patch({ flow_battery_power_sign: value })}
              />
              <EntityField
                label="Ladeleistung (getrennt)"
                value={draft.flow_battery_charge_power_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.flow_battery_charge_power_entity}
                onChange={(value) => patch({ flow_battery_charge_power_entity: value })}
              />
              <EntityField
                label="Entladeleistung (getrennt)"
                value={draft.flow_battery_discharge_power_entity} entities={entities} domains={['sensor']}
                error={fieldErrors.flow_battery_discharge_power_entity}
                onChange={(value) => patch({ flow_battery_discharge_power_entity: value })}
              />
              <ZielFeld
                label="Navigationsziel" wide ziele={ziele}
                value={draft.flow_nav_battery} error={fieldErrors.flow_nav_battery}
                onChange={(value) => patch({ flow_nav_battery: value })}
              />
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Geräte</h2></div>
          <div className="card-body">
            <p className="hint-box">
              Ein Navigationsziel legt fest, wohin ein Klick auf den Knoten springt. Ohne Ziel
              öffnet der Klick wie bisher den More-Info-Dialog der Leitentität.
            </p>
            {draft.devices.length === 0 ? (
              <div className="empty">
                <Icon name="plug" size={40} />
                <p>
                  Noch kein Gerät konfiguriert. Die Karte zeichnet die Geräte, die in der
                  Gerätekonfiguration stehen — hier lässt sich nur ihre Darstellung ändern.
                </p>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Gerät</th><th>Klasse</th><th>Anzeigen</th>
                      <th aria-label="Symbol" /><th aria-label="Farbe" />
                      <th aria-label="Navigationsziel" />
                    </tr>
                  </thead>
                  <tbody>
                    {draft.devices.map((device, index) => (
                      <tr key={`${device.name}-${index}`}>
                        <td>
                          <div className="cell-title">{device.label || device.name}</div>
                          <div className="cell-sub mono">{device.name || '—'}</div>
                        </td>
                        <td>{KLASSEN[device.class] ?? '—'}</td>
                        <td>
                          <label className="switch">
                            <input
                              type="checkbox"
                              checked={device.flow_show !== false}
                              aria-label={`${device.label || device.name} auf der Karte anzeigen`}
                              onChange={(event) =>
                                setDeviceField(index, { flow_show: event.target.checked })}
                            />
                            <span className="track" />
                          </label>
                        </td>
                        <td>
                          <TextField
                            label="Symbol" mono placeholder="mdi:radiator"
                            value={device.flow_icon ?? ''}
                            error={fieldErrors[`devices[${index}].flow_icon`]}
                            onChange={(value) => setDeviceField(index, { flow_icon: value })}
                          />
                        </td>
                        <td>
                          <TextField
                            label="Farbe" mono placeholder="#18bcf2"
                            value={device.flow_color ?? ''}
                            error={fieldErrors[`devices[${index}].flow_color`]}
                            onChange={(value) => setDeviceField(index, { flow_color: value })}
                          />
                        </td>
                        <td>
                          <ZielFeld
                            label="Ziel" ziele={ziele}
                            value={device.flow_navigation ?? ''}
                            error={fieldErrors[`devices[${index}].flow_navigation`]}
                            onChange={(value) => setDeviceField(index, { flow_navigation: value })}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Anzeige</h2></div>
          <div className="card-body form-grid">
            <TextField
              label="Überschrift"
              value={draft.flow_title}
              error={fieldErrors.flow_title}
              hint="Leer lassen heißt: keine Überschrift."
              onChange={(value) => patch({ flow_title: value })}
            />
            <NumberField
              label="Umschaltschwelle" unit="W" min={0} step={1}
              value={draft.flow_watt_threshold}
              error={fieldErrors.flow_watt_threshold}
              hint="Ab diesem Betrag zeigt die Karte kW statt W."
              onChange={(value) => patch({ flow_watt_threshold: value ?? 0 })}
            />
            <label className="switch">
              <input
                type="checkbox"
                checked={draft.flow_animation}
                onChange={(event) => patch({ flow_animation: event.target.checked })}
              />
              <span className="track" />
              <span className="switch-label">Wandernde Punkte auf den Flusslinien</span>
            </label>
            <label className="switch">
              <input
                type="checkbox"
                checked={draft.flow_house_node}
                onChange={(event) => patch({ flow_house_node: event.target.checked })}
              />
              <span className="track" />
              <span className="switch-label">Haus als eigenen Knoten zeichnen</span>
            </label>
          </div>
        </section>

        <Vorschau />

        <ConfigActions />
      </div>
    </>
  )
}

/* PV-Sensoren als Zeilenliste. Dasselbe Muster wie die Formel-Zeilen (D-045):
   die Zeilen haben keine stabile Id und werden nie umsortiert, der Index
   reicht als Schlüssel. */
function PvRows({ rows, entities, fieldErrors, onChange }: {
  rows: FlowEntityRow[]
  entities: EntityOption[]
  fieldErrors: Record<string, string>
  onChange: (rows: FlowEntityRow[]) => void
}) {
  return (
    <div className="formula-vars">
      {rows.length === 0 ? (
        <p className="hint-box">
          Noch kein Erzeugungssensor hinterlegt. Ohne Sensor zeichnet die Karte keinen
          Erzeugungsknoten — das ist ein gültiger Zustand.
        </p>
      ) : rows.map((row, index) => (
        <div className="formula-var-row pv-zeile" key={index}>
          <EntityField
            label="Leistungssensor" required
            value={row.entity} entities={entities} domains={['sensor']}
            error={fieldErrors[`flow_pv_power_entities[${index}].entity`]}
            onChange={(value) => onChange(rows.map((r, i) =>
              (i === index ? { ...r, entity: value } : r)))}
          />
          <label className="switch">
            <input
              type="checkbox"
              checked={row.in_summe !== false}
              aria-label={`Zeile ${index + 1} in die Erzeugungsleistung zählen`}
              onChange={(event) => onChange(rows.map((r, i) =>
                (i === index ? { ...r, in_summe: event.target.checked } : r)))}
            />
            <span className="track" />
            <span className="switch-label">In Summe</span>
          </label>
          <button
            type="button" className="icon-btn danger-icon"
            aria-label={`Zeile ${index + 1} entfernen`}
            onClick={() => onChange(rows.filter((_, i) => i !== index))}
          >
            <Icon name="trash" size={16} />
          </button>
        </div>
      ))}
      <button
        type="button" className="btn btn-ghost btn-sm"
        onClick={() => onChange([...rows, { entity: '' }])}
      >
        <Icon name="plus" size={16} />Zeile hinzufügen
      </button>
    </div>
  )
}

/* Was die Karte gerade bekäme, und welcher Verweis dabei trägt. Bewusst kein
   Dauerpolling: die Werte stammen aus dem Zustandsabbild des letzten Zyklus. */
function Vorschau() {
  const [preview, setPreview] = useState<FlowPreview | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const laden = async () => {
    setBusy(true)
    setError('')
    try {
      setPreview(await api.flowPreview())
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Vorschau nicht verfügbar.')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { void laden() }, [])

  return (
    <section className="card">
      <div className="card-head">
        <h2>Vorschau</h2>
        <div className="spacer" />
        <button
          type="button" className="btn btn-ghost btn-sm" disabled={busy}
          onClick={() => void laden()}
        >
          <Icon name="refresh" size={16} />{busy ? 'Lädt…' : 'Aktualisieren'}
        </button>
      </div>
      <div className="card-body">
        {error ? <div className="alert">{error}</div> : null}
        {!preview ? (
          error ? null : <div className="center"><div className="spinner" /></div>
        ) : (
          <>
            <div className="kv-row">
              <span className="k">Veröffentlichung</span>
              <span className={`v ${preview.publish_enabled ? 'ok' : 'warn'}`}>
                {preview.publish_enabled ? 'eingeschaltet' : 'ausgeschaltet'}
              </span>
            </div>
            <div className="kv-row">
              <span className="k">Revision</span>
              <span className="v mono">{preview.revision}</span>
            </div>
            <div className="kv-row">
              <span className="k">Zuletzt veröffentlicht</span>
              <span className="v">{preview.zuletzt_geschrieben || 'noch nie'}</span>
            </div>

            {preview.warnungen.map((warnung) => (
              <p className="hint-box" key={warnung}>{warnung}</p>
            ))}

            {preview.aufgeloest.length === 0 ? (
              <p className="hint-box">
                Noch kein Verweis hinterlegt. Sobald oben ein Sensor eingetragen ist, steht hier,
                ob er gerade einen brauchbaren Wert liefert.
              </p>
            ) : (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr><th>Verweis</th><th>Entität</th><th>Wert</th><th>Zustand</th></tr>
                  </thead>
                  <tbody>
                    {preview.aufgeloest.map((row) => (
                      <tr key={row.pfad}>
                        <td className="mono">{row.pfad}</td>
                        <td className="mono">{row.entity}</td>
                        <td>{row.value === null ? '—' : row.value}</td>
                        <td>
                          <span className={`pill ${row.valid ? 'ok' : 'err'}`}>
                            {row.valid ? 'trägt' : row.state || 'kein Wert'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}

/* Navigationsziele: die Liste der Dashboard-Ansichten.

   Home Assistant gibt sie nur über WebSocket heraus; das Add-on holt sie und
   reicht sie über `api.flowDashboards()` durch (D-049). Fällt das aus, bleibt
   die Seite bedienbar — das Feld wird dann ein Textfeld. */
interface Navigationsziele {
  /** Pfade in der Reihenfolge Dashboard, Ansicht. Leerer Eintrag = kein Ziel. */
  pfade: string[]
  beschriftungen: Record<string, string>
  geladen: boolean
  fehler: string
  warnungen: string[]
}

function useNavigationsziele(): Navigationsziele {
  const [dashboards, setDashboards] = useState<FlowDashboard[] | null>(null)
  const [warnungen, setWarnungen] = useState<string[]>([])
  const [fehler, setFehler] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const antwort = await api.flowDashboards()
        setDashboards(antwort.dashboards)
        setWarnungen(antwort.warnungen)
      } catch {
        setFehler('Die Dashboards konnten nicht gelesen werden.')
      }
    })()
  }, [])

  const pfade = ['']
  const beschriftungen: Record<string, string> = { '': 'kein Ziel' }
  for (const dashboard of dashboards ?? []) {
    for (const view of dashboard.views) {
      const pfad = `/${dashboard.url_path}/${view.path}`
      pfade.push(pfad)
      beschriftungen[pfad] = `${dashboard.title} › ${view.title}`
    }
  }

  return { pfade, beschriftungen, geladen: dashboards !== null, fehler, warnungen }
}

/** Ein Ziel wählen — oder tippen, wenn die Liste nicht zu haben war. */
function ZielFeld({ label, value, error, hint, wide, ziele, onChange }: {
  label: string
  value: string
  ziele: Navigationsziele
  error?: string
  hint?: string
  wide?: boolean
  onChange: (value: string) => void
}) {
  // Auch ein gespeichertes Ziel, das es nicht mehr gibt, muss wählbar bleiben —
  // sonst setzt die Auswahl es beim ersten Speichern still zurück.
  const pfade = value && !ziele.pfade.includes(value) ? [...ziele.pfade, value] : ziele.pfade
  const beschriftungen = value && !ziele.beschriftungen[value]
    ? { ...ziele.beschriftungen, [value]: `${value} (nicht gefunden)` }
    : ziele.beschriftungen

  if (!ziele.geladen) {
    return (
      <TextField
        label={label} mono wide={wide} value={value} error={error}
        placeholder="/dashboard-pv/pv"
        hint={ziele.fehler
          ? `${ziele.fehler} Pfad von Hand eintragen.`
          : (hint ?? 'Ansichten werden geladen …')}
        onChange={onChange}
      />
    )
  }

  return (
    <SelectField
      label={label} wide={wide}
      value={value} options={pfade} labels={beschriftungen}
      error={error} hint={hint}
      onChange={onChange}
    />
  )
}
