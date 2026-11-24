"""Zeichnet aus regelverhalten_daten.json das SVG regelverhalten.svg (gestapelte Leistungen über dem Überschuss).

Aufruf: python docs/grafiken/regelverhalten_grafik.py (nach regelverhalten_simulation.py)
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
rows = json.loads((HERE / "regelverhalten_daten.json").read_text(encoding="utf-8"))

W, H = 1520, 700
ML, MR, MT, MB = 80, 440, 90, 150
PW, PH = W - ML - MR, H - MT - MB
T_MAX = rows[-1]["t"]
Y_MAX = 13000


def x(t): return ML + PW * t / T_MAX
def y(w): return MT + PH * (1 - w / Y_MAX)


SERIES = [  # von unten nach oben gestapelt: Reihenfolge = Priorität
    ("e3dc", "E3DC Speicher (Laden, Prio 5)", "c-e3dc"),
    ("heizstab", "Heizstab (Prio 10)", "c-stab"),
    ("heizlufter", "Heizlüfter 1 (Prio 20, binär)", "c-fan"),
]


def clock(t):
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def first_change(key, thr=1.0):
    return next((r["t"] for r in rows if r[key] > thr), None)


out = []
a = out.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="system-ui, -apple-system, Segoe UI, sans-serif">')
a("""<title>HEMS-Regelverhalten bei steigendem PV-Überschuss</title>
<desc>Simulation mit dem echten HEMS-Regelcode: gestapelte Leistung von E3DC Speicher, Heizstab und Heizlüfter 1 über dem PV-Überschuss. AC Speicher 1 hat keine Freigabe.</desc>
<style>
 :root{--bg:#fff;--fg:#1c1c1c;--mut:#6b7280;--grid:#e5e7eb;--acc:#18BCF2;--c-e3dc:#18BCF2;--c-stab:#F08C00;--c-fan:#7048E8;--mut-fill:#6b7280;--line:#1c1c1c}
 @media (prefers-color-scheme:dark){:root{--bg:#111;--fg:#f3f4f6;--mut:#9ca3af;--grid:#2f3237;--line:#f3f4f6;--c-stab:#FFA94D;--c-fan:#9775FA;--mut-fill:#9ca3af}}
 text{fill:var(--fg)} .mut{fill:var(--mut)} .grid{stroke:var(--grid);stroke-width:1}
 .area-e3dc{fill:var(--c-e3dc)} .area-stab{fill:var(--c-stab)} .area-fan{fill:var(--c-fan)}
 .surplus{fill:none;stroke:var(--line);stroke-width:2.5}
 .limit{stroke:var(--c-e3dc);stroke-width:1.5;stroke-dasharray:6 4;fill:none}
 .prot{stroke:var(--fg);stroke-width:1;stroke-dasharray:1 4;fill:none;opacity:.7}
 .ev{stroke:var(--mut);stroke-width:1;stroke-dasharray:2 3}
</style>""")
a(f'<rect width="{W}" height="{H}" fill="var(--bg)"/>')
a(f'<text x="{ML}" y="34" font-size="20" font-weight="600">HEMS-Regelverhalten bei steigendem PV-Überschuss</text>')
a(f'<text x="{ML}" y="56" font-size="13" class="mut">Simulation mit dem echten Regelcode (app/ems), Helferwerte der Anlage vom 26.10.2026 · Zyklus 4 s · AC Speicher 1 ohne Freigabe (0 W)</text>')

# Gitter und Achsen
for w in range(0, Y_MAX, 2000):
    a(f'<line class="grid" x1="{ML}" x2="{ML+PW}" y1="{y(w):.1f}" y2="{y(w):.1f}"/>')
    a(f'<text class="mut" x="{ML-10}" y="{y(w)+4:.1f}" font-size="12" text-anchor="end">{w:,}'.replace(",", ".") + '</text>')
for m in range(0, int(T_MAX // 60) + 1, 4):
    a(f'<line class="grid" x1="{x(m*60):.1f}" x2="{x(m*60):.1f}" y1="{MT}" y2="{MT+PH}"/>')
    a(f'<text class="mut" x="{x(m*60):.1f}" y="{MT+PH+20}" font-size="12" text-anchor="middle">{m:02d}:00</text>')
a(f'<text class="mut" x="{ML+PW/2}" y="{MT+PH+42}" font-size="13" text-anchor="middle">Zeit seit Simulationsbeginn (mm:ss)</text>')
a(f'<text class="mut" transform="translate(22 {MT+PH/2}) rotate(-90)" font-size="13" text-anchor="middle">PV-Überschuss / Leistung in W</text>')

# gestapelte Flächen
lower = [0.0] * len(rows)
for key, label, cls in SERIES:
    upper = [lo + r[key] for lo, r in zip(lower, rows)]
    pts = [f"{x(r['t']):.1f},{y(u):.1f}" for r, u in zip(rows, upper)]
    pts += [f"{x(r['t']):.1f},{y(lo):.1f}" for r, lo in reversed(list(zip(rows, lower)))]
    area = {"e3dc": "area-e3dc", "heizstab": "area-stab", "heizlufter": "area-fan"}[key]
    a(f'<polygon class="{area}" fill-opacity="0.85" points="{" ".join(pts)}"/>')
    lower = upper

# E3DC-Grenzen (absolut, da E3DC die unterste Schicht ist)
a(f'<line class="prot" x1="{ML}" x2="{ML+PW}" y1="{y(3000):.1f}" y2="{y(3000):.1f}"/>')
a(f'<text x="{ML+6}" y="{y(3000)-5:.1f}" font-size="11" class="mut">E3DC geschützte Mindestleistung 3.000 W</text>')
# Ladelimit E3DC (Ladestufe 1) und Überschusslinie
a(f'<line class="limit" x1="{ML}" x2="{ML+PW}" y1="{y(5200):.1f}" y2="{y(5200):.1f}"/>')
a(f'<text x="{ML+6}" y="{y(5200)-6:.1f}" font-size="11" class="mut">E3DC Ladelimit 5.200 W (Ladestufe 1, SoC 40–80 %)</text>')
a('<polyline class="surplus" points="' + " ".join(f"{x(r['t']):.1f},{y(r['surplus']):.1f}" for r in rows) + '"/>')

# Ereignismarken
events = [
    (first_change("e3dc"), "E3DC lädt"),
    (first_change("heizstab"), "Heizstab ein"),
    (first_change("heizlufter"), "Heizlüfter ein"),
]
for n, (t, label) in enumerate(events):
    if t is None:
        continue
    yy = MT + 14 + n * 16
    a(f'<line class="ev" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{yy+4}" y2="{MT+PH}"/>')
    sur = next(r["surplus"] for r in rows if r["t"] == t)
    sur_txt = f"{sur:,.0f}".replace(",", ".")
    a(f'<text x="{x(t)+5:.1f}" y="{yy+4}" font-size="11" font-weight="600">{label} ({clock(t)}, Überschuss {sur_txt} W)</text>')

# Werte je Gerät in den Bändern, an Plateau-Zeitpunkten
for t in [300, 620, 960, 1340, 1800]:
    r = next(r for r in rows if r["t"] >= t)
    base = 0.0
    for key, label, cls in SERIES:
        v = r[key]
        if v >= 400:
            a(f'<text x="{x(r["t"]):.1f}" y="{y(base + v/2)+4:.1f}" font-size="12" font-weight="700" text-anchor="middle" '
              f'fill="#fff" stroke="#000" stroke-opacity=".35" stroke-width="3" paint-order="stroke">{v:,.0f} W'.replace(",", ".") + '</text>')
        base += v

# ungenutzter Überschuss am Ende
last = rows[-1]
rest = last["surplus"] - last["e3dc"] - last["heizstab"] - last["heizlufter"]
xr = x(last["t"]) - 140
top = last["e3dc"] + last["heizstab"] + last["heizlufter"]
a(f'<text x="{xr:.1f}" y="{y(top + rest/2)+4:.1f}" font-size="12" font-weight="600" text-anchor="middle">ungenutzt {rest:,.0f} W'.replace(",", ".") + ' (alle Geräte am Limit)</text>')

# Grenzwert-Tafel rechts
tx = ML + PW + 24
a(f'<text x="{tx}" y="{MT+16}" font-size="14" font-weight="600">Leistungsgrenzen (Anlage, Test)</text>')
panel = [
    ("E3DC Speicher · Prio 5", "c-e3dc", ["Ladelimit 5.200 W (Stufe 1, SoC 40–80 %)", "Geschützte Mindestleistung 3.000 W", "Schritt min. 25 W · Regelzeit 3 s"]),
    ("Heizstab · Prio 10", "c-stab", ["Maximum 3.500 W", "Geschützte Mindestleistung 1.000 W (Testannahme)", "Schritt min. 50 W, max. 1.000 W"]),
    ("Heizlüfter 1 · Prio 20 (binär)", "c-fan", ["Leistung 1.500 W (ein/aus)", "Einschalten ab Überschuss 5.500 W (3.000 + 1.000 + 1.500)", "Mindestlaufzeit 120 s · Einschaltverzögerung 0 s"]),
    ("AC Speicher 1 · Prio 8", "mut", ["Keine Freigabe (Testannahme) → 0 W"]),
    ("Global", "mut", ["Alle Reserven und Puffer 0 W (Testannahme)", "Mindestleistungs-Scope: binär + regelbar"]),
]
cy = MT + 46
for title, col, lines in panel:
    a(f'<rect x="{tx}" y="{cy-10}" width="12" height="12" fill="var(--{col if col != 'mut' else 'mut-fill'})"/>')
    a(f'<text x="{tx+20}" y="{cy}" font-size="13" font-weight="600">{title}</text>')
    for ln in lines:
        cy += 17
        a(f'<text x="{tx+20}" y="{cy}" font-size="12" class="mut">{ln}</text>')
    cy += 30

# Legende
ly = MT + PH + 66
a(f'<line x1="{ML}" x2="{ML+28}" y1="{ly}" y2="{ly}" stroke="var(--line)" stroke-width="2.5"/>')
a(f'<text x="{ML+36}" y="{ly+4}" font-size="13">PV-Überschuss (Eingang, nur steigend/gleichbleibend)</text>')
for n, (key, label, cls) in enumerate(SERIES):
    lx = ML + (n % 3) * 330
    yy = ly + 26
    area = {"e3dc": "area-e3dc", "heizstab": "area-stab", "heizlufter": "area-fan"}[key]
    a(f'<rect class="{area}" x="{lx}" y="{yy-10}" width="28" height="14" fill-opacity="0.85"/>')
    a(f'<text x="{lx+36}" y="{yy+2}" font-size="13">{label}</text>')
a(f'<text class="mut" x="{ML}" y="{ly+54}" font-size="12">Der Abstand zwischen Überschusslinie und Flächenoberkante ist ungenutzter Überschuss (Einspeisung ins Netz).</text>')
a(f'<text class="mut" x="{ML}" y="{ly+72}" font-size="12">Geschützte Mindestleistung: E3DC 3.000 W, Heizstab 1.000 W. Der Heizlüfter (1.500 W) schaltet erst ein, wenn sie beide zusätzlich gedeckt sind: ab 5.500 W Überschuss.</text>')
a("</svg>")

(HERE / "regelverhalten.svg").write_text("\n".join(out), encoding="utf-8")
print("regelverhalten.svg geschrieben")
