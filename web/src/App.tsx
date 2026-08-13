import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Status } from './pages/Status'
import { Steuerung } from './pages/Steuerung'
import { EnergyPilot } from './pages/EnergyPilot'

/* Ausschliesslich die Routentabelle. Das Layout ist Elternroute mit <Outlet />,
   damit Navigation und Kopfzeile beim Seitenwechsel nicht neu montiert werden. */
export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Status />} />
        <Route path="/steuerung" element={<Steuerung />} />
        <Route path="/energy-pilot" element={<EnergyPilot />} />
        <Route path="*" element={<div className="content"><div className="empty">Seite nicht gefunden.</div></div>} />
      </Route>
    </Routes>
  )
}
