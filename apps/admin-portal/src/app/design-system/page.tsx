"use client";

/**
 * The Lacteva Design System showroom (internal reference).
 *
 * A working page rather than a picture of one: every swatch is the live token,
 * every component is the shipping component, every timing is the real timing.
 * A design reference that can drift from the product is worse than none.
 *
 * It is a REFERENCE, not a product surface. It reads no API and writes
 * nothing. Every number below is a literal placed here for demonstration —
 * none of it is dairy data, and nothing here implies a capability exists.
 */

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState } from "@/components/states";
import { ComingSoonInsight, Insight } from "@/components/insight";
import { LiquidProgress } from "@/components/liquid-progress";
import {
  CollectionProgress,
  MilkFill,
  MilkRipple,
  MilkStream,
  MilkVolume,
} from "@/components/milk";
import { Skeleton, SkeletonRows } from "@/components/skeleton";
import { StatusBadge } from "@/components/status-badge";
import { Metric, Surface } from "@/components/surface";
import { SyncIndicator, type SyncState } from "@/components/sync-indicator";
import { TrendChart, BarBreakdown, type TrendDatum } from "@/components/trend-chart";

/* — Demonstration values. Literals, on purpose: see the file note. — */
const DEMO_TREND: TrendDatum[] = [
  { day: "2026-08-19", quantity: 742, value: "31164.00", currency: "INR", transactions: 61 },
  { day: "2026-08-20", quantity: 768, value: "32256.00", currency: "INR", transactions: 64 },
  { day: "2026-08-21", quantity: 731, value: "30702.00", currency: "INR", transactions: 60 },
  { day: "2026-08-22", quantity: 806, value: "33852.00", currency: "INR", transactions: 67 },
  { day: "2026-08-23", quantity: 795, value: "33390.00", currency: "INR", transactions: 66 },
  { day: "2026-08-24", quantity: 838, value: "35196.00", currency: "INR", transactions: 69 },
  { day: "2026-08-25", quantity: 820, value: "34440.00", currency: "INR", transactions: 68 },
];

const DEMO_CENTRES = [
  { key: "a", label: "Centre A", detail: "68 collections", magnitude: 820 },
  { key: "b", label: "Centre B", detail: "54 collections", magnitude: 640 },
  { key: "c", label: "Centre C", detail: "41 collections", magnitude: 470 },
  { key: "d", label: "Centre D", detail: "22 collections", magnitude: 260 },
];

function Section({
  title,
  note,
  children,
}: {
  title: string;
  note: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-section font-semibold tracking-tight">{title}</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">{note}</p>
      </div>
      {children}
    </section>
  );
}

function Swatch({ name, className }: { name: string; className: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className={`h-16 rounded-lg shadow-[var(--elevation-1)] ${className}`} />
      <code className="text-meta text-muted-foreground">{name}</code>
    </div>
  );
}

export default function DesignSystemPage() {
  const [sync, setSync] = useState<SyncState>("syncing");
  const [collected, setCollected] = useState(820);
  const [done, setDone] = useState(false);
  const [width, setWidth] = useState<"desktop" | "tablet" | "mobile">("desktop");

  const frame = { desktop: "100%", tablet: "768px", mobile: "390px" }[width];

  return (
    <div className="flex flex-col gap-12 p-6">
      {/* ── HERO ── */}
      <Surface tone="hero" className="relative overflow-hidden p-8 sm:p-10">
        {/*
         * Depth on the right, in the product's own language: a collection
         * signal — centres connected to a line, one of them carrying a
         * quality signal — over a soft milk form. Drawn, not photographed;
         * low contrast, so it is atmosphere rather than an illustration
         * competing with the headline.
         */}
        <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 end-0 hidden w-1/2 lg:block">
          <div className="absolute -end-16 top-1/2 size-72 -translate-y-1/2 rounded-full bg-milk/10 blur-3xl" />
          <svg viewBox="0 0 320 240" className="absolute inset-0 size-full opacity-[0.5]">
            {/* the collection line */}
            <path
              d="M20 190 C 90 190, 110 120, 175 120 S 260 60, 300 60"
              fill="none"
              stroke="var(--milk)"
              strokeOpacity="0.28"
              strokeWidth="1.5"
            />
            {/* centres reporting into it */}
            {[
              [20, 190, 3],
              [110, 155, 2.5],
              [175, 120, 4],
              [250, 84, 2.5],
              [300, 60, 3],
            ].map(([cx, cy, r], i) => (
              <circle key={i} cx={cx} cy={cy} r={r} fill="var(--milk)" fillOpacity={0.55} />
            ))}
            {/* one signal, breathing — the single computed thing this product does */}
            <circle cx="175" cy="120" r="11" fill="none" stroke="var(--milk)" strokeOpacity="0.35" strokeWidth="1" className="lacteva-attend" />
            {/* the vessel, implied */}
            <path d="M244 150 h44 v54 a8 8 0 0 1 -8 8 h-28 a8 8 0 0 1 -8 -8 z" fill="var(--milk)" fillOpacity="0.10" />
            <path d="M244 176 q 11 -6, 22 0 t 22 0 v28 a8 8 0 0 1 -8 8 h-28 a8 8 0 0 1 -8 -8 z" fill="var(--milk)" fillOpacity="0.22" />
          </svg>
        </div>

        <div className="relative flex flex-col gap-8 lg:max-w-[58%]">
          <div className="flex flex-col gap-3">
            <span className="text-meta font-semibold uppercase tracking-[0.2em] text-primary-foreground/70">
              Lacteva Design System
            </span>
            <h1 className="text-display font-semibold tracking-tight">
              A dairy intelligence platform, not a dashboard
            </h1>
            <p className="max-w-xl text-primary-foreground/80">
              Milk over cream, deep dairy green, motion built on how liquid settles.
              Everything here is live.
            </p>
          </div>

          <div className="grid gap-6 sm:grid-cols-3">
            <Metric onBrand label="Collected today" value="4,206" unit="L" delta={{ direction: "up", text: "3.1% vs yesterday" }} />
            <Metric onBrand label="Centres reporting" value="7 / 8" caption="One shift not yet opened" />
            <Metric onBrand label="Average fat" value="3.94" unit="%" delta={{ direction: "flat", text: "steady this week" }} />
          </div>
        </div>
      </Surface>

      {/* ── CORE ── */}
      <Section
        title="Core product primitives"
        note="Constrain the frame: mobile is not desktop shrunk."
      >
        <div className="flex flex-wrap gap-2">
          {(["desktop", "tablet", "mobile"] as const).map((w) => (
            <Button key={w} variant={width === w ? "default" : "outline"} onClick={() => setWidth(w)}>
              {w === "mobile" ? "Mobile 390px" : w === "tablet" ? "Tablet 768px" : "Desktop"}
            </Button>
          ))}
        </div>
        <div className="overflow-hidden rounded-xl border border-border bg-background p-4">
          <div style={{ maxWidth: frame, transition: "max-width var(--motion-base) var(--ease-out-liquid)" }}>
            <Surface tone="operational" className="flex flex-col gap-5">
              <CollectionProgress
                collected={collected}
                target={1000}
                title="Centre A — morning shift"
                caption={done ? "Target reached" : "Target 1,000 L"}
                paused={sync === "offline"}
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <Metric label="Farmers served" value="68" delta={{ direction: "up", text: "4 more than yesterday" }} />
                <Metric label="Rejected" value="1" caption="Reason recorded by the operator" />
              </div>
            </Surface>
          </div>
        </div>
      </Section>

      {/* ── MILK ── */}
      <Section
        title="The milk language"
        note="A vessel filling, a surface that moves. The number is always rendered."
      >
        <div className="grid gap-4 lg:grid-cols-3">
          <Surface tone="metric" className="flex flex-col gap-4">
            <MilkVolume value={collected} max={1000} label="Collected" caption="Centre A, this shift" />
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => { setCollected((v) => Math.max(0, v - 120)); setDone(false); }}>
                −120 L
              </Button>
              <Button variant="outline" onClick={() => { setCollected((v) => Math.min(1000, v + 120)); }}>
                +120 L
              </Button>
              <Button onClick={() => { setCollected(1000); setDone(true); }}>Fill</Button>
            </div>
          </Surface>

          <Surface tone="metric" className="flex flex-col justify-between gap-4">
            <div className="flex flex-col gap-1">
              <span className="text-meta uppercase tracking-wide text-muted-foreground">Flow</span>
              <span className="text-sm text-muted-foreground">
                A stream moves only while something is happening. Idle is still.
              </span>
            </div>
            <div className="flex items-end gap-4">
              <MilkFill value={82} max={100} label="Vessel, 82%" tone="dairy" className="h-24 w-12" />
              <MilkFill value={38} max={100} label="Vessel, 38%" tone="fresh" className="h-24 w-12" />
              <MilkFill value={64} max={100} label="Vessel, paused" tone="water" still className="h-24 w-12" />
            </div>
            <div className="flex flex-col gap-3">
              <MilkStream label="Route 1, in progress" active />
              <MilkStream label="Route 2, idle" active={false} tone="fresh" />
            </div>
          </Surface>

          <Surface tone="metric" className="flex flex-col items-start justify-between gap-4">
            <div className="flex flex-col gap-1">
              <span className="text-meta uppercase tracking-wide text-muted-foreground">Completion</span>
              <span className="text-sm text-muted-foreground">
                Fires once, on arrival, then stops. A success that keeps animating is one nobody believes.
              </span>
            </div>
            {done ? (
              <MilkRipple>
                <span className="rounded-full bg-success px-3 py-1 text-sm font-medium text-success-foreground">
                  Shift complete
                </span>
              </MilkRipple>
            ) : (
              <span className="text-meta text-muted-foreground">Press “Fill” to see the completion beat.</span>
            )}
          </Surface>
        </div>
      </Section>

      {/* ── SYNC ── */}
      <Section
        title="Sync"
        note="The word and the count are the signal; droplets move only when work does."
      >
        <div className="flex flex-wrap items-center gap-3">
          <SyncIndicator state="online" />
          <SyncIndicator state="offline" pending={3} />
          <SyncIndicator state="syncing" pending={3} />
          <SyncIndicator state="error" pending={1} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {(["online", "offline", "syncing", "error"] as const).map((s) => (
            <Button key={s} variant={sync === s ? "default" : "outline"} onClick={() => setSync(s)}>
              {s}
            </Button>
          ))}
          <SyncIndicator state={sync} pending={sync === "online" ? 0 : 2} />
        </div>
      </Section>

      {/* ── INTELLIGENCE ── */}
      <Section
        title="Intelligence"
        note="Indigo, used nowhere else. Evidence is the second line, never hidden."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <Insight
            title="Fat reading is unusual for this farmer"
            basis="4.8% against a 30-day average of 3.9% for the same farmer"
            confidence="moderate"
            reasoning="The platform compares each reading against that farmer's own trailing 30-day average and flags a deviation beyond the configured band. It is a statistical comparison over past readings — it does not diagnose a cause, and it does not act on its own."
          />
          <div className="flex flex-col gap-4">
            <ComingSoonInsight
              title="Deeper quality analysis"
              note="Listed and labelled on the roadmap page. Not built."
            />
            <Surface tone="warning" className="flex flex-col gap-1">
              <span className="text-meta font-semibold uppercase tracking-wider text-warning">
                Attention
              </span>
              <span className="text-sm">Centre D has not opened a shift today.</span>
              <span className="text-meta text-muted-foreground">
                Amber is attention, never alarm — and it carries ink, not milk, for contrast.
              </span>
            </Surface>
          </div>
        </div>
      </Section>

      {/* ── DATA ── */}
      <Section
        title="Data visualisation"
        note="Hues distinguishable by hue, not lightness."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <Surface tone="metric" className="flex flex-col gap-4">
            <div className="flex flex-col gap-0.5">
              <span className="text-section font-semibold tracking-tight">Collection trend</span>
              <span className="text-meta text-muted-foreground">Seven days, litres collected</span>
            </div>
            <TrendChart data={DEMO_TREND} metric="quantity" />
          </Surface>
          <Surface tone="metric" className="flex flex-col gap-4">
            <div className="flex flex-col gap-0.5">
              <span className="text-section font-semibold tracking-tight">Centre performance</span>
              <span className="text-meta text-muted-foreground">Litres collected, this shift</span>
            </div>
            <BarBreakdown rows={DEMO_CENTRES} />
          </Surface>
        </div>
      </Section>

      {/* ── SURFACES ── */}
      <Section
        title="Surfaces"
        note="Hierarchy from elevation, not a border on everything. Hover the lifting card."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Surface tone="quiet"><span className="text-sm">Quiet — reference material</span></Surface>
          <Surface tone="metric" lift><span className="text-sm">Metric — lifts on hover</span></Surface>
          <Surface tone="operational"><span className="text-sm">Operational — work in progress</span></Surface>
          <Surface tone="insight"><span className="text-sm">Insight — the intelligence surface</span></Surface>
          <Surface tone="warning"><span className="text-sm">Warning — attention, not alarm</span></Surface>
          <Surface tone="live"><span className="text-sm">Live — happening right now</span></Surface>
        </div>
      </Section>

      {/* ── CONTROLS ── */}
      <Section title="Controls" note="Press Tab: the focus ring is a deliverable, not a browser leftover.">
        <div className="flex flex-wrap items-center gap-2">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Button disabled>Disabled</Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge>Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <Badge variant="outline">Outline</Badge>
          <StatusBadge status="ACTIVE" />
          <StatusBadge status="QUALITY_PENDING" />
          <StatusBadge status="REJECTED" />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <div className="max-w-sm flex-1"><Input placeholder="Input" aria-label="Demonstration input" /></div>
          <LiquidProgress value={62} label="Demonstration progress" />
        </div>
      </Section>

      {/* ── STATES ── */}
      <Section title="States" note="Loading shows the shape of what is coming. Empty says what to do next. Errors are announced and recoverable.">
        <div className="grid gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Loading</CardTitle>
              <CardDescription>Skeleton, not a spinner</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Skeleton className="h-6 w-2/3" />
              <SkeletonRows rows={3} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Empty</CardTitle>
              <CardDescription>Guidance, not just “no data”</CardDescription>
            </CardHeader>
            <CardContent>
              <EmptyState
                title="No collections yet"
                description="Collections appear here once an operator records one at a centre."
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Error</CardTitle>
              <CardDescription>Announced, and recoverable</CardDescription>
            </CardHeader>
            <CardContent>
              <ErrorState
                message="Could not reach the platform."
                action={<Button variant="outline">Try again</Button>}
              />
            </CardContent>
          </Card>
        </div>
      </Section>

      {/* ── FOUNDATIONS ── */}
      <Section
        title="Foundations"
        note="Milk cards on a cream page."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          <Swatch name="--background (cream)" className="bg-background" />
          <Swatch name="--card (milk)" className="bg-card" />
          <Swatch name="--primary (dairy)" className="bg-primary" />
          <Swatch name="--fresh" className="bg-fresh" />
          <Swatch name="--water" className="bg-water" />
          <Swatch name="--amber" className="bg-amber" />
          <Swatch name="--success" className="bg-success" />
          <Swatch name="--warning" className="bg-warning" />
          <Swatch name="--destructive" className="bg-destructive" />
          <Swatch name="--info" className="bg-info" />
          <Swatch name="--intelligence" className="bg-intelligence" />
          <Swatch name="--ink" className="bg-ink" />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="h-16 rounded-lg bg-[image:var(--gradient-milk)] shadow-[var(--elevation-1)]" />
          <div className="h-16 rounded-lg bg-[image:var(--gradient-cream-fresh)] shadow-[var(--elevation-1)]" />
          <div className="h-16 rounded-lg bg-[image:var(--gradient-dairy)] shadow-[var(--elevation-1)]" />
        </div>
      </Section>

      {/* ── TYPE ── */}
      <Section title="Typography" note="A clamp() scale, so this is responsive rather than a desktop scale that shrinks badly.">
        <Surface tone="quiet" className="flex flex-col gap-3">
          <span className="text-display font-semibold tracking-tight">Display</span>
          <span className="text-page font-semibold tracking-tight">Page heading</span>
          <span className="text-section font-semibold tracking-tight">Section heading</span>
          <span className="text-base">Body — the size most of the product is read at.</span>
          <span className="text-meta text-muted-foreground">Metadata — captions, units, timestamps.</span>
        </Surface>
      </Section>

      {/* ── DIRECTION ── */}
      <Section
        title="Direction"
        note="Built on logical properties: RTL is a direction change, not a redesign."
      >
        <div dir="rtl">
          <Surface tone="metric" className="flex flex-wrap items-center gap-3">
            <SyncIndicator state="offline" pending={2} />
            <Button>إجراء</Button>
            <Badge variant="secondary">حالة</Badge>
            <MilkStream label="تدفق" active />
          </Surface>
        </div>
      </Section>
      {/* ── ACCESSIBILITY ── */}
      <Section
        title="Accessibility & motion"
        note="Contrast, focus and reduced motion are asserted by test, not asserted by prose."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Surface tone="quiet" className="flex flex-col gap-1">
            <span className="text-section font-semibold tracking-tight">AA+</span>
            <span className="text-meta text-muted-foreground">
              12 token pairs, both faces, computed from OKLCH. Body text ≥ 7:1.
            </span>
          </Surface>
          <Surface tone="quiet" className="flex flex-col gap-1">
            <span className="text-section font-semibold tracking-tight">Never colour alone</span>
            <span className="text-meta text-muted-foreground">
              Every status carries a word; every trend carries its direction in text.
            </span>
          </Surface>
          <Surface tone="quiet" className="flex flex-col gap-1">
            <span className="text-section font-semibold tracking-tight">Reduced motion</span>
            <span className="text-meta text-muted-foreground">
              One global honouring. Components cannot forget it.
            </span>
          </Surface>
          <Surface tone="quiet" className="flex flex-col gap-1">
            <span className="text-section font-semibold tracking-tight">48dp</span>
            <span className="text-meta text-muted-foreground">
              Mobile touch targets, above the platform floor. A counter is not a desk.
            </span>
          </Surface>
        </div>
      </Section>

    </div>
  );
}
