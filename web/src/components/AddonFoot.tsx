import { useEffect, useState, type MouseEvent } from 'react'
import { api } from '../api'
import type { AddonInfo } from '../types'
import { Icon } from './Icon'

/* Fuß der Sidebar (D-067): in allen Skytech-Add-ons gleich aufgebaut — Produkt-
   Icon, Name des Add-ons, darunter „Addon-Config“. Ein Klick öffnet die
   Konfigurationsseite des Add-ons in Home Assistant. Den Slug samt Präfix des
   Add-on-Repositorys kennt nur der Supervisor; fehlt er, bleibt der Fuß ein
   reines Namensschild ohne Link. */

const FALLBACK_NAME = 'Skytech HEMS'

/** Öffnet den Pfad im Fenster von Home Assistant. Unter dem Ingress läuft die
    Oberfläche in einem iframe gleichen Ursprungs: dann navigiert HA ohne
    Neuladen, genau wie bei einem eigenen Link. Klappt das nicht (eigenes
    Fenster, Sandbox), übernimmt der normale Link mit target="_top". */
function openInHomeAssistant(event: MouseEvent<HTMLAnchorElement>, path: string) {
  try {
    const top = window.top
    if (!top || top === window.self) return
    top.history.pushState(null, '', path)
    top.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } }))
    event.preventDefault()
  } catch {
    /* Zugriff verweigert: der Link navigiert selbst. */
  }
}

export function AddonFoot() {
  const [addon, setAddon] = useState<AddonInfo | null>(null)

  useEffect(() => {
    let active = true
    api
      .addon()
      .then((data) => {
        if (active) setAddon(data)
      })
      .catch((cause: Error) => console.error('Add-on-Angaben nicht abrufbar', cause))
    return () => {
      active = false
    }
  }, [])

  const content = (
    <>
      <span className="avatar"><Icon name="solar" size={16} /></span>
      <div className="who"><b>{addon?.name ?? FALLBACK_NAME}</b><span>Addon-Config</span></div>
    </>
  )

  const path = addon?.config_path
  if (!path) return <div className="sidebar-foot">{content}</div>
  return (
    <a
      className="sidebar-foot"
      href={path}
      target="_top"
      title="Add-on-Konfiguration in Home Assistant öffnen"
      onClick={(event) => openInHomeAssistant(event, path)}
    >
      {content}
    </a>
  )
}
