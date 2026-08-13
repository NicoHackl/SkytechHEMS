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

from ems.devices import ControllableDevice

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
