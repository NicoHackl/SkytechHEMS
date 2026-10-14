import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Status } from './pages/Status'
import { Steuerung } from './pages/Steuerung'
import { SteuerungInfo } from './pages/SteuerungInfo'
import { EnergyPilotUebersicht } from './pages/EnergyPilotUebersicht'
import { EnergyPilotVorschlaege } from './pages/EnergyPilotVorschlaege'
import { KonfigurationGlobal } from './pages/KonfigurationGlobal'
import { KonfigurationGeraete } from './pages/KonfigurationGeraete'
import { KonfigurationGeraet } from './pages/KonfigurationGeraet'
import { SensorenUeberschuss } from './pages/SensorenUeberschuss'
import { SensorenHausbilanz } from './pages/SensorenHausbilanz'
import { FlowCard } from './pages/FlowCard'
import { Notabschaltung } from './pages/Notabschaltung'
import { StrompreisUebersicht } from './pages/StrompreisUebersicht'
import { StrompreisPreise } from './pages/StrompreisPreise'
import { StrompreisNetzladen } from './pages/StrompreisNetzladen'
import { StrompreisDataInsight } from './pages/StrompreisDataInsight'
import { StrompreisQuellen } from './pages/StrompreisQuellen'

/* Ausschliesslich die Routentabelle. Das Layout ist Elternroute mit <Outlet />,
   damit Navigation und Kopfzeile beim Seitenwechsel nicht neu montiert werden.

   Energy Pilot und Dynamischer Strompreis sind in Unterseiten aufgeteilt; ihre
   Stammpfade leiten auf die Übersicht um, damit alte Lesezeichen gültig bleiben.

   Anlegen und Bearbeiten eines Geraets teilen sich eine Komponente mit
   mode: 'create' | 'edit' — das Muster der Vorlage (docs/frontend.md). */
export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Status />} />
        <Route path="/steuerung" element={<Steuerung />} />
        <Route path="/steuerung-info" element={<SteuerungInfo />} />
        <Route path="/energy-pilot" element={<Navigate to="/energy-pilot/uebersicht" replace />} />
        <Route path="/energy-pilot/uebersicht" element={<EnergyPilotUebersicht />} />
        <Route path="/energy-pilot/vorschlaege" element={<EnergyPilotVorschlaege />} />
        <Route path="/sensoren/ueberschuss" element={<SensorenUeberschuss />} />
        <Route path="/sensoren/hausbilanz" element={<SensorenHausbilanz />} />
        <Route path="/flow-card" element={<FlowCard />} />
        <Route path="/notabschaltung" element={<Notabschaltung />} />
        <Route path="/dynamischer-strompreis" element={<Navigate to="/dynamischer-strompreis/uebersicht" replace />} />
        <Route path="/dynamischer-strompreis/uebersicht" element={<StrompreisUebersicht />} />
        <Route path="/dynamischer-strompreis/preise" element={<StrompreisPreise />} />
        <Route path="/dynamischer-strompreis/netzladen" element={<StrompreisNetzladen />} />
        <Route path="/dynamischer-strompreis/data-insight" element={<StrompreisDataInsight />} />
        <Route path="/dynamischer-strompreis/quellen" element={<StrompreisQuellen />} />
        <Route path="/konfiguration/global" element={<KonfigurationGlobal />} />
        <Route path="/konfiguration/geraete" element={<KonfigurationGeraete />} />
        <Route path="/konfiguration/geraete/neu" element={<KonfigurationGeraet mode="create" />} />
        <Route path="/konfiguration/geraete/:index" element={<KonfigurationGeraet mode="edit" />} />
        <Route path="*" element={<div className="content"><div className="empty">Seite nicht gefunden.</div></div>} />
      </Route>
    </Routes>
  )
}
