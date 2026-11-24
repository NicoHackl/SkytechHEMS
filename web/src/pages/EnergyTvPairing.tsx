import { useEffect, useState, type ReactNode } from 'react'
import { PageHeader } from '../components/Layout'

const pairingPath = /^\/(?:app|hassio\/ingress)\/[a-z0-9_]+_skytech_hems\/energy-tv\/([0-9.]+)\/([0-9]{1,5})\/([a-f0-9-]{36})$/
// Der vom TV angezeigte Pfad enthält eine zufällige Sitzung, keine Dauerzugangsdaten.
const ticketPattern = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/

function privateIPv4(address: string): boolean {
  const parts = address.split('.')
  const bytes = parts.map(Number)
  if (parts.length !== 4 || !parts.every((part, index) =>
    /^\d+$/.test(part) && String(bytes[index]) === part && bytes[index]! <= 255,
  )) return false

  const [first, second] = bytes
  return first === 10 || (first === 172 && second! >= 16 && second! <= 31)
    || (first === 192 && second === 168)
}

function readPairingLink(): URL | null {
  let home: Location
  try {
    home = window.parent.location
    if (window.parent === window || home.origin !== window.location.origin) return null
  } catch {
    return null
  }

  const [, address, rawPort, ticket] = home.pathname.match(pairingPath) ?? []
  const port = Number(rawPort)
  if (!address || !ticket || !privateIPv4(address) || !ticketPattern.test(ticket)
      || !Number.isInteger(port) || port < 1 || port > 65535) return null

  const link = new URL(`http://${address}:${port}/authorize`)
  link.searchParams.set('pair', ticket)
  link.searchParams.set('instance', home.origin)
  return link
}

export function EnergyTvPairing({ children }: { children: ReactNode }) {
  const [link, setLink] = useState(readPairingLink)
  useEffect(() => {
    const parent = window.parent
    if (parent === window) return
    try {
      if (parent.location.origin !== window.location.origin) return
    } catch {
      return
    }
    const refresh = () => setLink(readPairingLink())
    parent.addEventListener('location-changed', refresh)
    parent.addEventListener('popstate', refresh)
    refresh()
    return () => {
      parent.removeEventListener('location-changed', refresh)
      parent.removeEventListener('popstate', refresh)
    }
  }, [])

  if (!link) return children
  return (
    <div className="content">
      <PageHeader title="Skytech Energy TV verbinden" />
      <div className="card">
        <div className="card-body">
          <p>Bestätige die Verbindung, wenn dir gerade der QR-Code auf deinem Apple TV angezeigt wird.</p>
          <p>Home Assistant fragt dich anschließend nach der Freigabe für den Fernseher.</p>
        </div>
        <div className="card-body">
          <a className="btn btn-primary" href={link.href} target="_top" referrerPolicy="no-referrer">
            Mit Apple TV verbinden
          </a>
        </div>
      </div>
    </div>
  )
}
