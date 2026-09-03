"""The milk day book as a file (WO-56 · BR-0030).

Same reasoning as the delivery export: what a dairy owner actually asks for is
not an API, it is *"give me today's day book"* — something to print, or to
hand to the person who reconciles the gate passes. CSV is what that person can
open.

The file states its own scope in its first lines, because a day book for one
centre and one for the whole organization look identical once the header row
is the only thing left, and somebody will forward it. And it carries the sales
figure with the reason it sits outside the ledger, rather than as a bare
number a reader would naturally subtract.
"""

from __future__ import annotations

import csv
import io

from platform_core.core.units import unit_label
from platform_core.modules.reporting.service import DayBook


#: Reading order: what came in, what went out, what that leaves. The
#: quantity headers name the book's OWN unit (D-21 / WO-70): a file that says
#: `collected_kg` over litres is the kind of thing somebody forwards.
def columns(book: DayBook) -> tuple[str, ...]:
    unit = unit_label(book.quantity_unit) or book.quantity_unit
    return (
        "milk_type",
        "collections",
        f"collected_{unit}",
        "dispatches",
        f"dispatched_{unit}",
        f"remainder_{unit}",
    )


#: The pre-WO-70 header, for anything that imported it by name.
COLUMNS = (
    "milk_type",
    "collections",
    "collected_kg",
    "dispatches",
    "dispatched_kg",
    "remainder_kg",
)


def filename(book: DayBook) -> str:
    scope = "all-centres" if book.center_id is None else str(book.center_id)[:8]
    return f"day-book-{book.business_date}-{scope}.csv"


def to_csv(book: DayBook) -> str:
    """One milk type per line, a totals row, then the day's sales as a note.

    The totals row is the platform's own aggregate rather than a sum of the
    lines above it — the same rule the delivery export follows, so the file
    cannot disagree with the screen.
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Milk day book"])
    writer.writerow(["business_date", str(book.business_date)])
    writer.writerow(["centre", book.center_name or "all centres"])
    writer.writerow(["quantity_unit", unit_label(book.quantity_unit) or book.quantity_unit])
    writer.writerow([])
    writer.writerow(columns(book))
    for row in book.rows:
        writer.writerow(
            [
                row.milk_type,
                row.collections,
                row.collected_kg,
                row.dispatches,
                row.dispatched_kg,
                row.remainder_kg,
            ]
        )
    writer.writerow(
        [
            "TOTAL",
            sum(r.collections for r in book.rows),
            book.total_collected_kg,
            sum(r.dispatches for r in book.rows),
            book.total_dispatched_kg,
            book.total_remainder_kg,
        ]
    )
    writer.writerow([])
    # Beside the ledger, never inside it, and the file says why in a sentence
    # a person can read — a lone "sold" number in a column of kilograms is
    # something a reader would subtract, and it is neither the same unit nor
    # the same scope.
    writer.writerow(["sold_today", book.sales.quantity, book.sales.quantity_unit])
    writer.writerow(["deliveries", book.sales.deliveries])
    # D-21 ruling 6: the refusal to subtract stands whatever the units. Where
    # the book is also in litres the file no longer claims a unit difference
    # it does not have — intake litres and delivered litres are still
    # different populations, and it says that instead.
    same_unit = unit_label(book.quantity_unit) == (book.sales.quantity_unit or "")
    why = (
        "They are a different population from intake — loss, retention and "
        "dispatch sit between the two even in the same unit."
        if same_unit
        else "They are measured in litres, while this ledger is in "
        f"{unit_label(book.quantity_unit) or book.quantity_unit}."
    )
    writer.writerow(
        [
            "note",
            "Sales are organization-wide and not attributed to a centre or a milk "
            f"type. {why} They are NOT subtracted from the remainder above.",
        ]
    )
    writer.writerow(
        [
            "note",
            "A flow ledger of recorded movements. It cannot see evaporation, "
            "spillage, testing samples or milk carried over from yesterday.",
        ]
    )
    return out.getvalue()
