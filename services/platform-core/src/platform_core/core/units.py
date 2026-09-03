"""The intake unit — the dairy's, never the code's (D-21 · WO-70).

In India milk is sold, quoted and discussed in LITRES. The platform collected
in kilograms because a hardware specification mentioned a weighing scale, and
that inference — from what the INSTRUMENT reports to what the DAIRY trades in
— was wrong. It is recorded in D-21 because it is exactly the mistake this
module exists to stop the code repeating: a unit is a property of the
organisation, resolved from its country like its currency, and READ FROM THE
RECORD everywhere downstream. Nothing may assume one.

Weight stays supported. A scale is the harder instrument to defraud — foam,
temperature and a misread meniscus all move a volume reading, and water is
cheap — and some cooperatives weigh deliberately. So this is not "replace kg
with litres"; it is "stop hard-coding either".

**Conversion is a commercial term, never physics (ruling 3).** Real milk is
1.026-1.034 kg/L depending on fat, SNF and temperature; a settlement cannot
drift with the weather. Where a dairy measures in one unit and trades in the
other, the owner declares the factor, with an effective date; it is pinned
onto each transaction at capture so a later change never re-prices a settled
day; and it is printed on the receipt beside both figures. **A literal 1.03
anywhere in this codebase is a defect** — `test_units.py` greps for one.

**Density is a quality dimension, not a converter (ruling 4).** The analyzer's
density reading feeds pricing as quality. Converting quantity by it would
make a farmer's effective rate depend on composition twice — once in the
quality premium and once in the quantity — which no dairy contract does.
Nothing in this module reads density, and nothing may.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

#: The two units an organisation may measure or trade in. D-21 ruling 1.
UNITS: tuple[str, ...] = ("litre", "kg")

#: What a person reads. The stored value is the word; the screen shows the
#: symbol. Deliveries have always carried `L` (sales module) and that is the
#: same litre.
LABELS: dict[str, str] = {"litre": "L", "kg": "kg"}

#: Spellings a client, a CSV or a tired operator might send. The stored value
#: is always one of `UNITS`; this is the boundary that makes it so.
_SPELLINGS: dict[str, str] = {
    "litre": "litre",
    "litres": "litre",
    "liter": "litre",
    "liters": "litre",
    "l": "litre",
    "ltr": "litre",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
}

#: Sanity bounds for a declared kg-per-litre factor. Milk is about one and a
#: bit; these are wide enough for any honest commercial term and narrow
#: enough to catch a factor typed with the units the wrong way round (0.97)
#: or a percentage typed as a factor (103). NOT a physical constant — a bound.
FACTOR_MIN = Decimal("0.900")
FACTOR_MAX = Decimal("1.200")

#: Quantities keep three decimals, the scale's own precision (ruling 5).
QUANTITY_SCALE = Decimal("0.001")


class UnknownUnitError(ValueError):
    """A unit the platform does not measure milk in."""


def normalise_unit(value: str | None) -> str:
    """`'L'`, `'Litres'`, `'kg'` → the stored word. Anything else is refused."""
    key = (value or "").strip().lower()
    unit = _SPELLINGS.get(key)
    if unit is None:
        raise UnknownUnitError(f"unknown quantity unit {value!r} — one of {', '.join(UNITS)}")
    return unit


def unit_label(unit: str | None) -> str:
    """The symbol for a stored unit; an unknown one is shown as sent."""
    if not unit:
        return ""
    try:
        return LABELS[normalise_unit(unit)]
    except UnknownUnitError:
        return unit


@dataclass(frozen=True)
class ConversionTerms:
    """An organisation's declared relationship between what it measures and
    what it trades in — or the ordinary case, where they are the same and
    nothing converts.

    `factor` is KILOGRAMS PER LITRE, whichever direction the dairy converts
    in: a litre tenant paying by weight multiplies, a kg tenant paying by
    volume divides. One definition, so two dairies cannot mean two things by
    the same number.
    """

    measured_unit: str
    trade_unit: str | None = None
    factor: Decimal | None = None
    effective_from: date | None = None

    @property
    def converts(self) -> bool:
        return self.trade_unit is not None and self.trade_unit != self.measured_unit

    def in_force(self, on: date) -> bool:
        """Does the declared factor apply to a transaction on this date?"""
        if not self.converts or self.factor is None:
            return False
        return self.effective_from is None or self.effective_from <= on


def validate_terms(
    quantity_unit: str | None,
    trade_unit: str | None,
    factor: Decimal | None,
    effective_from: date | None,
) -> ConversionTerms:
    """The invariants, in one place, spoken in ValueError for the boundary
    to translate.

    - both units must be units;
    - a trade unit that differs from the measured one REQUIRES a factor and
      an effective date — otherwise it is a claim with no arithmetic behind
      it, and pricing would silently fall back to the measured quantity;
    - a factor with no differing trade unit is meaningless and refused, so
      a half-filled form cannot leave a dormant number behind;
    - the factor lies within commercial bounds.
    """
    measured = normalise_unit(quantity_unit)
    trade = normalise_unit(trade_unit) if trade_unit else None
    if trade == measured:
        trade = None
    if trade is not None:
        if factor is None:
            raise ValueError(
                f"trading in {trade} while measuring in {measured} needs a declared "
                "kg-per-litre conversion factor"
            )
        if effective_from is None:
            raise ValueError("a conversion factor needs the date it takes effect")
    if factor is not None:
        if trade is None:
            raise ValueError(
                "a conversion factor only applies when the trade unit differs from the "
                "measured unit"
            )
        if not (FACTOR_MIN <= factor <= FACTOR_MAX):
            raise ValueError(
                f"conversion factor {factor} is outside {FACTOR_MIN}-{FACTOR_MAX} kg per litre"
            )
    return ConversionTerms(
        measured_unit=measured,
        trade_unit=trade,
        factor=factor if trade is not None else None,
        effective_from=effective_from if trade is not None else None,
    )


def trade_quantity(net: float, *, measured_unit: str, trade_unit: str, factor: Decimal) -> float:
    """The paid quantity from the measured one, by the DECLARED factor.

    Decimal all the way and rounded once, half-up, to the scale's own three
    places — the number on the receipt must be reproducible from the two
    beside it by anyone with a calculator.
    """
    measured = normalise_unit(measured_unit)
    trade = normalise_unit(trade_unit)
    if measured == trade:
        return net
    amount = Decimal(str(net))
    if measured == "litre" and trade == "kg":
        converted = amount * factor
    elif measured == "kg" and trade == "litre":
        converted = amount / factor
    else:  # pragma: no cover — UNITS has two members
        raise UnknownUnitError(f"cannot convert {measured} to {trade}")
    return float(converted.quantize(QUANTITY_SCALE, rounding=ROUND_HALF_UP))
