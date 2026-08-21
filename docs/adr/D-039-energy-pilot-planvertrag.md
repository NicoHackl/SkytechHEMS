# D-039: Semantischer Energy-Pilot-Planvertrag

## Status

Aktiv — 18.08.2026

## Kontext

Energy Pilot konnte Geräteklasse und Bedeutung der `ems_*`-Helfer bisher nur aus Entity-Namen
ableiten. Außerdem waren einzelne Vorschlagssensoren sofort sichtbar, sodass ein unterbrochener
Schreibvorgang alte und neue Planfelder mischen konnte. Abgelaufene Werte fielen nicht an einer
zentralen Stelle sicher zurück.

## Entscheidung

`/api/device_controls_schema` wird additiv um stabile Schlüssel, Datentyp, Einheit, semantische
Rolle und Planungsrelevanz aller Userinputs sowie um Geräteklasse, Modi, Regelprinzip,
Istleistungs-/Schaltentität und HEMS-Anforderung erweitert. Die bestehende Listenstruktur und die
Felder `entity`/`label` bleiben erhalten.

Ein Energy-Pilot-Plan wird atomar über `sensor.ep_plan_commit` sichtbar. HEMS akzeptiert pro Feld
nur einen Vorschlag mit gleicher `plan_id` und passender, aktueller Gültigkeit. Jeder Fehler führt
für genau dieses Feld zum vorhandenen Nutzerwert. Die Moduslogik entscheidet weiterhin, ob EP
überhaupt Quelle ist; technische Freigaben und Grenzen bleiben harte HEMS-Gates.

## Folgen

- Energy Pilot muss keine Namenssuffixe mehr erraten.
- Technische Grenzwerte können eindeutig von Messwerten unterschieden werden.
- Teilweise geschriebene und abgelaufene Pläne wirken nicht.
- Alte UI-Konsumenten des Schemas lesen ihre bisherigen Felder unverändert weiter.
