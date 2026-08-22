import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import { App } from './App'
import { ThemeProvider } from './components/Theme'
import { ToastProvider } from './components/Toast'
import { ConfigDraftProvider } from './components/ConfigDraft'
import './styles.css'

/* Verdrahtung, keine Logik. Provider-Reihenfolge: Router aussen, dann Theme,
   dann Toast, dann der Konfigurationsentwurf — Theme haengt an nichts, der
   Entwurf meldet Fehler ueber Toasts und liegt deshalb darunter. Er liegt ueber
   dem Layout, damit ein Seitenwechsel ihn nicht verwirft und die Navigation
   ungespeicherte Aenderungen erkennen kann. Geladen wird er erst, wenn eine
   Konfigurationsseite es anfordert.

   HashRouter statt BrowserRouter: Unter dem HA-Ingress kennt der Server das
   Pfadpraefix nicht und koennte fuer Unterrouten keine index.html ausliefern
   (D-036). Einen AuthProvider gibt es nicht — die Anmeldung macht der Ingress. */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <ThemeProvider>
        <ToastProvider>
          <ConfigDraftProvider>
            <App />
          </ConfigDraftProvider>
        </ToastProvider>
      </ThemeProvider>
    </HashRouter>
  </StrictMode>,
)
