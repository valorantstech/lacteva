"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CalendarClock, Phone, Users, Wallet } from "lucide-react";
import {
  ApiError,
  type ReceivableRow,
  type ReceivablesPage,
  getReceivables,
  describeError,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type Column, DataTable } from "@/components/data-table";
import { Money } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { PageContainer } from "@/components/page-container";
import { Metric, Surface } from "@/components/surface";

/**
 * Who owes money (DEMO-010).
 *
 * The collection round, in the order it should be walked. A dairy owner opens
 * this before anything else, so it exists as its own page rather than as a
 * filter buried in a customer list.
 *
 * Every figure is the platform's. `/v1/reports/receivables` joins invoices and
 * payments per customer inside the database and orders by the balance, so
 * this file does no arithmetic and no sorting — which matters more here than
 * anywhere else in the portal, because the headline is a TOTAL and the table
 * is a PAGE. Summing the visible rows would understate the debt of any dairy
 * with more households than fit on a screen, and look entirely plausible
 * while doing it.
 */

const PAGE_SIZE = 25;

const describe = (e: unknown) => {
  if (e instanceof ApiError)
    return describeError(e);
  return e instanceof Error ? e.message : "Could not load receivables";
};

const day = (iso: string | null) => (iso ? String(iso).slice(0, 10) : null);

export default function ReceivablesPage_() {
  // DEMO-013: the ORGANIZATION's currency, not a Kenyan default.
  const [page, setPage] = useState<ReceivablesPage | null>(null);
  const [q, setQ] = useState("");
  const [owingOnly, setOwingOnly] = useState(true);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPage(
        await getReceivables({
          q: q || undefined,
          owing_only: owingOnly ? "true" : "false",
          limit: String(PAGE_SIZE),
          offset: String(offset),
        }),
      );
    } catch (err) {
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  }, [offset, owingOnly, q]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 150);
    return () => clearTimeout(t);
  }, [load]);

  const columns: Column<ReceivableRow>[] = [
    {
      key: "customer",
      header: "Customer",
      cell: (row) => (
        <div className="flex flex-col">
          <Link
            className="font-medium hover:underline"
            href={`/customers/${row.customer_id}`}
          >
            {row.name}
          </Link>
          <span className="text-xs text-muted-foreground">
            {row.code}
            {row.phone ? ` · ${row.phone}` : ""}
          </span>
        </div>
      ),
    },
    {
      key: "billed",
      header: "Invoiced",
      align: "end",
      secondary: true,
      cell: (row) => <Money amount={row.invoiced} currency={row.currency} />,
    },
    {
      key: "paid",
      header: "Paid",
      align: "end",
      secondary: true,
      cell: (row) => <Money amount={row.paid} currency={row.currency} />,
    },
    {
      key: "outstanding",
      header: "Outstanding",
      align: "end",
      cell: (row) => (
        <div className="flex flex-col items-end">
          <Money amount={row.outstanding} currency={row.currency} emphasis />
          {row.open_invoices ? (
            <span className="text-xs text-muted-foreground">
              {row.open_invoices} open{" "}
              {row.open_invoices === 1 ? "bill" : "bills"}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "since",
      header: "Unpaid since",
      secondary: true,
      cell: (row) =>
        row.oldest_unpaid_from ? (
          <span className="tabular-nums text-sm">{row.oldest_unpaid_from}</span>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        ),
    },
    {
      key: "last",
      header: "Last payment",
      secondary: true,
      cell: (row) =>
        day(row.last_payment_at) ? (
          <span className="tabular-nums text-sm">
            {day(row.last_payment_at)}
          </span>
        ) : (
          <span className="text-sm text-muted-foreground">never paid</span>
        ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "end",
      cell: (row) => (
        <Link
          href={`/customers/${row.customer_id}`}
          className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
        >
          Record payment
        </Link>
      ),
    },
  ];

  return (
    <PageContainer width="wide">
      <PageHeader
        breadcrumbs={[
          { label: "Dashboard", href: "/" },
          { label: "Receivables" },
        ]}
        title="Who owes money"
        description="Every customer with an unpaid balance, largest first — the morning's collection round."
        actions={
          <Button
            type="button"
            variant="outline"
            disabled={loading}
            onClick={() => void load()}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </Button>
        }
      />

      <section
        aria-label="Receivables summary"
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
      >
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Total outstanding"
            value={
              page ? (
                <Money
                  amount={page.total_outstanding}
                  currency={page.currency}
                />
              ) : (
                "—"
              )
            }
            caption="across every customer matching this filter"
          />
          <span aria-hidden className="text-muted-foreground">
            <Wallet className="size-4" />
          </span>
        </Surface>
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label={owingOnly ? "Customers owing" : "Customers"}
            value={page ? page.total : "—"}
            caption={
              owingOnly
                ? "with a balance above zero"
                : "including settled accounts"
            }
          />
          <span aria-hidden className="text-muted-foreground">
            <Users className="size-4" />
          </span>
        </Surface>
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Oldest unpaid"
            value={
              page?.items?.length
                ? (page.items
                    .map((r) => r.oldest_unpaid_from)
                    .filter(Boolean)
                    .sort()[0] ?? "—")
                : "—"
            }
            caption="on this page"
          />
          <span aria-hidden className="text-muted-foreground">
            <CalendarClock className="size-4" />
          </span>
        </Surface>
      </section>

      <Card>
        <CardContent className="pt-6">
          <DataTable
            caption="Customers with an outstanding balance"
            columns={columns}
            rows={page?.items ?? []}
            rowKey={(row) => row.customer_id}
            loading={loading}
            error={error}
            onRetry={() => void load()}
            empty={{
              title: q
                ? "No customer matches that search"
                : owingOnly
                  ? "Every customer is settled"
                  : "No customers yet",
              description: q
                ? "Try a different name or customer code."
                : owingOnly
                  ? "Nobody has an outstanding balance right now."
                  : "Customers appear here once they are registered.",
            }}
            toolbar={
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="rc-q">Search</Label>
                  <Input
                    id="rc-q"
                    className="h-9 w-56"
                    placeholder="Customer name or code"
                    value={q}
                    onChange={(e) => {
                      setQ(e.target.value);
                      setOffset(0);
                    }}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="rc-scope">Show</Label>
                  <Select
                    id="rc-scope"
                    value={owingOnly ? "owing" : "all"}
                    onChange={(e) => {
                      setOwingOnly(e.target.value === "owing");
                      setOffset(0);
                    }}
                  >
                    <option value="owing">Only customers who owe</option>
                    <option value="all">Every customer</option>
                  </Select>
                </div>
                {q ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setQ("");
                      setOffset(0);
                    }}
                  >
                    Clear search
                  </Button>
                ) : null}
              </>
            }
            page={{
              offset,
              limit: PAGE_SIZE,
              total: page?.total ?? 0,
              onChange: setOffset,
              busy: loading,
            }}
          />
        </CardContent>
      </Card>

      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Phone aria-hidden className="size-4" />
        Open a customer to see their bills and record what they pay. A receipt
        is generated by the platform from the payment.
      </p>
    </PageContainer>
  );
}
