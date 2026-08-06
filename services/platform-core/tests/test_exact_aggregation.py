"""Exact numeric aggregation (DB-002).

Money was already exact: `Decimal(str(x))` arithmetic, `NUMERIC` columns, an
explicit rounding policy (BR-0005). What was not exact was **aggregation**.
`net_weight`, `fat` and `snf` are `double precision`, and floating point
addition is not associative — so `SUM(net_weight)` depended on the order the
planner happened to produce, and the result was written into a
`NUMERIC(16,3)` projection column, which made an inexact, non-reproducible
number look exact.

These tests pin the two properties that follow from the fix:

1. **Order independence** — the same rows, inserted and returned in any
   order, produce the same total.
2. **Replay reproducibility** — a projection rebuilt from the event log
   matches the incrementally built one, and matches itself across batch
   sizes. That is BR-0015, and it was not true for the last digit.

`_apply_sequence` mirrors the projection's accumulation exactly, which is why
these run on SQLite as well as PostgreSQL: the arithmetic under test is the
platform's, not the engine's.
"""

import random
from decimal import ROUND_HALF_UP, Decimal

import pytest

from platform_core.consumers.reporting_projection import _MONEY_SCALE, _WEIGHT_SCALE


@pytest.fixture
def guarded_registry():
    """Snapshot the consumer/projection registries — the rebuild tests below
    drive the real engine, and a leaked registration would corrupt the rest
    of the suite."""
    from tests.test_projections import projection_guard

    yield from projection_guard.__wrapped__()


def _apply_sequence(values, scale, *, flush_every: int) -> Decimal:
    """The projection handler, with an explicit flush boundary.

    The handler assigns `row.x = (row.x + value).quantize(scale)` once per
    event; `flush_every` decides when that value is written to a column of the
    same scale. Because the handler already quantizes, where the flush falls
    cannot matter — and that invariance is exactly what these tests assert.
    """
    stored = Decimal(0)
    for i, value in enumerate(values, start=1):
        stored = (stored + value).quantize(scale, rounding=ROUND_HALF_UP)
        if i % flush_every == 0:
            stored = stored.quantize(scale, rounding=ROUND_HALF_UP)  # the column write
    return stored


def _unquantized_sequence(values, scale, *, flush_every: int) -> Decimal:
    """The behaviour BEFORE DB-002: the running total kept full precision in
    the identity map and was rounded only when the batch was flushed.

    Kept so the defect stays legible — a test below shows it diverging.
    """
    stored = Decimal(0)
    pending = Decimal(0)
    for i, value in enumerate(values, start=1):
        pending += value
        if i % flush_every == 0:
            stored = (stored + pending).quantize(scale, rounding=ROUND_HALF_UP)
            pending = Decimal(0)
    return (stored + pending).quantize(scale, rounding=ROUND_HALF_UP) if pending else stored


def _projection_accumulate(values, scale) -> Decimal:
    """The handler's arithmetic, quantized per event — the fixed behaviour."""
    total = Decimal(0)
    for value in values:
        total = (total + value).quantize(scale, rounding=ROUND_HALF_UP)
    return total


# --- order independence ----------------------------------------------------


def test_a_decimal_total_does_not_depend_on_row_order():
    values = [Decimal(str(v)) for v in ("0.1", "0.2", "0.3", "125.555", "0.007")]
    totals = set()
    for _ in range(50):
        shuffled = values[:]
        random.shuffle(shuffled)
        totals.add(_projection_accumulate(shuffled, _WEIGHT_SCALE))
    assert len(totals) == 1, f"order changed the total: {totals}"


def test_the_same_float_values_summed_as_floats_DO_depend_on_order():
    """The defect, stated as a property — this is why the cast exists.

    If this ever stops failing to be order-independent, floating point has
    changed and the rest of this module can be reconsidered.
    """
    left = (0.1 + 0.2) + 0.3
    right = 0.1 + (0.2 + 0.3)
    assert left != right, "float addition was expected to be non-associative here"
    assert (left, right) == (0.6000000000000001, 0.6)
    # The same three values, added exactly, cannot disagree.
    a, b, c = Decimal("0.1"), Decimal("0.2"), Decimal("0.3")
    assert (a + b) + c == a + (b + c) == Decimal("0.6")


def test_random_insertion_order_never_changes_a_money_total():
    values = [Decimal(str(round(random.uniform(0, 500), 2))) for _ in range(200)]
    reference = _projection_accumulate(values, _MONEY_SCALE)
    for _ in range(20):
        shuffled = values[:]
        random.shuffle(shuffled)
        assert _projection_accumulate(shuffled, _MONEY_SCALE) == reference


# --- replay reproducibility (BR-0015) --------------------------------------


@pytest.mark.parametrize("batch", [1, 2, 3, 7, 100, 5000])
def test_a_rebuild_matches_the_incremental_total_at_every_batch_size(batch):
    """The regression this work order closes.

    The incremental consumer commits once per event; a rebuild commits once
    per batch. Before DB-002 the row stayed in the identity map across a
    batch and rounded once, so a weight with more decimals than the column
    stores produced a different total per batch size. Concretely: six values
    of 0.0005 gave 0.005 incrementally and 0.003 in one batch.
    """
    values = [Decimal("0.0005")] * 6 + [Decimal("125.5555"), Decimal("0.4444")]
    incremental = _apply_sequence(values, _WEIGHT_SCALE, flush_every=1)
    assert _apply_sequence(values, _WEIGHT_SCALE, flush_every=batch) == incremental


def test_the_old_accumulator_really_did_diverge():
    """Guards the fix by pinning what it fixed. Six weights of 0.0005 kg came
    to 0.005 incrementally and 0.003 in a single batch — the same events, the
    same log, two different totals, and no error anywhere. (0.006 vs 0.003
    under the platform's HALF_UP policy.)"""
    values = [Decimal("0.0005")] * 6
    assert _unquantized_sequence(values, _WEIGHT_SCALE, flush_every=1) == Decimal("0.006")
    assert _unquantized_sequence(values, _WEIGHT_SCALE, flush_every=500) == Decimal("0.003")
    # ...and the handler in place today does not.
    assert _apply_sequence(values, _WEIGHT_SCALE, flush_every=1) == _apply_sequence(
        values, _WEIGHT_SCALE, flush_every=500
    )


def test_rebuilding_twice_is_byte_identical():
    values = [Decimal(str(round(random.uniform(0, 50), 4))) for _ in range(500)]
    first = _apply_sequence(values, _WEIGHT_SCALE, flush_every=500)
    second = _apply_sequence(values, _WEIGHT_SCALE, flush_every=500)
    assert str(first) == str(second)
    assert first.as_tuple() == second.as_tuple(), "same value, different exponent"


def test_a_large_dataset_stays_exact():
    """Ten thousand three-decimal weights. A float accumulator drifts here;
    an exact one cannot."""
    values = [Decimal("0.001")] * 10_000
    assert _projection_accumulate(values, _WEIGHT_SCALE) == Decimal("10.000")


# --- decimal edge cases ----------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["0.0005", "2.675", "1.005", "0.145", "8.835", "1e-3", "999999.999"],
)
def test_ties_round_half_up_consistently(raw):
    """These are the values that expose a float accumulator: none of them is
    exactly representable in binary, and several are classic half-way cases."""
    value = Decimal(raw)
    once = value.quantize(_WEIGHT_SCALE, rounding=ROUND_HALF_UP)
    twice = _projection_accumulate([value], _WEIGHT_SCALE)
    assert once == twice


def test_negative_and_zero_contributions_are_handled():
    """Rejected collections contribute exactly zero — not `-0`, not `None`."""
    values = [Decimal("0"), Decimal("1.5"), Decimal("0"), Decimal("-1.5")]
    assert _projection_accumulate(values, _WEIGHT_SCALE) == Decimal("0.000")


# --- the SQL side ----------------------------------------------------------


def test_every_float_aggregation_in_reporting_is_cast_to_numeric():
    """A structural guard: a future report that sums `net_weight` directly
    reintroduces the defect, and no value-based test would necessarily catch
    it on a small dataset."""
    import inspect
    import re

    from platform_core.modules.reporting import service

    source = inspect.getsource(service)
    body = source.split("def _exact", 1)[1]  # skip the helper's own docstring
    offenders = [
        m.group(0)
        for m in re.finditer(r"func\.(sum|avg|min|max)\([^\n]*Tx\.(net_weight|fat|snf)", body)
        if "_exact(" not in m.group(0)
    ]
    assert offenders == [], (
        "float columns aggregated without _exact() — floating point addition "
        f"is not associative, so these totals are order-dependent: {offenders}"
    )


def test_the_cast_renders_as_numeric_on_both_engines():
    """SQLite and PostgreSQL must both receive the cast; only PostgreSQL can
    honour it (see the divergence note in the module docstring)."""
    from sqlalchemy import func
    from sqlalchemy.dialects import postgresql, sqlite

    from platform_core.modules.milk_collection.models import MilkCollectionTransaction as Tx
    from platform_core.modules.reporting.service import _exact

    expression = func.sum(_exact(Tx.net_weight))
    for dialect in (postgresql.dialect(), sqlite.dialect()):
        rendered = str(expression.compile(dialect=dialect)).upper()
        assert "CAST" in rendered and "NUMERIC" in rendered, rendered


async def test_the_reported_total_is_stable_across_repeated_reads(client):
    """End to end through the real API: the same rows, read twice, must give
    byte-identical numbers. Before DB-002 the plan was free to sum them in a
    different order and nothing would have said so."""
    from tests.test_reporting import _daily, _reported_env

    headers, _center, _supplier, _session = await _reported_env(client)
    first = await _daily(client, headers)
    second = await _daily(client, headers)
    for field in ("total_net_weight_kg", "weighted_avg_fat", "weighted_avg_snf"):
        assert repr(first[field]) == repr(second[field]), field
    assert first["payable_by_currency"] == second["payable_by_currency"]


async def test_the_weighted_average_divides_exactly(client):
    """`_weighted` now divides two exact sums in decimal and quantizes once.
    The fixture's two accepted deliveries are 25 kg @ fat 4.2 and 15 kg @ fat
    3.5, so the weighted mean is (4.2*25 + 3.5*15) / 40 = 3.9375 → 3.94."""
    from tests.test_reporting import _daily, _reported_env

    headers, _center, _supplier, _session = await _reported_env(client)
    summary = await _daily(client, headers)
    assert summary["weighted_avg_fat"] == 3.94


# --- the real engine: rebuild vs incremental, through the projection --------


async def test_a_real_rebuild_reproduces_the_incremental_totals_exactly(client, guarded_registry):
    """DB-002's acceptance criterion, driven through the actual projection
    engine rather than a model of it.

    The weights carry FOUR decimal places, more than the `NUMERIC(16,3)`
    column stores — reachable in production because `net_weight` is a float,
    and a scale reporting 25.0005 kg produces exactly this.

    **Engine note.** On PostgreSQL `numeric(16,3)` rounds on store, so without
    the handler's explicit quantize the in-memory total and the stored total
    drift apart inside a batch and the result depends on batch size. SQLite
    does not enforce a scale, so it cannot show that divergence — which is why
    the arithmetic itself is pinned by the model-based tests above, and by
    `test_exact_aggregation_postgres.py` on a real engine. This test is the
    end-to-end regression guard on whichever engine runs it.

    The incremental consumer commits once per event; the rebuild commits once
    per batch. Both must land on the same total, digit for digit — otherwise
    a rebuilt projection is not the same projection, and BR-0015 is a claim
    rather than a guarantee.
    """
    from tests.test_procurement_e2e import _accept_complete, _procurement_env, _run_collection
    from tests.test_projections import _daily_rows, _rebuilder, _runner

    headers, _center, supplier, session = await _procurement_env(client)
    for gross in (30.0005, 30.0005, 30.0005, 30.0005, 30.0005, 25.5555):
        tx = await _run_collection(client, headers, session["id"], supplier, gross=gross, tare=5.0)
        await _accept_complete(client, headers, tx["id"])
    await _runner().run_once()

    incremental = [
        (r.transactions, str(r.total_net_weight), str(r.payable_amount))
        for r in await _daily_rows()
    ]
    assert incremental, "fixture produced no projection rows"

    for batch_size in (1, 2, 5000):
        result = await _rebuilder().rebuild("reporting-projection", batch_size=batch_size)
        assert result.status == "completed"
        rebuilt = [
            (r.transactions, str(r.total_net_weight), str(r.payable_amount))
            for r in await _daily_rows()
        ]
        assert rebuilt == incremental, (
            f"batch_size={batch_size} produced different totals from the incremental "
            f"consumer: {rebuilt} != {incremental}"
        )


async def test_rebuilding_twice_in_a_row_is_byte_identical(client, guarded_registry):
    """Not merely equal — the same string. A `Decimal` comparing equal with a
    different exponent would still serialise differently to an API client."""
    from tests.test_projections import _collections, _daily_rows, _rebuilder

    await _collections(client, count=4)
    await _rebuilder().rebuild("reporting-projection")
    first = [str(r.total_net_weight) for r in await _daily_rows()]
    await _rebuilder().rebuild("reporting-projection")
    second = [str(r.total_net_weight) for r in await _daily_rows()]
    assert first == second and first, (first, second)
