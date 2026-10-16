import { useState, type MouseEvent, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { AddonFoot } from './AddonFoot'
import { Icon } from './Icon'
import { ThemeSwitch } from './Theme'
import { useConfigDraft } from './ConfigDraft'

/* App-Gerüst: Sidebar + Hauptspalte. Das Layout ist Elternroute mit <Outlet />,
   damit Navigation und Kopfzeile beim Seitenwechsel nicht neu montiert werden. */

const navClass = ({ isActive }: { isActive: boolean }) => `nav-item${isActive ? ' active' : ''}`

/* Bereiche mit Unterseiten (Vorausschau). Die Unterseiten klappen in der
   Sidebar auf, solange der Bereich aktiv ist. `draft` markiert Unterseiten, die
   in den gemeinsamen Konfigurationsentwurf schreiben – sie tragen den Punkt. */
interface NavSubPage { to: string; label: string; draft?: boolean }

const ENERGY_PILOT_PAGES: NavSubPage[] = [
  { to: '/energy-pilot/uebersicht', label: 'Übersicht' },
  { to: '/energy-pilot/vorschlaege', label: 'Vorschläge' },
]

const TARIFF_PAGES: NavSubPage[] = [
  { to: '/dynamischer-strompreis/uebersicht', label: 'Übersicht' },
  { to: '/dynamischer-strompreis/preise', label: 'Preise' },
  { to: '/dynamischer-strompreis/netzladen', label: 'Netzladen' },
  { to: '/dynamischer-strompreis/data-insight', label: 'Data Insight', draft: true },
  { to: '/dynamischer-strompreis/quellen', label: 'Quellen', draft: true },
]

export function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const closeMobile = () => setMobileOpen(false)
  const { dirty } = useConfigDraft()

  /* Wer den Konfigurationsbereich mit ungespeichertem Entwurf verlaesst, wird
     gefragt — innerhalb des Bereichs bleibt der Entwurf ohnehin erhalten.
     Sensoren (D-045), Flow Card (D-046), Notabschaltung (D-059) und der
     dynamische Strompreis (D-065) teilen sich
     denselben Entwurf und zaehlen deshalb dazu. */
  const guard = (event: MouseEvent<HTMLAnchorElement>, to: string) => {
    if (!dirty || to.startsWith('/konfiguration') || to.startsWith('/sensoren')
        || to.startsWith('/flow-card') || to.startsWith('/notabschaltung')
        || to.startsWith('/dynamischer-strompreis')) return
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
          <NavLink to="/steuerung-info" className={navClass} onClick={(event) => guard(event, '/steuerung-info')}><Icon name="info" /><span>Steuerung Info</span></NavLink>

          <div className="nav-label">Vorausschau</div>
          <NavBranch to="/energy-pilot" icon="spark" label="Energy Pilot" pages={ENERGY_PILOT_PAGES} guard={guard} />
          <NavBranch
            to="/dynamischer-strompreis" icon="plug" label="Dynamischer Strompreis"
            pages={TARIFF_PAGES} guard={guard} dirty={dirty}
          />

          <div className="nav-label">Einrichtung</div>
          <NavLink to="/konfiguration/global" className={navClass}>
            <Icon name="settings" /><span>Konfiguration</span>
            {dirty ? <span className="count">•</span> : null}
          </NavLink>
          <NavLink to="/sensoren/ueberschuss" className={navClass} onClick={(event) => guard(event, '/sensoren')}>
            <Icon name="pulse" /><span>Sensoren</span>
            {dirty ? <span className="count">•</span> : null}
          </NavLink>
          <NavLink to="/flow-card" className={navClass} onClick={(event) => guard(event, '/flow-card')}>
            <Icon name="flow" /><span>Flow Card</span>
            {dirty ? <span className="count">•</span> : null}
          </NavLink>
          <NavLink to="/notabschaltung" className={navClass} onClick={(event) => guard(event, '/notabschaltung')}>
            <Icon name="warning" /><span>Notabschaltung</span>
            {dirty ? <span className="count">•</span> : null}
          </NavLink>
        </nav>

        <AddonFoot />
      </aside>

      <main className="main">
        <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Navigation öffnen"><Icon name="menu" /></button>
        <Outlet />
      </main>
    </div>
  )
}

/** Bereichseintrag mit aufklappbaren Unterseiten. Der Bereich selbst führt auf
    seine Übersicht (Weiterleitung in App.tsx); aktiv markiert ist nur die
    Unterseite, der Bereich zeigt den Zustand allein über die Textfarbe. */
function NavBranch({ to, icon, label, pages, guard, dirty = false }: {
  to: string
  icon: string
  label: string
  pages: NavSubPage[]
  guard: (event: MouseEvent<HTMLAnchorElement>, to: string) => void
  dirty?: boolean
}) {
  const { pathname } = useLocation()
  const open = pathname === to || pathname.startsWith(`${to}/`)
  const branchClass = ({ isActive }: { isActive: boolean }) => `nav-item branch${isActive ? ' active' : ''}`
  const subClass = ({ isActive }: { isActive: boolean }) => `nav-item nav-sub-item${isActive ? ' active' : ''}`

  return (
    <>
      <NavLink to={to} className={branchClass} onClick={(event) => guard(event, to)} aria-expanded={open}>
        <Icon name={icon} /><span>{label}</span>
        {dirty ? <span className="count">•</span> : null}
      </NavLink>
      {open ? (
        <div className="nav-sub">
          {pages.map((page) => (
            <NavLink key={page.to} to={page.to} className={subClass} onClick={(event) => guard(event, page.to)}>
              <span>{page.label}</span>
              {dirty && page.draft ? <span className="count">•</span> : null}
            </NavLink>
          ))}
        </div>
      ) : null}
    </>
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
