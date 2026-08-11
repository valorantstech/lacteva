"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Building2, Tags } from "lucide-react";
import {
  ApiError,
  type MatrixDetail,
  type PricingMatrix,
  type RateCardDetail,
  getMatrixDetail,
  getRateCardDetail,
  listMatrices,
} from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState, TableSkeleton } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

/**
 * One rate card, and the bands that price milk against it (DEMO-004).
 *
 * The list page already handles the lifecycle (draft → submitted → approved →
 * published) and its actions. What was missing was the thing a customer
 * actually asks to see: the BANDS. A rate card without its bands visible is a
 * name and a date; with them it is the rule that decided every amount in the
 * product.
 *
 * Prices are rendered exactly as the platform stores them — `Numeric(12,4)`,
 * so `45.0000` keeps its four decimals rather than becoming `45`.
 */

type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

const LOADING = { state: "loading" } as const;
const describe = (e: unknown) =>
  e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "the request failed";

export default function RateCardDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [detail, setDetail] = useState<Load<RateCardDetail>>(LOADING);
  const [matrices, setMatrices] = useState<Load<PricingMatrix[]>>(LOADING);
  const [bands, setBands] = useState<Record<string, MatrixDetail>>({});

  const load = useCallback(async () => {
    const ok =
      <T,>(set: (v: Load<T>) => void) =>
      (data: T) =>
        set({ state: "ready", data });
    const fail =
      <T,>(set: (v: Load<T>) => void) =>
      (e: unknown) =>
        set({ state: "error", message: describe(e) });

    await Promise.allSettled([
      getRateCardDetail(id).then(ok(setDetail), fail(setDetail)),
      listMatrices({ rate_card_id: id, limit: 20, offset: 0 })
        .then(async (page) => {
          const items = page.items ?? [];
          setMatrices({ state: "ready", data: items });
          // One detail request per matrix. A card carries a handful, not a
          // table's worth, so this is bounded by the domain rather than by data.
          const loaded = await Promise.allSettled(items.map((m) => getMatrixDetail(m.id)));
          setBands(
            Object.fromEntries(
              loaded.flatMap((r, i) =>
                r.status === "fulfilled" ? [[items[i].id, r.value] as const] : [],
              ),
            ),
          );
        })
        .catch(fail(setMatrices)),
    ]);
  }, [id]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  if (detail.state === "error") {
    return (
      <div className="mx-auto w-full max-w-3xl p-8">
        <ErrorState message={`This rate card could not be loaded — ${detail.message}.`} />
        <p className="mt-4 text-sm">
          <Link className="underline underline-offset-4" href="/rate-cards">
            Back to rate cards
          </Link>
        </p>
      </div>
    );
  }

  // Narrow once: TypeScript cannot follow `card !== null` back to `detail`.
  const ready = detail.state === "ready" ? detail.data : null;
  const card = ready?.card ?? null;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        breadcrumbs={[{ label: "Rate cards", href: "/rate-cards" }, { label: card?.code ?? "Card" }]}
        title={card?.name ?? "Rate card"}
        description={
          card
            ? `${card.code} · version ${card.version} · ${card.currency}`
            : "Loading this rate card…"
        }
        actions={card ? <StatusBadge status={card.status} /> : undefined}
      />

      {detail.state === "loading" ? <LoadingState label="Loading the rate card…" /> : null}

      {card && ready ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Tags aria-hidden className="size-4 text-muted-foreground" />
                Card
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-2.5 text-sm">
                <Row label="Status">
                  <StatusBadge status={card.status} />
                </Row>
                <Row label="Effective from">{card.effective_from}</Row>
                <Row label="Effective until">
                  {card.effective_until ?? (
                    <span className="text-muted-foreground">open-ended</span>
                  )}
                </Row>
                <Row label="Currency">{card.currency}</Row>
                <Row label="Version">{card.version}</Row>
                {card.published_at ? <Row label="Published">{String(card.published_at).slice(0, 10)}</Row> : null}
              </dl>
              {/* The lifecycle is the platform's, and its actions live on the
                  list page. Showing them twice would be two places to keep
                  correct — and only one of them would be tested. */}
              <p className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">
                Lifecycle: draft → submitted → approved → published. Actions are on the rate cards
                list; the platform decides which are available.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Building2 aria-hidden className="size-4 text-muted-foreground" />
                Scope
              </CardTitle>
              <CardDescription>Where and to what this card applies.</CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-3 text-sm">
                <div>
                  <dt className="mb-1 text-muted-foreground">Products</dt>
                  <dd className="flex flex-wrap gap-1.5">
                    {(ready.products ?? []).length === 0 ? (
                      <span className="text-muted-foreground">none</span>
                    ) : (
                      (ready.products ?? []).map((p) => (
                        <span
                          key={p.product_code}
                          className="rounded border border-border px-1.5 py-0.5 font-mono text-xs"
                        >
                          {p.product_code}
                        </span>
                      ))
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="mb-1 text-muted-foreground">Collection centres</dt>
                  <dd className="flex flex-col gap-1">
                    {(ready.center_ids ?? []).length === 0 ? (
                      <span className="text-muted-foreground">all centres</span>
                    ) : (
                      (ready.center_ids ?? []).map((cid) => (
                        <Link
                          key={cid}
                          href={`/centers/${cid}`}
                          className="text-xs underline-offset-4 hover:underline"
                        >
                          {cid.slice(0, 8)}…
                        </Link>
                      ))
                    )}
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle className="text-base">How a price is chosen</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              <p>
                A collection&apos;s quality reading is matched against the bands below. The band it
                falls into gives the unit price, and the platform multiplies that by the net
                weight.
              </p>
              <p className="mt-2">
                Bands are half-open — a reading equal to a band&apos;s upper bound belongs to the
                next band, so no reading can match two prices.
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Rate bands</CardTitle>
          <CardDescription>The prices this card resolves to.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {matrices.state === "loading" ? (
            <TableSkeleton rows={4} columns={3} />
          ) : matrices.state === "error" ? (
            <ErrorState message={`Bands are unavailable — ${matrices.message}.`} />
          ) : matrices.data.length === 0 ? (
            <EmptyState
              title="No pricing matrix on this card"
              description="A card prices nothing until it carries a matrix with at least one band."
            />
          ) : (
            matrices.data.map((matrix) => {
              const loaded = bands[matrix.id];
              return (
                <div key={matrix.id} className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-sm font-medium">{matrix.name}</h3>
                    <span className="text-xs text-muted-foreground">
                      {matrix.dimension_code} · {matrix.product_code}
                    </span>
                  </div>
                  {!loaded ? (
                    <TableSkeleton rows={3} columns={2} />
                  ) : (loaded.rows ?? []).length === 0 ? (
                    <p className="text-sm text-muted-foreground">No bands defined.</p>
                  ) : (
                    <div className="w-full overflow-x-auto">
                      <table className="w-full text-sm">
                        <caption className="sr-only">
                          Rate bands for {matrix.name}
                        </caption>
                        <thead>
                          <tr className="border-b border-border text-left text-muted-foreground">
                            <th scope="col" className="py-2 font-medium">
                              Band ({loaded.dimension?.unit ?? matrix.dimension_code})
                            </th>
                            <th scope="col" className="py-2 text-right font-medium">
                              Rate
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {(loaded.rows ?? []).map((row) => (
                            <tr key={row.id} className="border-b border-border/60 last:border-0">
                              <td className="py-2 tabular-nums">
                                {row.from_value} – {row.to_value}
                              </td>
                              <td className="py-2 text-right tabular-nums font-medium">
                                {String(row.unit_price)}
                                <span className="ml-1 text-xs font-normal text-muted-foreground">
                                  {card?.currency}/kg
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {(loaded.gaps ?? []).length > 0 ? (
                        <p role="note" className="mt-2 text-xs text-destructive">
                          {loaded.gaps.length} gap(s) in coverage — a reading falling in a gap
                          cannot be priced.
                        </p>
                      ) : null}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}
