"""The daily delivery report as a file (DEMO-015 §15).

A dairy owner's actual request is not an API: it is *"give me today's milk
delivery report"* — something to print, or to send to an accountant who has
never heard of Lacteva. CSV is what that person can open, and it is the only
export format that needs no library and cannot go subtly wrong in a way the
platform would not notice.

Three decisions worth stating:

**The rows are built here, not in a browser.** Everything else about this
report is aggregated in SQL for the reasons §23 gives, and an export that
fetched pages and stitched them together in JavaScript would reintroduce
exactly the defect the rest of the design avoids — a total that depends on how
far the user scrolled.

**Money and quantity are written exactly as the platform stores them**, at the
currency's own scale and the column's own scale, with no thousands separators
and no symbol. A spreadsheet reads `1234.50` as a number and `₹1,234.50` as
text, and a report whose amounts are text is a report nobody can sum.

**A truncated export says so.** The last line of a capped file is a comment
naming what was dropped, because a file that silently stops at twenty thousand
rows looks exactly like a complete one — and this is the format people forward
without opening.
"""

from __future__ import annotations

import csv
import io

from platform_core.modules.delivery.service import DeliveryExport

#: Column order, which is also the reading order a dairy expects: who, when,
#: what, how much, at what rate, for how much.
COLUMNS = (
    "customer_code",
    "customer_name",
    "delivery_date",
    "slot",
    "product",
    "quantity",
    "unit",
    "unit_price",
    "amount",
    "currency",
    "status",
    "billed",
)


def to_csv(export: DeliveryExport) -> str:
    """One delivery per line, plus a header and a totals row.

    The totals row is the platform's own aggregate — the same figures
    `/v1/deliveries/report` returns — rather than a sum of the lines above it.
    They must agree, and a test asserts they do; computing it twice here would
    only mean the file could disagree with the screen.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in export.rows:
        writer.writerow(
            [
                row.customer_code,
                row.customer_name,
                row.delivery_date.isoformat(),
                row.slot,
                row.product,
                str(row.quantity),
                row.quantity_unit,
                str(row.unit_price),
                str(row.amount),
                row.currency,
                row.status,
                "yes" if row.billed else "no",
            ]
        )
    writer.writerow([])
    writer.writerow(
        [
            "TOTAL",
            f"{export.report.customers_served} customers",
            f"{export.report.date_from} — {export.report.date_to}",
            "",
            f"{export.report.deliveries} deliveries",
            str(export.report.total_quantity),
            export.report.quantity_unit,
            "",
            str(export.report.total_amount),
            export.report.currency,
            f"{export.report.skipped} skipped",
            "",
        ]
    )
    if export.truncated:
        writer.writerow([])
        writer.writerow(
            [
                f"# truncated: {len(export.rows)} of {export.matched} deliveries. "
                "Narrow the date range to export the rest."
            ]
        )
    return buffer.getvalue()


def filename(export: DeliveryExport) -> str:
    """`deliveries-2026-08-01.csv`, or `…-2026-08-01-to-2026-08-31.csv`.

    Named after what it contains, because these files land in a downloads
    folder next to a dozen others and `report.csv` is indistinguishable from
    `report (3).csv`.
    """
    if export.report.date_from == export.report.date_to:
        return f"deliveries-{export.report.date_from}.csv"
    return f"deliveries-{export.report.date_from}-to-{export.report.date_to}.csv"
