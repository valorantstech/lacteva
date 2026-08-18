"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Plus, Store, Users } from "lucide-react";
import {
  ApiError,
  type Customer,
  type CustomerPageResult,
  createCustomer,
  listCustomers,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type Column, DataTable } from "@/components/data-table";

import { PageHeader, StatTile } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

/**
 * Customers (DEMO-009).
 *
 * The people and businesses this dairy SELLS to — not suppliers. The
 * distinction is the whole point of the module: a supplier is somebody the
 * organization receives milk from and owes money to; a customer is somebody it
 * delivers milk to and is owed money by.
 *
 * Every filter is a query parameter, and a customer cannot be created without
 * a rate being agreed — because a customer with no plan cannot receive a
 * delivery, and finding that out at the door is too late.
 */

const PAGE_SIZE = 15;

const TYPES = [
  "",
  "household",
  "shop",
  "hotel",
  "institution",
  "distributor",
] as const;
const STATUSES = ["", "active", "inactive", "suspended"] as const;

const describe = (e: unknown) => {
  if (e instanceof ApiError)
    return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Request failed";
};

/**
 * The page reads its filters from the URL on first load, so `/customers?q=Mama`
 * is a link somebody can send. It was not, and a deep link silently showed the
 * unfiltered list — which looks like a filter that does not work.
 */
export default function CustomersPage() {
  return (
    <Suspense fallback={<div className="p-8" />}>
      <CustomersView />
    </Suspense>
  );
}

function CustomersView() {
  const searchParams = useSearchParams();
  const [page, setPage] = useState<CustomerPageResult | null>(null);
  const [q, setQ] = useState(() => searchParams.get("q") ?? "");
  const [status, setStatus] = useState<(typeof STATUSES)[number]>(
    () => (searchParams.get("status") as (typeof STATUSES)[number]) ?? "",
  );
  const [customerType, setCustomerType] = useState<(typeof TYPES)[number]>(
    () => (searchParams.get("type") as (typeof TYPES)[number]) ?? "",
  );
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const filtered = Boolean(q || status || customerType);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPage(
        await listCustomers({
          q: q || undefined,
          status: status || undefined,
          customer_type: customerType || undefined,
          limit: PAGE_SIZE,
          offset,
        }),
      );
    } catch (err) {
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  }, [customerType, offset, q, status]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 150);
    return () => clearTimeout(t);
  }, [load]);

  const columns: Column<Customer>[] = [
    {
      key: "name",
      header: "Customer",
      cell: (c) => (
        <div className="flex flex-col">
          <Link
            className="font-medium hover:underline"
            href={`/customers/${c.id}`}
          >
            {c.name}
          </Link>
          <span className="text-xs text-muted-foreground">{c.code}</span>
        </div>
      ),
    },
    {
      key: "type",
      header: "Type",
      secondary: true,
      cell: (c) => c.customer_type,
    },
    {
      key: "contact",
      header: "Contact",
      secondary: true,
      cell: (c) => (
        <div className="flex flex-col">
          <span>{c.phone || "—"}</span>
          <span className="max-w-56 truncate text-xs text-muted-foreground">
            {c.address}
          </span>
        </div>
      ),
    },
    {
      key: "billing",
      header: "Billing",
      secondary: true,
      cell: (c) => (
        <span className="text-sm">
          {c.billing_mode}
          <span className="ms-1 text-xs text-muted-foreground">
            day {c.billing_day}
          </span>
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (c) => <StatusBadge status={c.status} />,
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "end",
      cell: (c) => (
        <Link
          href={`/customers/${c.id}`}
          className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
        >
          Open
        </Link>
      ),
    },
  ];

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Customers"
        description="The households and businesses this dairy delivers to — and what each of them owes."
        actions={
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => (window.location.href = "/customers/import")}>
              Import CSV
            </Button>
          <Button type="button" onClick={() => setShowCreate((v) => !v)}>
            <Plus aria-hidden className="me-1.5 size-4" />
            New customer
          </Button>
          </div>
        }
      />

      <section
        aria-label="Customer summary"
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
      >
        <StatTile
          label="Customers"
          value={page ? page.total : "—"}
          hint={filtered ? "matching these filters" : "on the round"}
          icon={<Users className="size-4" />}
        />
        <StatTile
          label="Shown"
          value={page ? (page.items ?? []).length : "—"}
          hint={`page size ${PAGE_SIZE}`}
          icon={<Store className="size-4" />}
        />
      </section>

      {showCreate ? (
        <CreateCustomerCard
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            setOffset(0);
            void load();
          }}
        />
      ) : null}

      <Card>
        <CardContent className="pt-6">
          <DataTable
            caption="Customers in this organization"
            columns={columns}
            rows={page?.items ?? []}
            rowKey={(c) => c.id}
            loading={loading}
            error={error}
            onRetry={() => void load()}
            empty={{
              title: filtered
                ? "No customer matches these filters"
                : "No customers yet",
              description: filtered
                ? "Try a different type or status, or clear the filters."
                : "Register the first household or shop on the delivery round.",
            }}
            toolbar={
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="cu-q">Search</Label>
                  <Input
                    id="cu-q"
                    className="h-9 w-56"
                    placeholder="Name, code or phone"
                    value={q}
                    onChange={(e) => {
                      setQ(e.target.value);
                      setOffset(0);
                    }}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="cu-type">Type</Label>
                  <select
                    id="cu-type"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={customerType}
                    onChange={(e) => {
                      setCustomerType(e.target.value as (typeof TYPES)[number]);
                      setOffset(0);
                    }}
                  >
                    {TYPES.map((t) => (
                      <option key={t || "all"} value={t}>
                        {t || "All types"}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="cu-status">Status</Label>
                  <select
                    id="cu-status"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={status}
                    onChange={(e) => {
                      setStatus(e.target.value as (typeof STATUSES)[number]);
                      setOffset(0);
                    }}
                  >
                    {STATUSES.map((s) => (
                      <option key={s || "all"} value={s}>
                        {s || "All statuses"}
                      </option>
                    ))}
                  </select>
                </div>
                {filtered ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setQ("");
                      setStatus("");
                      setCustomerType("");
                      setOffset(0);
                    }}
                  >
                    Clear filters
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
    </div>
  );
}

/**
 * Registering a customer.
 *
 * The rate is part of the form because a customer without a delivery plan
 * cannot receive a delivery — the platform refuses, and discovering that at
 * the door in the morning is too late to be useful.
 */
function CreateCustomerCard({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState("household");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [quantity, setQuantity] = useState("2.000");
  const [rate, setRate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createCustomer({
        name,
        customer_type: type,
        phone,
        address,
        plan: {
          product: "RAW-COW-MILK",
          default_quantity: quantity,
          quantity_unit: "L",
          unit_price: rate,
        },
      });
      onCreated();
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New customer</CardTitle>
        <CardDescription>
          The daily quantity and rate are the standing order. A delivery uses
          them unless the operator records something different.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nc-name">Name</Label>
              <Input
                id="nc-name"
                required
                minLength={2}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Mama Njeri Household"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nc-type">Type</Label>
              <select
                id="nc-type"
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={type}
                onChange={(e) => setType(e.target.value)}
              >
                {TYPES.filter(Boolean).map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nc-phone">Phone</Label>
              <Input
                id="nc-phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <Label htmlFor="nc-address">Address</Label>
              <Input
                id="nc-address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Where the round drops the milk"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nc-qty">Daily quantity (L)</Label>
              <Input
                id="nc-qty"
                required
                inputMode="decimal"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nc-rate">Rate per litre</Label>
              <Input
                id="nc-rate"
                required
                inputMode="decimal"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                placeholder="e.g. 60.00"
              />
              <p className="text-xs text-muted-foreground">
                The agreed selling price. Every delivery is priced from it by
                the platform.
              </p>
            </div>
          </div>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              The platform refused: {error}
            </p>
          ) : null}
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Registering…" : "Register customer"}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
