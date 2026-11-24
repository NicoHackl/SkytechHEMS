# Watt-Ladeprotokoll 1 — HEMS und Ladeempfänger

**Stand: 21.10.2026. Protokollversion: 1.**

**Status:** HEMS implementiert und softwaregetestet; EVMS und die Watt-Umsetzung
im Wallbox-Provider sind Entwurf. Eigene Automationen müssen den Vertrag selbst
implementieren. Kein Weg ist damit bereits an echter Wallbox abgenommen.

Diese Datei liegt identisch bei den Verträgen HEMS–EVMS, HEMS–Wallbox-Provider
und HEMS–Automation. Bilaterale Dateien benennen den Status der jeweiligen Gegenstelle.

## Konfiguration im HEMS

`class: controllable`, `output_unit: watt`, `charging_backend` genau eines aus
`evms`, `wallbox_provider`, `automation`. Das HEMS-Präfix identifiziert ein Ladeziel,
nicht zwangsläufig ein Fahrzeug oder einen physischen Anschluss.
`charging_feedback_timeout_s` ist eine positive endliche Zahl, voreingestellt 90 s.
Die Frist ist vor Inbetriebnahme passend zum Rückmeldetakt festzulegen.
`actual_power_entity` bleibt leer: Istleistung kommt aus dem Schnittstellen-Schnappschuss.

Die vorhandenen sechs Grenz-/Rampenfelder bleiben verpflichtend, ausschließlich in
Watt beziehungsweise Sekunden. Geräte ohne `charging_backend` behalten die bisherige
Watt-/Ampere-Regelung und das bisherige Freigabeverhalten.

| Anbindung | Rückmeldung an HEMS |
|---|---|
| `evms` | `sensor.evms_schnittstelle` |
| `wallbox_provider` | `sensor.wallbox_provider_schnittstelle` |
| `automation` | `sensor.wallbox_automation_schnittstelle` |

## Rückmeldung

Der gewählte Empfänger veröffentlicht eine Schnittstellen-Entität für alle seine
Ladeziele. State: Präfixliste, durch Komma getrennt. Attribute eines Schnappschusses
werden zusammen geschrieben, nicht einzeln nachgetragen.

| Attribut | Typ / Einheit | Pflicht / Bedeutung |
|---|---|---|
| `ladevertrag_version` | Integer | Exakt `1`; unabhängig von älteren Provider-Vertragsversionen |
| `instanz_id` | nichtleerer String | Neue zufällige Prozesskennung bei jedem Start des Herausgebers |
| `<prefix>_rueckmeldung_zaehler` | Integer ≥ 0 | Ändert sich nach jeder neuen vollständigen Rückmeldung für dieses Ziel, auch bei gleichen Messwerten |
| `<prefix>_zuordnung_id` | nichtleerer String | Neue Kennung bei neuer Verbindung/Zuordnung, Fahrzeug- oder Anschlusswechsel; alte Vorgaben werden ungültig |
| `<prefix>_freigabe` | echter Bool | Nur `true` erlaubt die Zuteilung; fehlend/ungültig/false sperrt |
| `<prefix>_sperrgrund` | String oder null | Verständlicher Sperrgrund, optional |
| `<prefix>_istleistung_w` | endliche Zahl ≥ 0 | Tatsächlich gemessene Leistung, niemals ersatzweise geschätzte null |
| `<prefix>_minimum_w` | endliche Zahl ≥ 0 | Aktuell kleinste nutzbare positive Leistungszuteilung; null nur bei tatsächlich stufenlosem Verhalten |
| `<prefix>_maximum_w` | endliche Zahl ≥ Minimum | Aktuell nutzbare Obergrenze; 0 sperrt |

Die veröffentlichten Grenzen berücksichtigen Gerät, Kabel, Fahrzeug soweit bekannt,
Phasenbetrieb und aktuelle Einschränkungen. Gemeinsame Anschlusslimits mehrerer Geräte
sind gesondert zu lösen; die erste Implementierung garantiert sie nicht automatisch.

HEMS bildet das Maximum der konfigurierten und gemeldeten Untergrenzen und das Minimum
der Obergrenzen. Keine positive nutzbare Spanne, fehlende Leistung, falsche Version oder
fehlende Freigabe ⇒ Ziel inaktiv, bedingungslos null schreiben, auch unter Zwang.
Ein State `unknown`/`unavailable` bleibt trotz alter Attribute ungültig.

Frische wird über beobachtete Änderungen des Tupels Prozesskennung/Zuordnung/Zähler
und eine lokale monotone Uhr ermittelt. Der erste Schnappschuss nach Start oder
Zuordnungswechsel zählt nicht als Lebenszeichen. Erst eine weitere Probe derselben
Prozess-/Zuordnungskennung erlaubt Laden. Bleibt der Zähler bis zur Frist unverändert,
stoppt HEMS das Ziel. Ein Herausgeber darf seinen Zähler nicht allein aufgrund eines
Timers erhöhen, wenn die zugrunde liegende Messung oder der vorgelagerte Dienst ausgefallen ist.

## Wattvorgabe und Zuordnungsbestätigung

HEMS schreibt ausschließlich `input_number.ems_<prefix>_anforderung_leistung_w`.
0 bedeutet Stopp; positive Werte sind Leistungsbudgets, keine Garantie der tatsächlichen
Leistungsaufnahme. HEMS schreibt für diese Wege weder Ampere noch eine Phasenanzahl.
Der Helfer muss 0 sowie den konfigurierten Leistungsbereich darstellen können; vor
Inbetriebnahme passend anlegen. HEMS-interne Ersatzwerte sind keine Ausgabehelfer.

Zusätzlich veröffentlicht HEMS **nach** der Schreibcharge in `sensor.hems_schnittstelle`:

- `ladevertrag_version: 1`;
- `ladeziele`: Objekt mit Schlüssel `<prefix>` und den Feldern `anbindung`,
  `zuordnung_id`, `leistung_w`;
- das bestehende Lebenszeichen `zyklus_zaehler` und `zyklus_intervall_s`.

`leistung_w` bestätigt das Budget für genau diese Zuordnung. Bei Schreibfehler,
inaktivem Ziel oder Notabschaltung steht dort 0. Auch bei unverändertem Helferwert
wird der Commit nach dem Zyklus veröffentlicht. Der bestehende State mit Speicherpräfixen
und `vertrag_version: 2` bleiben aus Kompatibilitätsgründen unverändert; `ladeziele`
ist eine ausdrücklich dokumentierte additive Erweiterung.

**Pflichten des Empfängers vor jeder positiven Geräteausgabe:**

1. Eigene aktuelle Zuordnung und aktiver Befehlsgeber müssen zum Commit passen.
2. `anbindung` muss zum gewählten Weg passen; Version 1 muss unterstützt sein.
3. HEMS-Lebenszeichen muss frisch sein. Erster restaurierter Stand ist kein Lebenszeichen.
   Standardfrist wie im bestehenden Provider: 3 × gültiges Zyklusintervall, sonst 90 s.
4. Aktueller Helferwert und bestätigtes Budget müssen übereinstimmen und gültig sein.
   Bei Zwischenständen kurz stoppen und den nächsten konsistenten Stand abwarten.
5. Eigene Messung, Gerätefreigabe und technische Grenzen müssen gültig sein.

Fehlt eine Voraussetzung ⇒ Stopp. Null in Helfer oder Commit gilt sofort. Alte positive
Budgets dürfen niemals auf eine neue Zuordnung übertragen werden. Ein EVMS darf das
Lebenszeichen des HEMS nicht durch sein eigenes ersetzen.

Die technische Umsetzung wählt eine zulässige Strom-/Phasenkombination innerhalb des
Budgets und meldet die Istleistung zurück. Kein Aufrunden auf eine höhere Ladestufe.
Phasenumschaltung und deren Schutzzeiten liegen beim Provider beziehungsweise bei der
Eigenautomation. Verhalten und Messtoleranzen werden an Hardware geprüft.

## Betrieb und Migration

Genau ein Steuerungsweg pro physischem Anschluss; direkte und virtuelle Abbildung desselben
Anschlusses nicht parallel im HEMS eintragen. Konfigurationsprüfung über Repo-/Systemgrenzen
ist noch nicht implementiert. Kein automatischer Ausweichweg bei EVMS-Ausfall.

Bestehende Ampere-Installationen werden nicht automatisch konvertiert. Der Nutzer richtet
Watt-Helfer und Wattgrenzen ein, aktiviert einen passenden Empfänger und wechselt dann
bewusst die HEMS-Anbindung. Der bisherige Provider 2.1 unterstützt dieses Protokoll noch nicht.

## Softwareprüfung

HEMS: `tests/test_charging.py` plus bestehende Konfigurations-, Controller-,
Notabschaltungs- und Publisher-Tests. Gegenstellen-/Hardwaretests stehen noch aus.
