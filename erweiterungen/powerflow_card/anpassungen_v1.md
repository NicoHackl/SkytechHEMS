# Optik (Skytech-Powerflow-Card)
- Optik ist aktuell nicht gut, und ähnlich aktuell überhautp nicht dem Original
- Schaue dir die Darstellung selber an über den MCP, im Test Dashoard auf der PV Seite
# Config (SkytechHEMS)
- Konfiguratin ist schlecht ich konnte das Addon nicht starten bevor ich nicht flow_battery_capacity_kwh in der Addon/App Config gepflegt habe, das darf kein Mussfeld sein um das Addon zu starten. Ehrlich gesagt weiß ich nicht warum das überhaupt für die Config der Flow Card gebraucht wird, das können wir weglassen.
# Feature (SkytechHEMS)
- Ich weiß nicht wie das aktuell berechnet/ermittelt wird, aber ich möchte bei Erzeugung einaml bei String leistungen angeben als Entität und einmal die PV Systemleistung angeben, dann muss natürlich verhindert werden (falls da im Hintergrund was berechnet wird) das die systemleistung oder die beiden einzelleistungen zusammengezählt werden, den sonst hätte ich ja eine doppelte Leistung
- Falls dem so ist würde ich einen boolean Schalter in der Config einbauen wo man angeben kann ob diese Entität zu der Leistungsberechnung hinzugefügt werden soll/muss