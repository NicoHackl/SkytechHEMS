import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import { App } from './App'
import { ThemeProvider } from './components/Theme'
import { ToastProvider } from './components/Toast'
import './styles.css'

/* Verdrahtung, keine Logik. Provider-Reihenfolge: Router aussen, dann Theme,
   dann Toast — Theme haengt an nichts und alles darunter darf es lesen.

   HashRouter statt BrowserRouter: Unter dem HA-Ingress kennt der Server das
   Pfadpraefix nicht und koennte fuer Unterrouten keine index.html ausliefern
   (D-036). Einen AuthProvider gibt es nicht — die Anmeldung macht der Ingress. */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <ThemeProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </ThemeProvider>
    </HashRouter>
  </StrictMode>,
)
