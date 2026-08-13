import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Icon } from './Icon'

/* Hell/Dunkel-Umschaltung. Pflicht in jeder Oberfläche — siehe AGENTS.md,
   eiserne Regel 10. Der Provider setzt ausschließlich data-theme am <html>;
   welche Farben daran hängen, entscheidet allein styles.css. Kein Farbwert
   und keine Designsprache stehen in dieser Datei. */

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

/** Erst die gespeicherte Wahl, sonst die Systemvorgabe. */
function readInitialTheme(): Theme {
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readInitialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    /* Adressleiste mobiler Browser mitfärben — der Wert kommt aus dem Token,
       damit hier keine zweite Farbquelle entsteht. */
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) {
      const background = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()
      if (background) meta.setAttribute('content', background)
    }
  }, [theme])

  /* Der Systemvorgabe wird nur gefolgt, solange der Nutzer nicht selbst
     gewählt hat — eine getroffene Wahl überschreibt man ihm nicht. */
  useEffect(() => {
    const query = window.matchMedia(DARK_QUERY)
    const handleChange = (event: MediaQueryListEvent) => {
      if (window.localStorage.getItem(STORAGE_KEY)) return
      setThemeState(event.matches ? 'dark' : 'light')
    }
    query.addEventListener('change', handleChange)
    return () => query.removeEventListener('change', handleChange)
  }, [])

  const setTheme = useCallback((next: Theme) => {
    window.localStorage.setItem(STORAGE_KEY, next)
    setThemeState(next)
  }, [])

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, setTheme, toggleTheme: () => setTheme(theme === 'dark' ? 'light' : 'dark') }),
    [theme, setTheme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme muss innerhalb des ThemeProvider verwendet werden.')
  return context
}

/** Der Schalter selbst. Gehört sichtbar in jede Oberfläche, nicht in ein Untermenü. */
export function ThemeSwitch() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      className="icon-btn"
      onClick={toggleTheme}
      aria-pressed={isDark}
      aria-label={isDark ? 'Zu hellem Design wechseln' : 'Zu dunklem Design wechseln'}
      title={isDark ? 'Helles Design' : 'Dunkles Design'}
    >
      <Icon name={isDark ? 'sun' : 'moon'} />
    </button>
  )
}
