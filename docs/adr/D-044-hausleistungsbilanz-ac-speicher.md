# D-044: Separate Hausleistungsbilanz steuert die AC-Speicherentladung

> **Ergänzung:** [D-045](D-045-formel-basierte-sensorwerte.md) erlaubt zusätzlich eine im
> Ingress-Panel gepflegte, intern ausgewertete Formel als Alternative zu der hier beschriebenen
> externen HA-Vorlage. Diese Entscheidung bleibt unverändert gültig — die externe Vorlage
> funktioniert weiter.

- **Datum:** 21.08.2026
- **Status:** Aktiv
- **Betrifft:** [`app/configuration.py`](../../app/configuration.py),
  [`app/ems/controller.py`](../../app/ems/controller.py),
  [`app/ems/devices.py`](../../app/ems/devices.py), [`app/main.py`](../../app/main.py),
  [`config.yaml`](../../config.yaml), `web/src/` und die HA-Template-Vorlage unter
  [`erweiterungen/zusatz_sensor_für_speicher_null_einspeisung/`](../../erweiterungen/zusatz_sensor_für_speicher_null_einspeisung/)

> Diese Entscheidung ersetzt in [D-040](D-040-ac-speicher.md) ausschließlich die Quelle von
> `entlade_basis_w` und `hausdefizit_w`. Die PV-Pool-Berechnung, Pool-Bereinigung, Prioritäten
> und der signierte Speicher-Sollwert bleiben unverändert.

## Kontext

Der vorhandene Überschuss-Sensor ist absichtlich konservativ: Er stellt die Leistung zum Laden von
Überschussverbrauchern bereit. Für eine Nulleinspeisung durch AC-Speicher wäre er jedoch zu grob.
Mit den in dieser Anlage gewählten HA-Berechnungen würde ein AC-Speicher am Netzübergabepunkt etwa
`700 W` zu viel einspeisen.

Der vorhandene E3DC ist DC-gekoppelt und regelt seinen Akku selbst. Er soll kein
`BatteryDevice` werden. Wenn er eine Hauslast von `700 W` deckt, muss das HEMS diese Leistung
dennoch als Unterdeckung für die AC-Speicher erkennen; der E3DC nimmt seine Entladung danach
selbstständig zurück. Die gemessene Reaktionszeit des E3DC liegt unter zwei Sekunden, der
HEMS-Zyklus dieser Anlage bei drei Sekunden.

## Betrachtete Optionen

### Option A — Den Überschuss-Sensor auch für die Entladung verwenden

- Dafür: keine zusätzliche Konfiguration und kein zusätzlicher HA-Template-Sensor.
- Dagegen: der Sensor enthält bewusst Glättungen und Ladefreigaben. Für die Nulleinspeisung würde
  die Anlage rund `700 W` zu viel einspeisen.

### Option B — Einen reinen Netzleistungssensor zusätzlich absichern

- Dafür: direkter Messwert am Netzübergabepunkt.
- Dagegen: Der E3DC-Anteil fehlt. Das HEMS würde seine Entladung nicht als AC-Unterdeckung sehen;
  zusätzliche Rohsensor- und Abstimmungslogik wäre nötig.

### Option C — Eine signierte Hausleistungsbilanz aus Netz- und E3DC-Batterieleistung

- Dafür: ein einziger, gezielt formulierter Sensor enthält genau die AC-relevante Unterdeckung;
  der Überschuss-Sensor bleibt für seinen konservativen Zweck unverändert.
- Dagegen: Zwei Sensorverträge müssen nachvollziehbar dokumentiert und überwacht werden. Pool und
  Hausdefizit können im Status gleichzeitig positiv sein.

## Entscheidung

**Option C.** Die globale Add-on-Option heißt `battery_residual_power_entity`, die Oberfläche
zeigt sie als **„Hausleistungsbilanz für AC-Speicher"**. Sie ist Pflicht, sobald mindestens ein
`class: battery` konfiguriert ist.

Der Vertrag lautet: negativ = Netzbezug/Unterdeckung, positiv = Einspeisung. Für die vorhandenen
E3DC-Entitäten bildet Home Assistant den Sensor als

```text
−e3dc_leistung_netz + e3dc_leistung_batterie_laden − e3dc_leistung_batterie_entladen
```

Das HEMS hält die PV- und Verbraucherseite am bestehenden Überschuss-Sensor:

```text
residual_bereinigt_w = residual_w − Σ netz_support_w
pool_w               = max(residual_bereinigt_w + Σ current_w, 0)
```

Nur die Entladeplanung verwendet die neue Bilanz:

```text
battery_residual_bereinigt_w = battery_residual_w − Σ netz_support_w
entlade_basis_w               = battery_residual_bereinigt_w + Σ gemessene_last_w
hausdefizit_w                 = max(−entlade_basis_w, 0)
```

`input_number.ems_ac_speicher_entlade_abschlag_w` wird anschließend **einmal für die gesamte
Speicherflotte** abgezogen, nie pro Speicher. Fällt die Hausleistungsbilanz aus, schreibt das
HEMS alle AC-Speicher aktiv auf `0 W` und `standby`; der primäre Überschuss-Pool läuft weiter.

## Folgen

- **Positiv:** Die drei maßgeblichen Fälle (`−700 W`, `0 W`, `−1400 W`) liefern jeweils ein
  Entladeziel von `700 W` vor dem systemweiten Abschlag. Der E3DC bleibt ohne HEMS-Schreibzugriff
  selbstregulierend, während AC-Speicher die Nulleinspeisung nachführen.
- **Negativ:** Die Konfiguration braucht eine zusätzliche HA-Entity. Ein unbrauchbarer Wert sperrt
  die AC-Speicher aus Sicherheitsgründen, obwohl PV-Verbraucher weiterarbeiten können. Der
  Status muss zwei Sensoren erklären statt nur einen.
- **Aufwand:** Validierung, sichere Deaktivierung bei Konfigurationswechsel, Statusvertrag,
  Ingress-Formular, HA-Template, Tests und Dokumentation werden additiv erweitert.

## Rücknahmebedingung

Die Entscheidung wird überprüft, wenn mindestens eines dieser Signale auftritt:

1. **Der E3DC reagiert nicht mehr innerhalb eines HEMS-Zyklus** oder die History zeigt einen
   stabilen Grenzzyklus zwischen E3DC und AC-Speicher. Dann braucht es eine gedämpfte Übergabe oder
   eine andere Messgröße.
2. **Die Bilanz liefert trotz korrekter E3DC-Sensoren wiederholt falsche Vorzeichen** oder
   `unknown`/`unavailable`. Dann ist die HA-Template-Quelle nicht ausreichend belastbar und muss
   durch eine zuverlässigere Messkette ersetzt werden.
3. **Pool und Entladebedarf widersprechen sich dauerhaft in relevantem Umfang.** Dann sind die
   beiden Sensorverträge nicht mehr physikalisch konsistent; ein zusätzliches Diagnose- oder
   Freigabekonzept ist erforderlich.
