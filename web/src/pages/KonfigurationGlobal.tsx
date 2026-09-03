import { useEffect } from 'react'
import { PageHeader } from '../components/Layout'
import { ConfigActions, RestartOverlay } from '../components/ConfigActions'
import { useConfigDraft } from '../components/ConfigDraft'
import {
  EntityField, ModeChecks, NumberField, SelectField,
} from '../components/ConfigFields'
import { KonfigurationNav } from '../components/KonfigurationNav'

/* Globale Add-on-Optionen. Sieben Felder plus die Freischaltung der normalen
   Regelmodi — mehr gibt es auf dieser Ebene nicht. */

export function KonfigurationGlobal() {
  const { data, draft, entities, loadError, fieldErrors, restarting, ensureLoaded, patch }
    = useConfigDraft()

  useEffect(ensureLoaded, [ensureLoaded])

  if (!data || !draft) {
    return (
      <>
        <PageHeader title="Konfiguration" subtitle="Globale Einstellungen" />
        <div className="content form-content">
          {loadError
            ? <div className="alert">Konfiguration nicht verfügbar: {loadError}</div>
            : <div className="center"><div className="spinner" /></div>}
        </div>
      </>
    )
  }

  const betroffeneGeraete = (mode: string) => draft.devices
    .filter((device) => device.allowed_modes.split(',').map((m) => m.trim()).includes(mode))
    .map((device) => device.label || device.name)
  const hasBattery = draft.devices.some((device) => device.class === 'battery')

  /* Wird ein globaler Modus abgewählt, nennt die UI die betroffenen Geräte und
     entfernt ihn nach Bestätigung aus deren allowed_modes — sonst wäre die
     Konfiguration sofort ungültig, ohne dass jemand weiss, warum. */
  const setModes = (next: string) => {
    const vorher = draft.available_modes.split(',').map((m) => m.trim()).filter(Boolean)
    const nachher = next.split(',').map((m) => m.trim()).filter(Boolean)
    const entfernt = vorher.filter((mode) => !nachher.includes(mode))

    for (const mode of entfernt) {
      const namen = betroffeneGeraete(mode)
      if (namen.length && !window.confirm(
        `Der Modus wird bei ${namen.length} Gerät(en) entfernt: ${namen.join(', ')}. Fortfahren?`,
      )) return
    }

    const devices = entfernt.length
      ? draft.devices.map((device) => ({
        ...device,
        allowed_modes: device.allowed_modes.split(',').map((m) => m.trim())
          .filter((mode) => mode && !entfernt.includes(mode)).join(','),
      }))
      : draft.devices
    patch({ available_modes: next, devices })
  }

  return (
    <>
      <PageHeader title="Konfiguration" subtitle="Globale Einstellungen" />
      {restarting ? <RestartOverlay /> : null}

      <div className="content form-content">
        <KonfigurationNav />

        <section className="card">
          <div className="card-head"><h2>Regelzyklus</h2></div>
          <div className="card-body form-grid">
            <NumberField
              label="Regelintervall" unit="s" required min={1} step={1}
              value={draft.interval_s}
              error={fieldErrors.interval_s}
              hint="1 bis 300 Sekunden. Ein neues Intervall gilt erst nach dem Neustart."
              onChange={(value) => patch({ interval_s: value ?? 0 })}
            />
            <SelectField
              label="Log-Level" required
              value={draft.log_level} options={data.supported.log_levels}
              error={fieldErrors.log_level}
              hint="Unabhängig vom HA-Helfer für die Zyklus-Debugausgabe."
              onChange={(value) => patch({ log_level: value })}
            />
            <EntityField
              label="Post-Cycle-Skript" wide
              value={draft.post_cycle_script} entities={entities} domains={['script']}
              error={fieldErrors.post_cycle_script}
              hint="Optional. Wird nach jedem erfolgreichen Zyklus gestartet."
              onChange={(value) => patch({ post_cycle_script: value })}
            />
            <SelectField
              label="Geltungsbereich der geschützten Mindestleistung" required wide
              value={draft.protected_minimum_scope}
              options={data.supported.protected_minimum_scopes}
              labels={{
                binary_only: 'Nur Binärgeräte',
                binary_and_controllable: 'Binär- und regelbare Geräte',
              }}
              error={fieldErrors.protected_minimum_scope}
              hint={'„Nur Binärgeräte“ erhält das bisherige Verhalten. Bei „Binär- und regelbare Geräte“ '
                    + 'sichert die Prioritätskaskade regelbare Verbraucher zunächst bis zu ihrer geschützten Mindestleistung ab.'}
              onChange={(value) => patch({ protected_minimum_scope: value })}
            />
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>Leistungssensoren</h2>
            <div className="spacer" />
          </div>
          <div className="card-body">
            <EntityField
              label="Überschuss-Sensor" required
              value={draft.residual_power_entity} entities={entities} domains={['sensor']}
              error={fieldErrors.residual_power_entity}
              hint="Positiver Wert = Einspeisung, negativer = Netzbezug. Die bereits vom HEMS
                    geschalteten Lasten müssen darin noch enthalten sein."
              onChange={(value) => patch({ residual_power_entity: value })}
            />
            <EntityField
              label="Hausleistungsbilanz für AC-Speicher" required={hasBattery}
              value={draft.battery_residual_power_entity} entities={entities} domains={['sensor']}
              error={fieldErrors.battery_residual_power_entity}
              hint={'Nur für AC-Speicher: negativ = Netzbezug/Unterdeckung, positiv = Einspeisung. '
                    + 'Sie muss Netzleistung und E3DC-Batterieleistung enthalten; sie steuert nur die Entladung.'}
              onChange={(value) => patch({ battery_residual_power_entity: value })}
            />
            <label className="switch">
              <input
                type="checkbox"
                checked={draft.speicher_in_residual_enthalten}
                onChange={(event) => patch({ speicher_in_residual_enthalten: event.target.checked })}
              />
              <span className="track" />
              <span className="switch-label">Speicherleistung ist im Überschuss-Sensor enthalten</span>
            </label>
            <p className="hint-box">
              Bei AC-gekoppelten Speichern mit Messpunkt an der Netzübergabe ist das der Normalfall.
              Ein Fehler hier <b>ist</b> die Aufschaukelung: das HEMS läse die eigene Entladung als
              Überschuss.
            </p>
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Aktivierte Regelmodi</h2></div>
          <div className="card-body">
            <ModeChecks
              legend="Normale Regelmodi"
              value={draft.available_modes}
              options={data.supported.modes}
              error={fieldErrors.available_modes}
              hint={'Die Sondermodi „auto" (Energy Pilot) und „aus" gehören nicht in diese Liste '
                    + 'und bleiben immer verfügbar. Meldet der HA-Helfer einen hier nicht '
                    + 'aktivierten Modus, bleibt der Zyklus sicher inaktiv.'}
              onChange={setModes}
            />
          </div>
        </section>

        <ConfigActions />
      </div>
    </>
  )
}
