import { Link } from 'react-router-dom'
import { KeyValue } from '../components/DeviceCard'
import {
  INTERVAL_LABELS, StatePill, TariffPage, formatHours, formatKwh, formatPrice, slotText, useTariffStatus, windowText,
} from '../components/TariffShared'
import type { TariffEnergy, TariffFigures, TariffLoad, TariffStorage } from '../types'

/* Übersicht des dynamischen Strompreises (D-065): aktueller Preis, PV-Prognose,
   Verbrauch, Reichweite und Kennzahlen. Reine Anzeige – das Modul schaltet nichts. */

export function StrompreisUebersicht() {
  const { status, statusError } = useTariffStatus()
  const price = status?.preis ?? null
  const pv = status?.pv ?? null

  return (
    <TariffPage subtitle="Übersicht – Datenerhebung, schaltet nichts" statusError={statusError}>
      {!status && !statusError ? <div className="center"><div className="spinner" /></div> : null}

      {status ? (
        <section className="card">
          <div className="card-head">
            <h2>Strompreis</h2>
            <div className="spacer" />
            <StatePill active={status.aktiv} valid={price?.gueltig ?? false} />
          </div>
          <div className="card-body">
            {!status.aktiv ? (
              <p className="hint-box">
                Ausgeschaltet. Unter <Link to="/dynamischer-strompreis/quellen">Quellen</Link> einschalten,
                Preissensor wählen und speichern.
              </p>
            ) : null}
            {status.aktiv && price ? (
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
    </TariffPage>
  )
}

function EnergyRow({ label, value }: { label: string; value: TariffEnergy }) {
  if (!value.entity) return <KeyValue label={label} value="nicht konfiguriert" tone="muted" />
  return value.gueltig
    ? <KeyValue label={label} value={formatKwh(value.wert_kwh)} />
    : <KeyValue label={label} value={value.grund ?? 'ungültig'} tone="err" />
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
