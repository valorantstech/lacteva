"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Plus, Store, Users } from "lucide-react";
import {
  type Customer,
  type CustomerPageResult,
  type Product,
  createCustomer,
  listCustomers,
  listCustomerTypes,
  listProducts,
  describeError,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
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

import { PageHeader } from "@/components/page-header";
import { RateChangeCard } from "@/components/rate-change";
import { PageContainer } from "@/components/page-container";
import { Metric, Surface } from "@/components/surface";
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

/** WO-107 §4: SUGGESTIONS. The type is the owner's own word; the filter
 *  lists the types actually in use (`/v1/customers/types`). */
const TYPE_SUGGESTIONS = ["household", "shop", "hotel", "institution", "distributor"] as const;
const OTHER_TYPE = "__other__";

/** "Rate per litre", "per kg", "per piece", "per packet" — the unit's word. */
export function unitWord(unit: string | null | undefined): string {
  switch ((unit ?? "").trim()) {
    case "L":
      return "litre";
    case "kg":
      return "kg";
    case "pc":
      return "piece";
    case "":
      return "unit";
    default:
      return unit!.trim();
  }
}

/** A product a standing order can be for: active, and not the catch-all. */
export const standingOrderProducts = (products: Product[]) =>
  products.filter((p) => p.active && p.code !== "OTHER");
const STATUSES = ["", "active", "inactive", "suspended"] as const;

const describe = (e: unknown) => describeError(e);

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
  const [typesInUse, setTypesInUse] = useState<string[]>([]);
  const [customerType, setCustomerType] = useState<string>(
    () => searchParams.get("type") ?? "",
  );
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  // WO-89 §5: the bulk rate change, previewed before anything moves.
  const [showRates, setShowRates] = useState(false);

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

  // WO-107 §4: the filter offers the types this organisation actually uses.
  useEffect(() => {
    let cancelled = false;
    listCustomerTypes()
      .then((types) => !cancelled && setTypesInUse(types))
      .catch(() => !cancelled && setTypesInUse([]));
    return () => {
      cancelled = true;
    };
  }, []);

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
    <PageContainer width="wide">
      <PageHeader
        title="Customers"
        description="The households and businesses this dairy delivers to — and what each of them owes."
        actions={
          // WO-96 / D-45: the row WRAPS. Three shrink-0 buttons in a row that
          // did not wrap made this page 376px wide on a 360px phone — and a
          // page wider than the phone makes mobile Chrome zoom the whole
          // thing out. This is the shop owner's most-used page.
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => (window.location.href = "/customers/import")}
            >
              Import CSV
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setShowRates((v) => !v)}
            >
              Change rate
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
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Customers"
            value={page ? page.total : "—"}
            caption={filtered ? "matching these filters" : "on the round"}
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
            label="Shown"
            value={page ? (page.items ?? []).length : "—"}
            caption={`page size ${PAGE_SIZE}`}
          />
          <span aria-hidden className="text-muted-foreground">
            <Store className="size-4" />
          </span>
        </Surface>
      </section>

      {showRates ? (
        <RateChangeCard
          onClose={() => setShowRates(false)}
          onApplied={() => void load()}
        />
      ) : null}

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
                  <Select
                    id="cu-type"
                    value={customerType}
                    onChange={(e) => {
                      setCustomerType(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">All types</option>
                    {typesInUse.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="cu-status">Status</Label>
                  <Select
                    id="cu-status"
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
                  </Select>
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
    </PageContainer>
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
  const [otherType, setOtherType] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [quantity, setQuantity] = useState("2.000");
  const [rate, setRate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // WO-107 §1: the standing order is for ONE OF THE ORGANISATION'S products.
  // This form hard-coded the demo seed's code, and the platform — rightly —
  // refused it in every organisation without that exact code, which was all
  // of them but the demo's. The labels follow the chosen product's unit and
  // the rate prefills from its price.
  const [products, setProducts] = useState<Product[] | null>(null);
  const [productCode, setProductCode] = useState("");
  useEffect(() => {
    let cancelled = false;
    listProducts(true)
      .then((page) => {
        if (cancelled) return;
        const usable = standingOrderProducts(page.items);
        setProducts(usable);
        if (usable[0]) {
          setProductCode(usable[0].code);
          if (usable[0].default_price != null && String(usable[0].default_price) !== "") {
            setRate(String(usable[0].default_price));
          }
        }
      })
      .catch(() => !cancelled && setProducts([]));
    return () => {
      cancelled = true;
    };
  }, []);
  function choose(code: string) {
    setProductCode(code);
    const chosen = products?.find((p) => p.code === code);
    if (chosen?.default_price != null && String(chosen.default_price) !== "") {
      setRate(String(chosen.default_price));
    }
  }
  const product = products?.find((p) => p.code === productCode) ?? null;
  const unit = product?.unit ?? "L";
  const customerType = type === OTHER_TYPE ? otherType.trim() : type;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!product) {
      setError(
        "choose the product this customer takes — add your milk products first if there are none",
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createCustomer({
        name,
        customer_type: customerType,
        phone,
        address,
        plan: {
          product: product.code,
          default_quantity: quantity,
          quantity_unit: product.unit,
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
              <Select
                id="nc-type"
                value={type}
                onChange={(e) => setType(e.target.value)}
              >
                {TYPE_SUGGESTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
                <option value={OTHER_TYPE}>Other…</option>
              </Select>
              {type === OTHER_TYPE ? (
                <Input
                  id="nc-type-other"
                  aria-label="Type (your own word)"
                  required
                  minLength={2}
                  maxLength={40}
                  placeholder="e.g. Temple"
                  value={otherType}
                  onChange={(e) => setOtherType(e.target.value)}
                />
              ) : null}
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
              <Label htmlFor="nc-product">Product</Label>
              {products && products.length === 0 ? (
                <p className="text-sm text-muted-foreground" data-testid="no-products">
                  Add your milk products first — nothing in the catalogue can be
                  a standing order yet.{" "}
                  <Link
                    href="/admin/products"
                    className="text-primary underline underline-offset-4"
                  >
                    Products
                  </Link>
                </p>
              ) : (
                <Select
                  id="nc-product"
                  required
                  value={productCode}
                  onChange={(e) => choose(e.target.value)}
                >
                  {(products ?? []).map((p) => (
                    <option key={p.code} value={p.code}>
                      {p.name} ({p.unit})
                    </option>
                  ))}
                </Select>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nc-qty">Daily quantity ({unit})</Label>
              <Input
                id="nc-qty"
                required
                inputMode="decimal"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nc-rate">Rate per {unitWord(unit)}</Label>
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
            <Button type="submit" disabled={busy || !product}>
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
