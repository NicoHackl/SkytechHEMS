import { NavLink } from 'react-router-dom'

/* Umschalter zwischen den beiden Konfigurationsansichten. Er sitzt in beiden
   Seiten und gehört deshalb hierher, nicht in eine davon. */
export function KonfigurationNav() {
  const cls = ({ isActive }: { isActive: boolean }) =>
    `btn btn-ghost btn-sm${isActive ? ' active' : ''}`
  return (
    <nav className="pill-row config-tabs" aria-label="Konfigurationsbereich">
      <NavLink to="/konfiguration/global" className={cls}>Globale Einstellungen</NavLink>
      <NavLink to="/konfiguration/geraete" className={cls}>Geräte</NavLink>
    </nav>
  )
}
