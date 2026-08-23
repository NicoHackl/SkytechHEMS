import { useState, type MouseEvent, type ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Icon } from './Icon'
import { ThemeSwitch } from './Theme'
import { useConfigDraft } from './ConfigDraft'

/* App-Gerüst: Sidebar + Hauptspalte. Das Layout ist Elternroute mit <Outlet />,
   damit Navigation und Kopfzeile beim Seitenwechsel nicht neu montiert werden. */

const navClass = ({ isActive }: { isActive: boolean }) => `nav-item${isActive ? ' active' : ''}`

export function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const closeMobile = () => setMobileOpen(false)
  const { dirty } = useConfigDraft()

  /* Wer den Konfigurationsbereich mit ungespeichertem Entwurf verlaesst, wird
     gefragt — innerhalb des Bereichs bleibt der Entwurf ohnehin erhalten.
     Sensoren (D-045) teilt sich denselben Entwurf und zaehlt deshalb dazu. */
  const guard = (event: MouseEvent<HTMLAnchorElement>, to: string) => {
    if (!dirty || to.startsWith('/konfiguration') || to.startsWith('/sensoren')) return
    if (!window.confirm('Es gibt ungespeicherte Änderungen an der Konfiguration. Trotzdem wechseln?')) {
      event.preventDefault()
    }
  }

  return (
    <div className="shell">
      {mobileOpen ? <button className="sidebar-backdrop" aria-label="Navigation schließen" onClick={closeMobile} /> : null}

      <aside className={`sidebar${mobileOpen ? ' open' : ''}`}>
        <div className="sidebar-brand">
          <span className="crest">SH</span>
          <div><b>Skytech HEMS</b><span>Energiemanagement</span></div>
        </div>

        <nav className="nav" onClick={closeMobile}>
          <NavLink to="/" end className={navClass} onClick={(event) => guard(event, '/')}><Icon name="dashboard" /><span>Status</span></NavLink>
          <NavLink to="/steuerung" className={navClass} onClick={(event) => guard(event, '/steuerung')}><Icon name="sliders" /><span>Steuerung</span></NavLink>

          <div className="nav-label">Vorausschau</div>
          <NavLink to="/energy-pilot" className={navClass} onClick={(event) => guard(event, '/energy-pilot')}><Icon name="spark" /><span>Energy Pilot</span></NavLink>

          <div className="nav-label">Einrichtung</div>
          <NavLink to="/konfiguration/global" className={navClass}>
            <Icon name="settings" /><span>Konfiguration</span>
            {dirty ? <span className="count">•</span> : null}
          </NavLink>
          <NavLink to="/sensoren/ueberschuss" className={navClass} onClick={(event) => guard(event, '/sensoren')}>
            <Icon name="pulse" /><span>Sensoren</span>
            {dirty ? <span className="count">•</span> : null}
          </NavLink>
        </nav>

        <div className="sidebar-foot">
          <span className="avatar"><Icon name="spark" size={16} /></span>
          <div className="who"><b>PV-Überschuss</b><span>Regelung über HA-Helfer</span></div>
        </div>
      </aside>

      <main className="main">
        <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Navigation öffnen"><Icon name="menu" /></button>
        <Outlet />
      </main>
    </div>
  )
}

/** Klebrige Kopfzeile jeder Seite. Keine Seite baut sich eine eigene.
    Der Theme-Schalter sitzt hier und nicht in der Sidebar: die faehrt unter
    820px aus dem Bild, der Schalter muss aber auf jeder Seite erreichbar sein. */
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="topbar">
      <div>
        <h1>{title}</h1>
        {subtitle ? <div className="sub">{subtitle}</div> : null}
      </div>
      <div className="spacer" />
      {actions}
      <ThemeSwitch />
    </div>
  )
}
