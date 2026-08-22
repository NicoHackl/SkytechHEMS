import { NavLink } from 'react-router-dom'

/* Unter-Tabs des Sensoren-Bereichs (D-045) — wortgetreue Kopie des Musters aus
   KonfigurationNav.tsx: ein Bereich, mehrere Unteransichten. */

export function SensorenNav() {
  const cls = ({ isActive }: { isActive: boolean }) => `btn btn-ghost btn-sm${isActive ? ' active' : ''}`
  return (
    <nav className="pill-row config-tabs" aria-label="Sensorbereich">
      <NavLink to="/sensoren/ueberschuss" className={cls}>Überschuss</NavLink>
      <NavLink to="/sensoren/hausbilanz" className={cls}>Hausbilanz</NavLink>
    </nav>
  )
}
