import { EntityField, NumberField, SelectField } from './ConfigFields'
import type { ConfigDevice, ConfigSupported, EntityOption } from '../types'

/* Die klassenspezifischen Abschnitte des Geräteformulars. Sie liegen hier,
   weil das Formular sonst deutlich über 150 Zeilen wüchse (docs/frontend.md). */

interface Props {
  device: ConfigDevice
  patch: (partial: Partial<ConfigDevice>) => void
  entities: EntityOption[]
  error: (field: string) => string | undefined
}

interface PropsMitSupported extends Props {
  supported: ConfigSupported
}

const PHASEN_LABEL: Record<string, string> = {
  '1': 'nur einphasig',
  '3': 'nur dreiphasig',
  '1,3': 'automatisch umschalten',
}

const EINHEIT_LABEL: Record<string, string> = {
  watt: 'Watt (schreibt Watt)',
  ampere: 'Ampere (schreibt ganze Ampere)',
}

const VORZEICHEN_LABEL: Record<string, string> = {
  positiv_laden: 'positiv = laden',
  positiv_entladen: 'positiv = entladen',
}

export function DeviceFieldsControllable({ device, patch, entities, supported, error }: PropsMitSupported) {
  const ampere = device.output_unit === 'ampere'
  const einheit = ampere ? 'A' : 'W'
  const mehrphasig = ampere && device.phases === '1,3'

  return (
    <>
      <section className="card section-card">
        <div className="card-head"><h2>Messwerte und Ausgabe</h2></div>
        <div className="card-body form-grid">
          <EntityField
            label="Ist-Leistungssensor" required wide
            value={device.actual_power_entity ?? ''} entities={entities} domains={['sensor']}
            error={error('actual_power_entity')}
            hint="Leistungsaufnahme in Watt. Wird nur gelesen."
            onChange={(value) => patch({ actual_power_entity: value })}
          />
          <SelectField
            label="Ausgabeeinheit"
            value={device.output_unit ?? 'watt'} options={supported.output_units}
            labels={EINHEIT_LABEL} error={error('output_unit')}
            onChange={(value) => patch({ output_unit: value as 'watt' | 'ampere' })}
          />
          {ampere ? (
            <SelectField
              label="Phasen"
              value={device.phases ?? '1'} options={supported.phases}
              labels={PHASEN_LABEL} error={error('phases')}
              onChange={(value) => patch({ phases: value })}
            />
          ) : null}
          {mehrphasig ? (
            <NumberField
              label="Sperrzeit zwischen Phasenwechseln" unit="s" min={0} step={1}
              value={device.phase_switch_delay_s} error={error('phase_switch_delay_s')}
              hint="Fallback für min_umschaltzeit_s. Ein gültiger HA-Wert hat Vorrang – auch die 0."
              onChange={(value) => patch({ phase_switch_delay_s: value })}
            />
          ) : null}
          {ampere ? (
            <>
              <EntityField label="Spannung L1" value={device.voltage_l1_entity ?? ''}
                           entities={entities} domains={['sensor']} error={error('voltage_l1_entity')}
                           hint="Optional. Fehlt oder unplausibel: 230 V."
                           onChange={(value) => patch({ voltage_l1_entity: value })} />
              <EntityField label="Spannung L2" value={device.voltage_l2_entity ?? ''}
                           entities={entities} domains={['sensor']} error={error('voltage_l2_entity')}
                           onChange={(value) => patch({ voltage_l2_entity: value })} />
              <EntityField label="Spannung L3" value={device.voltage_l3_entity ?? ''}
                           entities={entities} domains={['sensor']} error={error('voltage_l3_entity')}
                           onChange={(value) => patch({ voltage_l3_entity: value })} />
            </>
          ) : null}
        </div>
      </section>

      <section className="card section-card">
        <div className="card-head">
          <h2>Grenzen und Rampe</h2>
          <div className="spacer" />
          <span className="pill muted">Werte in {einheit}</span>
        </div>
        <div className="card-body">
          <p className="hint-box">
            Diese sechs Werte sind Pflicht. Sie greifen, wenn der gleichnamige HA-Helfer fehlt,
            ausgefallen oder unbrauchbar ist — ein gültiger HA-Wert hat immer Vorrang.
          </p>
          <div className="form-grid">
            <NumberField label="Technisches Minimum" unit={einheit} required min={0}
                         value={device.technical_minimum} error={error('technical_minimum')}
                         hint="Untergrenze, ab der das Gerät überhaupt laufen kann."
                         onChange={(value) => patch({ technical_minimum: value })} />
            <NumberField label="Technisches Maximum" unit={einheit} required min={0}
                         value={device.technical_maximum} error={error('technical_maximum')}
                         hint="Muss größer als 0 sein — der Startwert 0 ist absichtlich ungültig."
                         onChange={(value) => patch({ technical_maximum: value })} />
            <NumberField label="Wartezeit beim Hochregeln" unit="s" required min={0}
                         value={device.increase_delay_s} error={error('increase_delay_s')}
                         onChange={(value) => patch({ increase_delay_s: value })} />
            <NumberField label="Wartezeit beim Absenken" unit="s" required min={0}
                         value={device.decrease_delay_s} error={error('decrease_delay_s')}
                         hint="Bei Netzdefizit wird unabhängig davon sofort abgeregelt."
                         onChange={(value) => patch({ decrease_delay_s: value })} />
            <NumberField label="Maximale Änderung pro Schritt" unit={einheit} required min={0}
                         value={device.maximum_step_change} error={error('maximum_step_change')}
                         onChange={(value) => patch({ maximum_step_change: value })} />
            <NumberField label="Totband" unit={einheit} required min={0}
                         value={device.minimum_step_change} error={error('minimum_step_change')}
                         hint="Kleinere Änderungen werden nicht geschrieben."
                         onChange={(value) => patch({ minimum_step_change: value })} />
          </div>
        </div>
      </section>
    </>
  )
}

export function DeviceFieldsBinary({ device, patch, entities, error }: Props) {
  return (
    <section className="card section-card">
      <div className="card-head"><h2>Schalter, Leistung und Zeitschutz</h2></div>
      <div className="card-body">
        <EntityField
          label="Schalter des realen Geräts" required
          value={device.switch_entity ?? ''} entities={entities} domains={['switch']}
          error={error('switch_entity')}
          hint="Wird nur gelesen. Das HEMS schreibt ausschließlich die Anforderung."
          onChange={(value) => patch({ switch_entity: value })}
        />
        <p className="hint-box">
          Die fünf Werte unten sind Pflicht. Sie greifen, wenn der gleichnamige HA-Helfer fehlt,
          ausgefallen oder unbrauchbar ist. Mindestlaufzeit und Abschaltverzögerung gelten
          <b> auch bei einer Notabschaltung</b>.
        </p>
        <div className="form-grid">
          <NumberField label="Leistung im EIN-Zustand" unit="W" required min={0}
                       value={device.power_w} error={error('power_w')}
                       hint="Muss größer als 0 sein — sonst ist die Pool-Rechnung unbrauchbar."
                       onChange={(value) => patch({ power_w: value })} />
          <NumberField label="Einschaltreserve" unit="W" required min={0}
                       value={device.on_reserve_w} error={error('on_reserve_w')}
                       hint="Zusätzlich zur globalen Einschaltreserve."
                       onChange={(value) => patch({ on_reserve_w: value })} />
          <NumberField label="Mindestlaufzeit" unit="s" required min={0}
                       value={device.min_runtime_s} error={error('min_runtime_s')}
                       onChange={(value) => patch({ min_runtime_s: value })} />
          <NumberField label="Mindestauszeit" unit="s" required min={0}
                       value={device.min_offtime_s} error={error('min_offtime_s')}
                       onChange={(value) => patch({ min_offtime_s: value })} />
          <NumberField label="Abschaltverzögerung" unit="s" required min={0} wide
                       value={device.off_delay_s} error={error('off_delay_s')}
                       onChange={(value) => patch({ off_delay_s: value })} />
        </div>
      </div>
    </section>
  )
}

export function DeviceFieldsBattery({ device, patch, entities, supported, error }: PropsMitSupported) {
  const signiert = Boolean(device.power_entity)

  return (
    <>
      <section className="card section-card">
        <div className="card-head"><h2>Messwerte</h2></div>
        <div className="card-body form-grid">
          <EntityField
            label="Ladezustand (SoC)" required wide
            value={device.soc_entity ?? ''} entities={entities} domains={['sensor']}
            error={error('soc_entity')} hint="In Prozent."
            onChange={(value) => patch({ soc_entity: value })}
          />
          <div className="wide">
            <p className="hint-box">
              Genau <b>eine</b> Ist-Leistungsvariante ausfüllen: entweder zwei vorzeichenlose
              Sensoren für Laden und Entladen oder einen signierten Sensor. Beides zugleich ist
              ungültig.
            </p>
          </div>
          <EntityField
            label="Ist-Ladeleistung" value={device.charge_power_entity ?? ''}
            entities={entities} domains={['sensor']} error={error('charge_power_entity')}
            onChange={(value) => patch({ charge_power_entity: value })}
          />
          <EntityField
            label="Ist-Entladeleistung" value={device.discharge_power_entity ?? ''}
            entities={entities} domains={['sensor']} error={error('discharge_power_entity')}
            onChange={(value) => patch({ discharge_power_entity: value })}
          />
          <EntityField
            label="Signierter Leistungssensor" value={device.power_entity ?? ''}
            entities={entities} domains={['sensor']} error={error('power_entity')}
            hint="Alternative zu den beiden Sensoren darüber."
            onChange={(value) => patch({ power_entity: value })}
          />
          {signiert ? (
            <SelectField
              label="Vorzeichen"
              value={device.power_sign ?? 'positiv_laden'} options={supported.power_signs}
              labels={VORZEICHEN_LABEL} error={error('power_sign')}
              onChange={(value) => patch({ power_sign: value as ConfigDevice['power_sign'] })}
            />
          ) : null}
        </div>
      </section>

      <section className="card section-card">
        <div className="card-head"><h2>Physische Grenzen</h2></div>
        <div className="card-body">
          <p className="hint-box">
            Diese beiden Wattwerte sind die <b>alleinigen</b> physischen Maximalgrenzen und
            deshalb Pflicht. Sie werden direkt in der Add-on-Konfiguration gepflegt. Ein Wert
            von 0 W sperrt die jeweilige Richtung bewusst.
          </p>
          <div className="form-grid">
            <NumberField
              label="Verfügbare Ladeleistung" unit="W" required min={0}
              value={device.available_charge_power_w}
              error={error('available_charge_power_w')}
              onChange={(value) => patch({ available_charge_power_w: value })}
            />
            <NumberField
              label="Verfügbare Entladeleistung" unit="W" required min={0}
              value={device.available_discharge_power_w}
              error={error('available_discharge_power_w')}
              onChange={(value) => patch({ available_discharge_power_w: value })}
            />
          </div>
        </div>
      </section>

      <section className="card section-card">
        <div className="card-head"><h2>Regelverhalten und Anzeige</h2></div>
        <div className="card-body form-grid">
          <NumberField label="Wiedereinstieg unter SoC-Maximum" unit="%" required min={0} step={0.5}
                       value={device.soc_max_hysteresis_percent}
                       error={error('soc_max_hysteresis_percent')}
                       hint="Ohne Hysterese flippt der Speicher bei 100 % im Takt."
                       onChange={(value) => patch({ soc_max_hysteresis_percent: value })} />
          <NumberField label="Sperrzeit nach Richtungswechsel" unit="s" required min={0} step={1}
                       value={device.direction_switch_delay_s}
                       error={error('direction_switch_delay_s')}
                       hint="Währenddessen wird Standby angefordert, nicht die alte Richtung."
                       onChange={(value) => patch({ direction_switch_delay_s: value })} />
          <NumberField label="Nutzbare Kapazität" unit="kWh" min={0} step={0.1} wide
                       value={device.capacity_kwh} error={error('capacity_kwh')}
                       hint="Nur Anzeige, keine Regelgröße."
                       onChange={(value) => patch({ capacity_kwh: value })} />
        </div>
      </section>
    </>
  )
}
