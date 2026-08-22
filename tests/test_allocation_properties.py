"""Property-based Invarianten für die ControllableDevice-Zuteilung (Hypothesis).

Statt einzelne Beispiele zu prüfen, erzeugt Hypothesis zufällige Geräte-
Konfigurationen und Pool-Größen und verifiziert die in der README zugesagten
Garantien. Diese Tests fangen ganze Klassen von Abweichungen automatisch ab –
insbesondere die Regression, dass geschuetzte_mindestleistung die Zuteilung
verändert.

`_allocate` spiegelt die 2-Durchlauf-Schleife aus EMSController.run_cycle
(controller.py, „Durchlauf 1: Minimum" + „Durchlauf 2: Überschuss") wider; die
Phasenwahl ist im Watt-Modus ein No-Op und hier bewusst ausgeklammert.
"""

import pytest
from hypothesis import given, strategies as st

from ems.controller import EMSController
from ems.devices import BinaryDevice, ControllableDevice
from test_run_cycle import CTRL_FALLBACKS

from conftest import make_states
from test_battery_device import battery_states, make_battery

TOL = 1e-6


def _make(min_w, max_w, geschuetzt, prio):
    d = ControllableDevice(
        id="d", allowed_modes=["auto"],
        entity_actual_w="sensor.x",
        entity_anforderung_w="input_number.ems_d_anforderung_leistung_w",
    )
    d.eligible = True
    d.priority = prio
    d.min_technisch_w = min_w
    d.max_technisch_w = max_w
    d.geschuetzte_mindestleistung_w = geschuetzt
    return d


def _allocate(devices, pool):
    """Wie controller.run_cycle: erst Minimum (Prio-Reihenfolge), dann Überschuss."""
    ordered = sorted(devices, key=lambda d: d.priority)
    remaining = pool
    for d in ordered:
        remaining = d.allocate_minimum(remaining)
    for d in ordered:
        remaining = d.allocate_surplus(remaining)
    return remaining


# ---- Strategien: realistische Geräte (0 <= min <= max) ----

_power = st.floats(min_value=0.0, max_value=20000.0, allow_nan=False, allow_infinity=False)
_pool  = st.floats(min_value=0.0, max_value=60000.0, allow_nan=False, allow_infinity=False)


@st.composite
def _device_params(draw):
    min_w = draw(st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False))
    max_w = draw(st.floats(min_value=min_w, max_value=20000.0, allow_nan=False, allow_infinity=False))
    geschuetzt = draw(_power)
    prio = draw(st.integers(min_value=1, max_value=10))
    return (min_w, max_w, geschuetzt, prio)


_devices = st.lists(_device_params(), min_size=1, max_size=5)


@given(params=_devices, pool=_pool)
def test_floor_cap_conservation(params, pool):
    devices = [_make(*p) for p in params]
    remaining = _allocate(devices, pool)

    assert remaining >= -TOL
    for d in devices:
        assert d.alloc_w >= -TOL
        # Cap: nie über das technische Maximum
        assert d.alloc_w <= d.max_technisch_w + TOL
        # Floor: entweder aus (0) oder mindestens das technische Minimum
        assert d.alloc_w <= TOL or d.alloc_w >= d.min_technisch_w - TOL

    # Erhaltung: Summe der Zuteilungen + Rest == Pool (nichts erzeugt/verloren)
    total = sum(d.alloc_w for d in devices)
    assert total + remaining == pytest.approx(pool, abs=1e-4)


@given(params=_devices, pool=_pool)
def test_surplus_fully_distributed(params, pool):
    # Bleibt nach der Zuteilung Pool übrig, MUSS jedes Gerät entweder aus (0) oder
    # am technischen Maximum sein – sonst wäre absorbierbarer Überschuss verschenkt.
    devices = [_make(*p) for p in params]
    remaining = _allocate(devices, pool)
    if remaining > TOL:
        for d in devices:
            assert d.alloc_w <= TOL or d.alloc_w >= d.max_technisch_w - TOL


@given(params=_devices, pool=_pool, alt=st.lists(_power, min_size=1, max_size=5))
def test_allocation_independent_of_geschuetzte(params, pool, alt):
    # Kernregression: geschuetzte_mindestleistung darf die Zuteilung NICHT verändern.
    # Identische Geräte, nur die geschützte Mindestleistung variiert → identische
    # Zuteilung. Auf dem fehlerhaften Code (max(min, geschuetzt)) schlägt das fehl.
    base = [_make(*p) for p in params]
    _allocate(base, pool)
    base_alloc = [d.alloc_w for d in base]

    variant = []
    for i, (min_w, max_w, _g, prio) in enumerate(params):
        variant.append(_make(min_w, max_w, alt[i % len(alt)], prio))
    _allocate(variant, pool)
    variant_alloc = [d.alloc_w for d in variant]

    assert base_alloc == variant_alloc


@given(min_w=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
       extra=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
       geschuetzt=_power)
def test_single_device_runs_whenever_pool_covers_min_technisch(min_w, extra, geschuetzt):
    # Sobald der Pool das technische Minimum trägt, läuft ein einzelnes Gerät –
    # unabhängig von der geschützten Mindestleistung.
    max_w = min_w + extra + 1.0   # sicher > min_w
    pool = min_w + extra          # >= min_w
    d = _make(min_w, max_w, geschuetzt, prio=1)
    remaining = d.allocate_minimum(pool)
    d.allocate_surplus(remaining)
    assert d.alloc_w >= min_w - TOL
    assert d.alloc_w == pytest.approx(min(pool, max_w), abs=1e-4)


# ===========================================================================
# Speicher-Invarianten P1–P7
# ===========================================================================
#
# Die Zuteilungs-Invarianten (P3, P4) gelten auf der Ebene der Zuteilung, NICHT
# auf der des geschriebenen Sollwerts. Das ist Absicht: die asymmetrische
# Entladerampe hält bei einer kleinen Zielabsenkung den Sollwert bewusst
# vorübergehend über dem Ziel – genau das ist das Gegenmittel gegen den
# Sensor-Versatz (H-7). Auf Sollwertebene gilt deshalb nur die Monotonie-Form P6.

_soc      = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_watt     = st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
_defizit  = st.floats(min_value=0.0, max_value=20000.0, allow_nan=False, allow_infinity=False)


@st.composite
def _battery_state(draw):
    """Zieht einen vollständigen, in sich plausiblen Speicher-Zustand."""
    soc_min = draw(st.floats(min_value=0.0, max_value=50.0, allow_nan=False))
    soc_max = draw(st.floats(min_value=soc_min, max_value=100.0, allow_nan=False))
    return dict(
        soc=draw(_soc),
        soc_min=soc_min,
        soc_max=soc_max,
        lade_limit=draw(_watt),
        entlade_limit=draw(_watt),
        min_lade=draw(st.sampled_from([0.0, 500.0])),
        min_entlade=draw(st.sampled_from([0.0, 500.0])),
        sollwert=draw(st.floats(min_value=-8000.0, max_value=8000.0, allow_nan=False)),
        totzone=draw(st.sampled_from([0.0, 100.0])),
        schritt=draw(st.sampled_from([50.0, 500.0, 100000.0])),
        betriebsart=draw(st.sampled_from(["auto", "nur_laden", "nur_entladen"])),
        laden=draw(st.sampled_from(["on", "off"])),
        entladen=draw(st.sampled_from(["on", "off"])),
    )


def _ready_battery(params, alloc_w=0.0, ziel_w=0.0):
    b = make_battery()
    b.begin_cycle(10_000.0)
    b.update_from_ha(battery_states(**params), 10_000.0, 0.0)
    b._alloc_w = alloc_w
    b.set_discharge_target(ziel_w)
    return b


@given(params=_battery_state(), alloc=_watt, ziel=_watt)
def test_p1_nie_gleichzeitig_laden_und_entladen(params, alloc, ziel):
    b = _ready_battery(params, alloc, ziel)
    b.calculate_ramp(0.0)
    assert b.new_lade_w == 0.0 or b.new_entlade_w == 0.0


@given(params=_battery_state(), alloc=_watt, ziel=_watt)
def test_p5_soc_grenzen_werden_nie_verletzt(params, alloc, ziel):
    b = _ready_battery(params, alloc, ziel)
    b.calculate_ramp(0.0)
    if b.soc_prozent >= b.soc_max_prozent:
        assert b.new_lade_w == 0.0
    if b.soc_prozent <= b.soc_min_prozent:
        assert b.new_entlade_w == 0.0


@given(params=_battery_state(), ziel=_watt)
def test_p6_entladung_steigt_nie_ueber_ziel_und_bisherigen_wert(params, ziel):
    b = _ready_battery(params, 0.0, ziel)
    vorher = b.entlade_anforderung_w
    zugeteilt = b.entlade_ziel_w
    b.calculate_ramp(0.0)
    assert b.new_entlade_w <= max(zugeteilt, vorher) + 1.0


@given(params=_battery_state(), ziel=_watt)
def test_p6b_ladung_steigt_nie_ueber_zuteilung_und_bisherigen_wert(params, ziel):
    b = _ready_battery(params, ziel, 0.0)
    vorher = b.lade_anforderung_w
    b.calculate_ramp(0.0)
    assert b.new_lade_w <= max(b.alloc_w, vorher, b.max_technisch_w) + 1.0


@given(params=st.lists(_battery_state(), min_size=1, max_size=4),
       hausdefizit=_defizit, abschlag=st.floats(min_value=0.0, max_value=500.0, allow_nan=False))
def test_p3_zuteilung_ueberschreitet_hausdefizit_nie(params, hausdefizit, abschlag):
    batteries = [_ready_battery(p) for p in params]
    ctrl = EMSController([], residual_power_entity="sensor.s")
    ctrl._allocate_discharge(batteries, hausdefizit, abschlag)
    assert sum(b.entlade_ziel_w for b in batteries) <= hausdefizit + TOL
    for b in batteries:
        assert b.entlade_ziel_w <= b.entlade_kapazitaet_w() + TOL


@given(params=_device_params(), battery=_battery_state(), pool=_pool)
def test_p4_zuteilung_ueberschreitet_pool_nie(params, battery, pool):
    """Der Speicher hängt in derselben 2-Pass-Allokation wie jeder Verbraucher."""
    devices = [_make(*params), _ready_battery(battery)]
    remaining = _allocate(devices, pool)
    assert remaining >= -TOL
    assert sum(d.alloc_w for d in devices) <= pool + 1e-4


@given(residual=st.floats(min_value=-20000.0, max_value=20000.0, allow_nan=False),
       heizstab_ist=_watt, sollwert=_watt)
def test_p7_ohne_speicher_identisch_zum_altverhalten(residual, heizstab_ist, sollwert):
    """Referenzimplementierung des alten _calc_pool gegen den neuen Zyklus."""
    ctrl = EMSController(
        [{"name": "heizstab", "class": "controllable",
          "actual_power_entity": "sensor.heizstab_ist", "allowed_modes": "auto", **CTRL_FALLBACKS}],
        residual_power_entity="sensor.s",
    )
    states = {
        "input_boolean.ems_pv_regelung_aktiv": "on",
        "input_select.ems_regelmodus": "auto",
        "input_number.ems_globaler_puffer_w": 0,
        "input_number.ems_einschaltreserve_global_w": 0,
        "input_boolean.ems_heizstab_freigabe": "on",
        "input_boolean.ems_heizstab_technische_freigabe": "on",
        "input_select.ems_heizstab_modus": "auto",
        "input_number.ems_heizstab_prioritat": 1,
        "input_number.ems_heizstab_min_technisch_w": 500,
        "input_number.ems_heizstab_max_technisch_w": 3000,
        "input_number.ems_heizstab_geschutzte_mindestleistung_w": 0,
        "input_number.ems_heizstab_reserve_w": 0,
        "input_number.ems_heizstab_hoch_regelzeit_s": 0,
        "input_number.ems_heizstab_runter_regelzeit_s": 0,
        "input_number.ems_heizstab_max_anderung_pro_schritt_w": 100000,
        "input_number.ems_heizstab_min_anderung_pro_schritt_w": 0,
        "input_number.ems_heizstab_anforderung_leistung_w": sollwert,
        "sensor.s": residual,
        "sensor.heizstab_ist": heizstab_ist,
    }
    status = ctrl.run_cycle(make_states(states))["status"]
    referenz = max(residual + min(heizstab_ist, sollwert), 0.0)
    assert status["pool_w"] == pytest.approx(referenz, abs=1e-4)
    assert status["netz_support_w"] == 0.0
    assert status["hausdefizit_w"] == 0.0 or status["pool_w"] == 0.0


@given(params=_battery_state(), power=_watt, switch=st.booleans())
def test_p2_gemessene_last_nie_kleiner_als_current(params, power, switch):
    """Die Ungleichung, die P2 trägt: entlade_basis_w >= pool_roh_w."""
    battery = _ready_battery(params)
    binary = BinaryDevice(id="hl", allowed_modes=["auto"],
                          entity_switch="switch.hl",
                          entity_anforderung_an="input_boolean.ems_hl_anforderung_an")
    binary.eligible = True
    binary.power_w = power
    binary._actual_on = switch
    binary._anforderung_an = switch
    controllable = _make(0.0, 10000.0, 0.0, 1)
    controllable._actual_w = power
    controllable._anforderung_current_w = power / 2

    for device in (battery, binary, controllable):
        assert device.gemessene_last_w >= device.current_w - TOL


@given(residual=st.floats(min_value=-20000.0, max_value=20000.0, allow_nan=False),
       hems_last=_watt, extra=_watt)
def test_p2_pool_und_hausdefizit_sind_komplementaer(residual, hems_last, extra):
    """Rein rechnerisch: solange gemessene_last >= current_w gilt, schliessen
    sich Pool und Hausdefizit gegenseitig aus."""
    hems_last_gemessen = hems_last + extra
    pool_roh      = residual + hems_last
    entlade_basis = residual + hems_last_gemessen
    pool          = max(pool_roh, 0.0)
    hausdefizit   = max(-entlade_basis, 0.0)
    assert entlade_basis >= pool_roh - TOL
    assert pool == 0.0 or hausdefizit == 0.0
