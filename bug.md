# Bekannte Bugs

Stand: 2026-06-15

Sammlung bekannter, noch nicht behobener Fehler. Schweregrad: 🔴 hoch · 🟡 mittel · 🟢 niedrig.

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
