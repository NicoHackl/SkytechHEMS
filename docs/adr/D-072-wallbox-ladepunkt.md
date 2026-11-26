# D-072 — Virtueller Ladepunkt und wählbare Regelungsquelle

- Datum: 26.11.2026
- Status: Fachliches Zielbild vereinbart. Geräteklasse und Profilwahl sind geplant.

Je unabhängig steuerbarem Anschluss wird im HEMS ein dauerhafter Ladepunkt
eingerichtet. Eine eigene Geräteklasse Wallbox ist vorgesehen. EVMS kann daran
wechselnde Fahrzeuge zuordnen. Dadurch kann der Betreiber etwa der Garage Vorrang
geben oder die Priorität des jeweiligen Fahrzeugs an dessen Ladepunkt übernehmen.

Die Wahl der Regelungsquelle betrifft die betrieblichen Einstellungen. Der in
[D-071](D-071-wallbox-watt-anbindungen.md) festgelegte Befehlsweg gilt für beide
Quellen. Für Anlagen ohne Fahrzeugverwaltung ist die Direktanbindung vorgesehen.
Die technische Maximalleistung gilt je Wallbox. Eine übergreifende
Anschlussbegrenzung ist ein separates HEMS-Thema.

[Konfiguration und Direktbetrieb](../device_classes/charging.md) ·
[HEMS–EVMS-Vertrag](../../contract/contract_hems_evms/contract_hems_evms.md)
