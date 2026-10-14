import { useEffect } from 'react'
import { ConfigActions, RestartOverlay } from '../components/ConfigActions'
import { useConfigDraft } from '../components/ConfigDraft'
import { EntityField, NumberField, SelectField, TextField } from '../components/ConfigFields'
import { INTERVAL_LABELS, TariffPage } from '../components/TariffShared'
import type { ConfigDevice } from '../types'

/* Quellen des dynamischen Strompreises (D-065): Preis, PV-Prognose, Zähler,
   Grundlast und Wirkungsgrade der Speicher. Teil des gemeinsamen
   Konfigurationsentwurfs – wirkt nach „Speichern und neu starten“. */

export function StrompreisQuellen() {
  const { data, draft, entities, loadError, fieldErrors, restarting, ensureLoaded, patch } = useConfigDraft()

  useEffect(ensureLoaded, [ensureLoaded])

  if (!data || !draft) {
    return (
      <TariffPage subtitle="Quellen">
        {loadError
          ? <div className="alert">Konfiguration nicht verfügbar: {loadError}</div>
          : <div className="center"><div className="spinner" /></div>}
      </TariffPage>
    )
  }

  const batteries = draft.devices
    .map((device, index) => ({ device, index }))
    .filter(({ device }) => device.class === 'battery')
  const setDeviceField = (index: number, changes: Partial<ConfigDevice>) => patch({
    devices: draft.devices.map((device: ConfigDevice, i) => (i === index ? { ...device, ...changes } : device)),
  })

  return (
    <TariffPage subtitle="Quellen – Preis, Prognosen, Zähler und Speicher">
      {restarting ? <RestartOverlay /> : null}

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

          <div className="section-title">Netzanschluss und Energiezähler</div>
          <p className="hint-box">
            Optional und nur zur Datenerhebung in Data Insight: echter Netzbezug, robuste Tagesenergien und
            gemessene Wirkungsgrade. Leistung in W, Zähler in kWh oder Wh – passt die Einheit nicht, ordnet das
            HEMS die Rolle nicht zu und zeigt unten einen Hinweis.
          </p>
          <div className="form-grid">
            <EntityField
              label="Netzanschluss (Leistung)"
              value={draft.tariff_grid_power_entity} entities={entities} domains={['sensor']}
              error={fieldErrors.tariff_grid_power_entity}
              hint="In W, positiv = Bezug, z. B. sensor.e3dc_leistung_netz_modbus."
              onChange={(next) => patch({ tariff_grid_power_entity: next })}
            />
            <EntityField
              label="Netzbezug (Zähler)"
              value={draft.tariff_grid_import_energy_entity} entities={entities} domains={['sensor']}
              error={fieldErrors.tariff_grid_import_energy_entity}
              hint="z. B. sensor.e3dc_energie_netz_bezug."
              onChange={(next) => patch({ tariff_grid_import_energy_entity: next })}
            />
            <EntityField
              label="Netzeinspeisung (Zähler)"
              value={draft.tariff_grid_export_energy_entity} entities={entities} domains={['sensor']}
              error={fieldErrors.tariff_grid_export_energy_entity}
              hint="z. B. sensor.e3dc_energie_netz_einspeisung."
              onChange={(next) => patch({ tariff_grid_export_energy_entity: next })}
            />
            <EntityField
              label="PV-Ertrag (Zähler)"
              value={draft.pv_actual_energy_entity} entities={entities} domains={['sensor']}
              error={fieldErrors.pv_actual_energy_entity}
              hint="z. B. sensor.e3dc_energie_ertrag_gesamt."
              onChange={(next) => patch({ pv_actual_energy_entity: next })}
            />
            <EntityField
              label="Hausverbrauch (Zähler)"
              value={draft.tariff_house_load_energy_entity} entities={entities} domains={['sensor']}
              error={fieldErrors.tariff_house_load_energy_entity}
              hint="z. B. sensor.e3dc_energie_hausverbrauch_gesamt."
              onChange={(next) => patch({ tariff_house_load_energy_entity: next })}
            />
          </div>
          {batteries.map(({ device, index }) => (
            <div className="form-grid" key={`meter-${device.name}`}>
              <EntityField
                label={`${device.label || device.name}: Laden (Zähler)`}
                value={device.tariff_charge_energy_entity ?? ''} entities={entities} domains={['sensor']}
                error={fieldErrors[`devices[${index}].tariff_charge_energy_entity`]}
                onChange={(next) => setDeviceField(index, { tariff_charge_energy_entity: next })}
              />
              <EntityField
                label={`${device.label || device.name}: Entladen (Zähler)`}
                value={device.tariff_discharge_energy_entity ?? ''} entities={entities} domains={['sensor']}
                error={fieldErrors[`devices[${index}].tariff_discharge_energy_entity`]}
                onChange={(next) => setDeviceField(index, { tariff_discharge_energy_entity: next })}
              />
            </div>
          ))}

          <div className="section-title">Grundlast</div>
          <p className="hint-box">
            Grundlast = Hausverbrauch − Istleistung aller HEMS-Verbraucher − Leistung der Speicher, die im
            Hausverbrauch-Sensor stecken (Laden erhöht ihn, Entladen senkt ihn). Das HEMS rechnet sie je
            Minute aus den in Data Insight aufgezeichneten Werten.
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

      <ConfigActions />
    </TariffPage>
  )
}
