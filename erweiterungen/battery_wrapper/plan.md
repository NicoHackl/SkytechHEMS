# Plan: Home-Assistant-Integration „Battery Bridge" (Arbeitstitel)

> Diese Datei ist ein Planungsdokument für ein **eigenständiges, neues Git-Repository**. Sie liegt
> vorübergehend hier im SkytechHEMS-Repo unter `erweiterungen/battery_wrapper/`, damit sie versioniert
> mitläuft, bis das neue Repo existiert. Sie ist **kein** Teil des HEMS-Add-ons, die
> Iron-Rules aus `AGENTS.md` (Changelog-Pflicht, `docs/`-Pflege) gelten dafür nicht — sobald ins neue
> Repo kopiert, gilt dort ein eigenes `AGENTS.md`/`CLAUDE.md`.

## 1. Zweck

Eine Home-Assistant-Integration, die Batteriespeicher verschiedener Hersteller einheitlich als
normalisierte HA-Entitäten bereitstellt: Ist-SoC, Ist-Lade-/Entladeleistung lesen; Soll-Lade-/
Entladeleistung schreiben. Sie ist die Brücke zwischen der herstellerspezifischen Anbindung
(Marstek zuerst, später weitere) und generischen Verbrauchern dieser Daten — allen voran SkytechHEMS,
aber auch Dashboards, andere Automationen, Energy-Dashboard.

**Kein** Ersatz für den bestehenden HEMS-Anforderungsvertrag
(`input_number.ems_<prefix>_anforderung_leistung_w` /
`input_select.ems_<prefix>_anforderung_betriebsart`, siehe
[docs/device_classes/battery.md](../../docs/device_classes/battery.md) im HEMS-Repo). Diese
Integration ersetzt nur die **Geräteautomation**, die bisher diesen Helfer-Vertrag in reale
Modbus/Cloud-Aufrufe übersetzt hat — durch sauberen, getesteten Python-Code statt YAML/Jinja.

## 2. Architekturentscheidung (Zusammenfassung)

- **Integration statt HEMS-Erweiterung.** HEMS darf laut Architektur kein Gerät direkt schalten
  (`docs/architektur.md`: „Direktes Schalten der Endgeräte" ist explizit **nicht** Aufgabe des
  Add-ons; `HAClient` ist einzige Stelle mit HA-Zugriff, nur REST, kein Modbus/UDP). Die
  Geräteklasse `battery` in HEMS liest bereits beliebige Entity-IDs (`soc_entity`,
  `charge_power_entity`/`discharge_power_entity` bzw. `power_entity`) — diese Integration liefert
  genau solche Entitäten, HEMS-Config zeigt einfach darauf. Keine Codeänderung in HEMS nötig.
- **Ein Wrapper, mehrere Speicher, mehrere Hersteller.** Eine Integration (ein `domain`), pro
  physischem Speicher ein eigener `ConfigEntry` (HA-Standardmuster: Integration mehrfach über die
  UI hinzufügen). Herstellerunterschiede stecken hinter einem Adapter-Interface — neuer Hersteller
  = neuer Adapter, keine Änderung an Coordinator/Platforms/HEMS-Anbindung.
- **Transport pro Adapter, nicht pro Integration.** Marstek: lokale UDP-Open-API (JSON-RPC, Port
  30000) statt Modbus TCP — offizielles, zweckgebautes Protokoll, weniger Overhead pro Abfrage,
  läuft unabhängig vom Firmware-Mindeststand, den natives Modbus TCP voraussetzt. Spätere
  Hersteller bringen ihr eigenes Protokoll (Modbus, REST, Cloud …) mit — bleibt Adapter-intern.

## 3. Verzeichnisstruktur (Zielrepo)

```
custom_components/battery_bridge/
  __init__.py            # Setup/Unload ConfigEntry, Coordinator anlegen
  manifest.json           # domain, name, codeowners, requirements, iot_class: local_polling
  config_flow.py           # Schritt 1: Hersteller wählen · Schritt 2: Verbindungsdaten je Hersteller
  const.py                 # DOMAIN, Plattform-Konstanten, Default-Poll-Intervall
  coordinator.py            # DataUpdateCoordinator[StorageState] pro ConfigEntry
  models.py                  # StorageState (Dataclass): soc_percent, charge_power_w,
                              #   discharge_power_w, available, last_update
  adapters/
    __init__.py
    base.py                  # StorageAdapter-Protocol: connect(), read(), write_charge_power(),
                              #   write_discharge_power(), close()
    marstek_udp.py            # Marstek Open API, UDP JSON-RPC Port 30000, Discovery + Commands
  sensor.py                   # SoC-%, Ist-Ladeleistung-W, Ist-Entladeleistung-W (oder signiert)
  number.py                    # Soll-Ladeleistung-W, Soll-Entladeleistung-W (Control-Entities)
  strings.json / translations/de.json   # Config-Flow-Texte
tests/
  test_config_flow.py
  test_coordinator.py
  adapters/test_marstek_udp.py         # gegen UDP-Mock/Fixture, keine echte Hardware nötig
hacs.json
README.md
LICENSE
```

## 4. Adapter-Vertrag (`adapters/base.py`)

Gemeinsame Schnittstelle, die jeder Hersteller-Adapter implementiert — Coordinator und Platforms
kennen nur dieses Protocol, nie Herstellerdetails:

```python
class StorageAdapter(Protocol):
    async def connect(self) -> None: ...
    async def read(self) -> StorageState: ...
    async def write_charge_power(self, watts: float) -> None: ...
    async def write_discharge_power(self, watts: float) -> None: ...
    async def close(self) -> None: ...
```

`StorageState` (Dataclass, `models.py`):

| Feld | Typ | Bedeutung |
|---|---|---|
| `soc_percent` | `float \| None` | Ladezustand, `None` bei ungültigem Wert |
| `charge_power_w` | `float \| None` | Ist-Ladeleistung ≥ 0 |
| `discharge_power_w` | `float \| None` | Ist-Entladeleistung ≥ 0 |
| `available` | `bool` | Letzte Abfrage erfolgreich |
| `last_update` | `datetime` | Zeitstempel der letzten gültigen Antwort |

`None`/`available=False` löst in HA `unavailable` aus — Verbraucher wie HEMS behandeln das über
ihren bestehenden Fallback-auf-sicheren-Zustand (siehe `battery.md`: ungültiger SoC/Ist-Leistungs-
Sensor → Speicher geht in sicheren Zustand). Diese Integration muss dafür nichts Eigenes bauen.

## 5. Marstek-Adapter (`adapters/marstek_udp.py`)

- Verbindung: UDP, Ziel-IP + Port (Default `30000`, Marstek erlaubt Änderung im Bereich
  `49152–65535` über die App — Config-Flow-Feld, Default vorbelegt).
- Protokoll: JSON-RPC, ein Request → ein Response, Requests tragen `id` zum Antwort-Matching
  (Pflicht, da UDP keine Zustellgarantie hat → eigenes Timeout+Retry, z. B. 3 Versuche à 1 s).
- Discovery (optional, Komfortfeature im Config-Flow): UDP-Broadcast
  `{"id": 0, "method": "Marstek.GetDevice", "params": {"ble_mac": "0"}}` findet Geräte im LAN.
- Referenzen: [offizielle Marstek Open-API-Doku](https://manuals.plus/m/d0c8656e5b0773c24100f04f4e4e35d0c4e6f9ac6b6408b0765f2eb3872c2dbf),
  Spiegel [Randyocean/Marstek](https://github.com/Randyocean/Marstek/blob/main/docs/marstek_device_openapi.MD),
  bestehende Referenzimplementierungen [jaapp/ha-marstek-local-api](https://github.com/jaapp/ha-marstek-local-api)
  und [taurgis/has-marstek-local-api](https://github.com/taurgis/has-marstek-local-api).

**Offen — vor Implementierung zu klären (nicht raten, siehe AGENTS.md-Grundsatz):**

- Exakte Methodennamen/Payload für SoC- und Leistungsabfrage sowie für das Setzen einer
  Lade-/Entladeleistungsvorgabe — aus der offiziellen Doku entnehmen, nicht annehmen.
- Ob die Venus E 3.0 über die UDP-API einen **direkten Leistungs-Sollwert** (Watt) entgegennimmt,
  oder nur Betriebsmodus (z. B. „Manual Mode" + festes Zielfenster) — das entscheidet, ob
  `number.soll_ladeleistung_w` wirklich stufenlos schreibt oder auf ein Moduskonzept abgebildet
  werden muss.
- Tatsächliche Reaktionszeit auf eine geschriebene Leistungsvorgabe (siehe Punkt 7 — Messung an
  echter Hardware nötig, bekannte Zahl ist nur „~3 s" für den *Selbstverbrauchsmodus mit CT002*,
  nicht für eine direkte Vorgabe).

## 6. Config-Flow

1. **Hersteller wählen** (`SelectSelector`, aktuell einzige Option „Marstek").
2. **Verbindungsdaten je Hersteller** — bei Marstek: Host/IP (Pflicht), UDP-Port (Default 30000,
   editierbar), optional Discovery-Button.
3. **Verbindungstest** vor Abschluss (`connect()` + `read()` einmal ausführen) — schlägt er fehl,
   bleibt der Flow im Fehlerzustand statt einen kaputten Entry anzulegen.
4. `unique_id` je Entry aus Host+Port (oder, falls die Marstek-Antwort eine Geräte-/MAC-ID liefert,
   daraus) — verhindert doppelte Entries für denselben Speicher.

Mehrere Speicher = Schritt 1–4 mehrfach über „Integration hinzufügen" in der HA-UI. Jeder Entry
bekommt einen eigenen Coordinator, eigenes Device in der Device-Registry, eigene Entity-IDs
(Präfix aus einem im Flow vergebenen Anzeigenamen).

## 7. Polling, Fehlerbehandlung, Reconnect

- `DataUpdateCoordinator` pro Entry, Poll-Intervall konfigurierbar (Default z. B. 5 s — Startwert,
  nach echter Latenzmessung ggf. anpassen, siehe Punkt 5).
- Fehlgeschlagene Abfrage (Timeout nach Retries) → `UpdateFailed`, HA setzt Entities `unavailable`;
  kein Crash der Integration, kein Reload nötig.
- Verbindung beim Start nicht erreichbar → `ConfigEntryNotReady`, HA versucht automatisch erneut.
- Schreiboperationen (`write_charge_power`/`write_discharge_power`) melden Erfolg/Fehler an den
  Aufrufer zurück (kein stiller Fehlschlag) — Analogie zu HEMS' eigenem `ha_client.py`-Vertrag
  („meldet je Schreiboperation Erfolg oder bereinigten Fehler zurück").

## 8. Entities pro Speicher-Instanz

| Entity | Plattform | Einheit | Richtung |
|---|---|---|---|
| `sensor.<prefix>_soc` | sensor | % | lesen |
| `sensor.<prefix>_ist_ladeleistung` | sensor | W | lesen |
| `sensor.<prefix>_ist_entladeleistung` | sensor | W | lesen |
| `number.<prefix>_soll_ladeleistung` | number | W | schreiben |
| `number.<prefix>_soll_entladeleistung` | number | W | schreiben |

Alle einem gemeinsamen `device_info` (Hersteller, Modell, `unique_id` des Entry) zugeordnet, damit
HA sie als ein Gerät gruppiert.

## 9. Anbindung an HEMS (Beispiel)

Sobald die Integration läuft, zeigt die HEMS-Add-on-Konfiguration direkt auf ihre Entities —
keine Änderung am HEMS-Code, nur an dessen Konfiguration:

```yaml
devices:
  - name: acspeicher1
    class: battery
    entity_prefix: acspeicher1
    soc_entity: sensor.marstek_venus1_soc
    charge_power_entity: sensor.marstek_venus1_ist_ladeleistung
    discharge_power_entity: sensor.marstek_venus1_ist_entladeleistung
    available_charge_power_w: 1500
    available_discharge_power_w: 1500
```

Die HEMS-eigenen Anforderungshelfer (`input_number...anforderung_leistung_w`,
`input_select...anforderung_betriebsart`) bleiben bestehen — eine schlanke HA-Automation (oder,
später, ein optionaler „Bridge"-Baustein dieser Integration) übersetzt sie weiterhin in
`number.<prefix>_soll_ladeleistung` / `_soll_entladeleistung`. Das ist bewusst **nicht** Teil
dieser Integration selbst, um die HEMS-Grenze („kein direktes Schalten") nicht zu verwischen.

## 10. Nicht-Ziele

- Keine eigene Persistenz — HA-State/Config-Entries reichen.
- Kein Cloud-Zugriff auf Marstek-Server — ausschließlich lokal (LAN).
- Kein Ersatz des HEMS-Anforderungsvertrags (`anforderung_leistung_w`/`anforderung_betriebsart`).
- Keine Regel-/Verteilungslogik — die bleibt vollständig bei HEMS.

## 11. Repo-Grundgerüst (für den Start im neuen Repo)

- `hacs.json` (`{"name": "Battery Bridge", "content_in_root": false}`), `README.md` mit
  Kurzbeschreibung + unterstützten Herstellern, `LICENSE`.
- `manifest.json`: `"iot_class": "local_polling"`, `"config_flow": true`,
  `"integration_type": "hub"` (mehrere Geräte pro Hersteller, aber jeder Speicher eigener Entry →
  eher `"device"` je Entry — beim Anlegen gegen aktuelle HA-Dev-Docs prüfen, ändert sich gelegentlich).
- CI: `pytest` + `ruff` wie im HEMS-Repo, plus `hassfest`/`hacs` Validierungsworkflow (HA-Standard
  für Integrationen, prüft `manifest.json`/`hacs.json`-Konsistenz).

## 12. Nächste Schritte

1. Marstek Open-API-Doku vollständig lesen, exakte Commands für Punkt 5 festhalten.
2. Neues Repo anlegen, dieses Dokument dorthin kopieren, `AGENTS.md`/`CLAUDE.md` fürs neue Repo
   aufsetzen (eigene Regeln — kein Blindübernehmen der HEMS-Regeln, da anderer Artefakttyp).
3. Scaffold gemäß Abschnitt 3 aufsetzen, `marstek_udp`-Adapter zuerst mit Lesezugriff (SoC,
   Ist-Leistung), Schreibzugriff erst nach Klärung von Punkt 5.
4. An echter Venus E 3.0 testen: Poll-Intervall aus Punkt 7 anhand gemessener Reaktionszeit justieren.
5. HEMS-Konfiguration (im HEMS-Repo, nicht hier) auf die neuen Entities umstellen, alte
   Modbus-Automation ablösen.
