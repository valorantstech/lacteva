"use client";

import { Money, Quantity } from "@/components/money";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * The dairy, at a glance (LACTEVA-ADMIN-015; board: Dashboard).
 *
 * The dashboard opened on a grid of six equal cards, and a manager reading it
 * had to work out for themselves which four mattered. This band answers the
 * four questions an owner actually opens the page with — how much milk, from
 * how many farmers, what it cost, what came back in — and the rest of the page
 * stays where it was, for the reader who wants the detail.
 *
 * **On-brand tokens, because the ground is brand.** `--on-brand`,
 * `--on-brand-muted` and `--on-brand-positive` were measured for exactly this
 * surface: `--muted-foreground` and `--success` are tuned for a milk ground
 * and effectively disappear on deep green. Using them here would have been a
 * contrast failure dressed as a colour choice.
 *
 * **Every figure is the platform's own.** Nothing on this band is summed, and
 * nothing is converted — the litres, the farmer count, the payable and the
 * received are four fields off the dashboard report, rendered by `<Quantity>`
 * and `<Money>` from the exact decimal strings the platform sent.
 */
export function DashboardHero({
  dateLine,
  centresCollecting,
  centresTotal,
  litres,
  fill,
  farmers,
  payable,
  payableCurrency,
  received,
  receivedCurrency,
}: {
  /** The window these figures cover, as the PLATFORM echoed it back. */
  dateLine: string;
  centresCollecting: number | null;
  centresTotal: number | null;
  /** Kilograms, exactly as the platform counted them. */
  litres: number | null;
  /**
   * How full the vessel is, 0..1 — or null when there is nothing to measure
   * against, in which case no vessel is drawn at all. A vessel is a
   * measurement and a measurement needs a scale (LACTEVA-MOBILE-007).
   */
  fill: number | null;
  farmers: number | null;
  payable: string | null;
  payableCurrency: string | null;
  received: string | null;
  receivedCurrency: string | null;
}) {
  const t = useT();
  const known = centresCollecting !== null && centresTotal !== null;

  return (
    <div className="relative -mx-4 overflow-hidden bg-[image:var(--gradient-dairy)] px-4 py-7 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
      {/* The light in the corner. Decoration, and hidden from anyone who is
          not looking at it. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -end-16 -top-20 size-[340px] rounded-full bg-[radial-gradient(circle_at_38%_32%,color-mix(in_oklch,var(--on-brand)_13%,transparent),transparent_62%)]"
      />
      <div className="relative flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <p className="text-sm text-on-brand-muted">{dateLine}</p>
            <h1 className="text-page font-semibold tracking-tight text-on-brand">
              {t("dashboard.heroTitle")}
            </h1>
          </div>
          {known ? (
            <p
              className="flex items-center gap-2 rounded-full border border-on-brand/20 bg-on-brand/10 px-3.5 py-1.5 text-sm font-medium text-on-brand"
              role="status"
            >
              {/* Never colour alone: the dot is the fast signal and the
                  sentence is the one that survives not seeing it. */}
              <span
                aria-hidden
                className={cn(
                  "size-2 rounded-full",
                  centresCollecting! > 0
                    ? "bg-on-brand-positive"
                    : "bg-on-brand-muted",
                )}
              />
              {t("dashboard.centresCollecting", {
                collecting: String(centresCollecting),
                total: String(centresTotal),
              })}
            </p>
          ) : null}
        </div>

        <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-[1.3fr_1fr_1fr_1fr]">
          <HeroCell>
            <div className="flex items-center gap-4">
              {fill === null ? null : <MilkVessel fill={fill} />}
              <HeroFigure
                value={
                  litres === null ? "—" : <Quantity value={litres} unit="kg" />
                }
                caption={t("dashboard.heroCollected")}
              />
            </div>
          </HeroCell>
          <HeroCell>
            <HeroFigure
              value={farmers === null ? "—" : String(farmers)}
              caption={t("dashboard.heroFarmers")}
            />
          </HeroCell>
          <HeroCell>
            <HeroFigure
              value={
                payable === null ? (
                  "—"
                ) : (
                  <Money amount={payable} currency={payableCurrency} />
                )
              }
              caption={t("dashboard.heroPayable")}
            />
          </HeroCell>
          <HeroCell>
            <HeroFigure
              // Money coming IN is the one figure on this band that is good
              // news, and the on-brand positive token is what says so on a
              // ground where `--success` cannot be read.
              tone="positive"
              value={
                received === null ? (
                  "—"
                ) : (
                  <Money amount={received} currency={receivedCurrency} />
                )
              }
              caption={t("dashboard.heroReceived")}
            />
          </HeroCell>
        </div>
      </div>
    </div>
  );
}

function HeroCell({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-on-brand/15 bg-on-brand/[0.09] px-4 py-4">
      {children}
    </div>
  );
}

function HeroFigure({
  value,
  caption,
  tone,
}: {
  value: React.ReactNode;
  caption: string;
  tone?: "positive";
}) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span
        className={cn(
          "truncate text-metric font-semibold tracking-tight tabular-nums",
          tone === "positive" ? "text-on-brand-positive" : "text-on-brand",
        )}
      >
        {value}
      </span>
      <span className="text-meta text-on-brand-muted">{caption}</span>
    </div>
  );
}

/**
 * The day's milk, as a thing rather than a number.
 *
 * The fill RISES on first paint, once — `--motion-slow` on the liquid curve,
 * which is the token for something arriving. `prefers-reduced-motion` is
 * honoured by the global rule in `globals.css`, which collapses every
 * animation to 1ms; the vessel is drawn at its final height either way, so
 * removing the motion removes only the motion.
 */
export function MilkVessel({ fill }: { fill: number }) {
  const percent = Math.round(Math.min(Math.max(fill, 0), 1) * 100);
  return (
    <div
      role="img"
      aria-label={`${percent}%`}
      className="relative h-[66px] w-[46px] shrink-0 overflow-hidden rounded-t-[10px] rounded-b-[14px] border-[1.5px] border-on-brand/30 bg-on-brand/10"
    >
      <div
        data-testid="vessel-fill"
        className="lacteva-vessel absolute inset-x-0 bottom-0 bg-on-brand"
        style={{ height: `${percent}%` }}
      >
        {/* Milk has a surface. Drawing one is the difference between a vessel
            and a progress bar. */}
        <span
          aria-hidden
          className="absolute inset-x-0 -top-1 h-2 rounded-[50%] bg-on-brand"
        />
      </div>
    </div>
  );
}
