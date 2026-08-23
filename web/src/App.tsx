import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Status } from './pages/Status'
import { Steuerung } from './pages/Steuerung'
import { EnergyPilot } from './pages/EnergyPilot'
import { KonfigurationGlobal } from './pages/KonfigurationGlobal'
import { KonfigurationGeraete } from './pages/KonfigurationGeraete'
import { KonfigurationGeraet } from './pages/KonfigurationGeraet'
import { SensorenUeberschuss } from './pages/SensorenUeberschuss'
import { SensorenHausbilanz } from './pages/SensorenHausbilanz'

/* Ausschliesslich die Routentabelle. Das Layout ist Elternroute mit <Outlet />,
   damit Navigation und Kopfzeile beim Seitenwechsel nicht neu montiert werden.

   Anlegen und Bearbeiten eines Geraets teilen sich eine Komponente mit
   mode: 'create' | 'edit' — das Muster der Vorlage (docs/frontend.md). */
export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Status />} />
        <Route path="/steuerung" element={<Steuerung />} />
        <Route path="/energy-pilot" element={<EnergyPilot />} />
        <Route path="/sensoren/ueberschuss" element={<SensorenUeberschuss />} />
        <Route path="/sensoren/hausbilanz" element={<SensorenHausbilanz />} />
        <Route path="/konfiguration/global" element={<KonfigurationGlobal />} />
        <Route path="/konfiguration/geraete" element={<KonfigurationGeraete />} />
        <Route path="/konfiguration/geraete/neu" element={<KonfigurationGeraet mode="create" />} />
        <Route path="/konfiguration/geraete/:index" element={<KonfigurationGeraet mode="edit" />} />
        <Route path="*" element={<div className="content"><div className="empty">Seite nicht gefunden.</div></div>} />
      </Route>
    </Routes>
  )
}
