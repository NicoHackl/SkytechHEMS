# Bekannte Bugs

Stand: 2026-06-15

Sammlung bekannter, noch nicht behobener Fehler. Schweregrad: 🔴 hoch · 🟠 mittel-hoch · 🟡 mittel · 🟢 niedrig.

---

## 1. 🟢 Debug-Schalter fehlt im Steuerung-Tab der Web-UI

**Ort:** [app/main.py](app/main.py#L48-L53) → `_GLOBAL_CTRL_ITEMS`

**Beschreibung:**
Die README beschreibt `input_boolean.ems_pyems_debug_output` als Laufzeit-Schalter
für das Zyklus-Logging (Abschnitt „Globale Helfer" sowie „Laufzeit-Schalter, kein
Add-on-Neustart nötig"). Der Steuerung-Tab soll laut README „alle relevanten
Helfer-Entitäten" editierbar machen. In `_GLOBAL_CTRL_ITEMS` fehlt dieser Toggle
jedoch, sodass er sich nicht über die UI ein-/ausschalten lässt — nur direkt in
Home Assistant.

Der Controller liest die Entität korrekt (`HA_DEBUG_OUTPUT`,
[controller.py:27](app/ems/controller.py#L27) / [:147](app/ems/controller.py#L147));
betroffen ist ausschließlich die Bedienbarkeit über die UI.

**Erwartet:** Toggle „Debug-Logging" in der Global-Karte des Steuerung-Tabs.

**Möglicher Fix:** Eintrag
`{"entity": "input_boolean.ems_pyems_debug_output", "label": "Debug-Logging"}`
zu `_GLOBAL_CTRL_ITEMS` ergänzen.

---

## 2. 🟢 Spannungs-Plausibilitätsbereich schließt 180 V und 260 V aus

**Ort:** [app/ems/devices.py:260](app/ems/devices.py#L260) → `update_from_ha` / `_read_v`

**Beschreibung:**
Die README nennt für die Phasenspannungssensoren einen Plausibilitätsbereich von
„180 – 260 V" (klingt inklusive). Der Code prüft strikt `180.0 < v < 260.0`,
wodurch exakt 180 V oder 260 V als unplausibel gelten und auf den Fallback 230 V
zurückfallen.

**Auswirkung:** In der Praxis vernachlässigbar (Nennspannung 230 V), aber Doku und
Code sind an den Bereichsgrenzen uneinig.

**Möglicher Fix:** Entweder `180.0 <= v <= 260.0` im Code, oder Klarstellung in der
README, dass die Grenzen exklusiv gemeint sind.

---

## 3. 🟠 Ampere-Modus: Schreib-/Deadband-Guard rechnet in Watt statt Ampere

**Ort:** [app/ems/devices.py:461-489](app/ems/devices.py#L461-L489) → `get_write_ops`

**Beschreibung:**
`delta`, `is_on_off` und der Deadband-Vergleich rechnen in **Watt**, der tatsächlich
an HA geschriebene Wert ist aber **abgerundete Ampere** (`floor(new_w / eff)`). Eine
Watt-Änderung unterhalb von 1 A (z. B. durch Pool-Schwankungen) ergibt denselben
Ampere-Wert, löst bei `deadband_w == 0` aber trotzdem einen Schreibvorgang aus → der
**identische Ampere-Wert wird erneut geschrieben**. Genau das soll der Guard laut
eigenem Kommentar verhindern: Der erneute Write setzt `last_changed` zurück, was das
Rampen-Timing (`hoch_regelzeit_s` / `runter_regelzeit_s`) stört und unnötige
HA-API-Writes pro Zyklus erzeugt. (Bestätigt per Code-Trace: `new_w = 4900 W` bei 7 A
in HA → schreibt erneut 7 A.)

**Auswirkung:** Nur im `output_unit=ampere`-Modus (Wallbox), v. a. bei
`min_anderung_pro_schritt_a = 0`.

**Möglicher Fix:** Im Ampere-Modus die Ziel- gegen die Ist-**Ampere** vergleichen
(`floor(new_w / eff)` vs `floor(anforderung_current_w / eff)`) und nur bei Differenz
oder An/Aus-Wechsel schreiben; Deadband ebenfalls in Ampere prüfen.

---

## 4. 🟠 Pool-Berechnung filtert nicht nach Eligibility (Inkonsistenz + README-Abweichung)

**Ort:** [app/ems/controller.py:257-262](app/ems/controller.py#L257-L262) (`_calc_pool`),
[app/ems/devices.py:239-240](app/ems/devices.py#L239-L240) & [:582-583](app/ems/devices.py#L582-L583) (`current_w`)

**Beschreibung:**
`_calc_pool` summiert `current_w` über **alle** Geräte, unabhängig von `eligible`.
`current_w` ist nicht eligibility-gegated (regelbar = `actual_w`; binär = `power_w`
wenn `actual_on`) — obwohl `consume_from_pool` sehr wohl auf `eligible` prüft
([devices.py:388](app/ems/devices.py#L388), [:608](app/ems/devices.py#L608)). Ein
physisch laufendes, aber **nicht** vom EMS geregeltes Gerät (manuell eingeschaltet
oder gerade deaktiviert) wird damit in den Pool zurückgerechnet → Pool zu groß →
Über-Allokation / möglicher Netzbezug. Die README sagt ausdrücklich „Σ current_w der
**aktuell vom EMS geschalteten** Geräte".

**Status:** Designabsicht zu prüfen. Die Inkonsistenz zur Eligibility-Prüfung in
`consume_from_pool` ist real; ob nicht-eligible, physisch laufende Geräte mitzählen
sollen, ist eine bewusste Entscheidung.

**Möglicher Fix (falls bestätigt):** `current_w` bzw. die Pool-Summe in `_calc_pool`
auf `eligible` Geräte beschränken.

---

## 5. 🟡 Schreibfehler werden verschluckt (nicht an UI/`_last_error` gemeldet)

**Ort:** [app/ha_client.py:79-95](app/ha_client.py#L79-L95) (`execute_write_ops`),
[app/main.py:117-136](app/main.py#L117-L136) (`_run_cycle`)

**Beschreibung:**
Nicht-2xx-Antworten und Exceptions beim Schreiben werden in `execute_write_ops` nur
**geloggt**, nicht geworfen. Der Zyklus gilt danach als erfolgreich
(`_last_error = ""`). Ein vertippter HA-Helfername (ein zentrales README-Thema)
schlägt damit **jeden Zyklus still fehl** — in der Web-UI ist kein Fehler sichtbar.
(`call_service`, genutzt für das Post-Cycle-Skript, wirft hingegen sehr wohl.)

**Möglicher Fix:** Fehlgeschlagene Write-Ops zählen/sammeln und im Status-Snapshot
(`/api/status`) bzw. in `_last_error` sichtbar machen.

---

## 6. 🟡 README „Architektur" und „Repository-Layout" sind veraltet

**Ort:** [README.md:49-60](README.md#L49-L60) (Architektur),
[README.md:387-410](README.md#L387-L410) (Repository-Layout)

**Beschreibung:**
Beide Diagramme zeigen `templates/index.html` als „Web-UI" und **fehlen**:
`app/static/app.js` + `app/static/styles.css` (die eigentliche UI-Logik seit der
Auslagerung), das `tests/`-Verzeichnis (5 Testdateien), `pyproject.toml`,
`requirements-dev.txt` sowie `.github/workflows/ci.yaml` (nur `bump-version.yaml` ist
gelistet). `index.html` ist heute nur noch die HTML-Hülle, die `static/app.js` und
`static/styles.css` lädt.

**Möglicher Fix:** Beide Abschnitte an die reale Verzeichnisstruktur angleichen.

---

## 7. 🟢 Translations behaupten falsch, der Debug-Helfer schalte den Log-Level um

**Ort:** [translations/de.yaml:75-77](translations/de.yaml#L75-L77),
[translations/en.yaml:71-75](translations/en.yaml#L71-L75)

**Beschreibung:**
Die `log_level`-Beschreibung sagt: „Der Log-Level kann auch zur Laufzeit über den
HA-Helfer `input_boolean.ems_pyems_debug_output` umgeschaltet werden". Tatsächlich
aktiviert dieser Helfer nur das zusätzliche Zyklus-Logging (`debug_output` in
[controller.py:147](app/ems/controller.py#L147)) — unabhängig vom Python-`log_level`.
Geringe Wirkung, da die Translations im YAML-Listenmodus von HA ohnehin kaum
angezeigt werden (die README ist maßgeblich).

**Möglicher Fix:** Formulierung in beiden Translations korrigieren (der Helfer steuert
„zusätzliches Regelentscheidungs-Logging", nicht den Log-Level).

---

## Bekannte, bewusst belassene Punkte (siehe `Claude-Analyse.md`)

Bereits in der früheren Analyse erfasst und bewusst nicht geändert — hier nur zur
Vollständigkeit, ohne erneute Beschreibung:

- **S1** 🟠 `/api/set` schreibt in *jede* `input_*`-Entität, nicht nur `ems_*`
  ([app/main.py:192-215](app/main.py#L192-L215)) — bewusst belassen (Single-User).
- **A5** 🟢 `HARD_LOCKOUT_THRESHOLD_W = -50000` als unkommentierte Magic Number
  ([app/ems/controller.py:34](app/ems/controller.py#L34)).
- **A1** ⏸️ Zeit-Guards (Mindestlaufzeit/Abschaltverzögerung) gelten auch bei
  Notabschaltung — bewusste Designentscheidung, in README dokumentiert.
- **S2** ⏸️ Server lauscht auf `0.0.0.0` + `EXPOSE` im Dockerfile.
- **Z2** ⏸️ Bump-Workflow pusht direkt auf `main`.
- **Z3** ⏸️ Voller State-Pull (`/api/states`) pro Zyklus.
