"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarDays, Clock, Lock, LockOpen } from "lucide-react";

import {
  ApiError,
  type CalendarDayView,
  type FinancialPeriodView,
  type OrganizationCalendar,
  closeFinancialPeriod,
  getCalendarDays,
  getFinancialPeriods,
  getOrganizationCalendar,
  openFinancialPeriod,
  reopenFinancialPeriod,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader, StatTile } from "@/components/page-header";

/**
 * The organization's calendar and its financial periods (DEMO-020).
 *
 * **Everything on this page is the SERVER's answer.** The business date, the
 * month it falls in, the previous month, whether today is a working day — all
 * computed from the organization's own timezone and rendered here verbatim.
 *
 * That is the whole point of the screen, and it is why there is no date
 * arithmetic in this file. DEMO-019 spent a milestone discovering that the
 * portal held its own copies of "what month is it" and got them wrong for
 * every dairy east of UTC; a page that recomputed any of this to display it
 * would be the same defect wearing a different hat. If a figure here is
 * wrong, exactly one place is responsible.
 *
 * Deliberately read-only. The work order asked for the smallest view that
 * demonstrates the capability — current period, previous period, status — and
 * an accounting dashboard is the thing it asked not to build.
 */

const describe = (e: unknown) => {
  if (e instanceof ApiError)
    return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Could not load the calendar";
};

function PeriodRow({
  period,
  busy,
  onClose,
  onReopen,
}: {
  period: FinancialPeriodView;
  busy?: boolean;
  onClose?: () => void;
  onReopen?: () => void;
}) {
  const closed = period.status === "closed";
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-3 last:border-b-0">
      <div>
        <div className="text-sm font-medium">
          {period.period_start} — {period.period_end}
        </div>
        {period.label ? (
          <div className="text-xs text-muted-foreground">{period.label}</div>
        ) : null}
      </div>
      <span
        className={
          closed
            ? "inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium"
            : "inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100"
        }
      >
        {closed ? (
          <Lock className="h-3 w-3" />
        ) : (
          <LockOpen className="h-3 w-3" />
        )}
        {closed ? "Closed" : "Open"}
      </span>
      {/* Closing stops new bills, payments and settlements landing in the
          period. Reopening is deliberately available: a month shut by mistake
          would otherwise be unbillable forever, which is worse than the
          mistake. */}
      {closed && onReopen ? (
        <Button size="sm" variant="ghost" disabled={busy} onClick={onReopen}>
          Reopen
        </Button>
      ) : null}
      {!closed && onClose ? (
        <Button size="sm" variant="secondary" disabled={busy} onClick={onClose}>
          Close
        </Button>
      ) : null}
    </div>
  );
}

export default function OrganizationCalendarPage() {
  const [calendar, setCalendar] = useState<OrganizationCalendar | null>(null);
  const [periods, setPeriods] = useState<FinancialPeriodView[]>([]);
  const [days, setDays] = useState<CalendarDayView[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const cal = await getOrganizationCalendar();
      const [list, exceptions] = await Promise.all([
        getFinancialPeriods(),
        // A year around today: enough to see the holidays that matter without
        // asking the server for a range nobody looks at.
        getCalendarDays(cal.previous_month_start, cal.month_end),
      ]);
      setCalendar(cal);
      setPeriods(list);
      setDays(exceptions);
    } catch (e) {
      setError(describe(e));
    } finally {
      setLoading(false);
    }
  }, []);

  /** Run a period action, then reload — the server's answer is the truth. */
  const act = useCallback(
    async (run: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await run();
        await load();
      } catch (e) {
        setError(describe(e));
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  useEffect(() => {
    // Deferred by a tick, the idiom the rest of the portal uses: calling
    // setState synchronously in an effect body cascades a render, and the
    // lint rule that says so is on for the whole tree.
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  // The previous month's period, matched by its START date rather than by
  // position in the list: a dairy may have declared periods that are not
  // months, and "the one before this" is then not "the row below".
  const previousPeriod = calendar
    ? (periods.find((p) => p.period_start === calendar.previous_month_start) ??
      null)
    : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Business calendar"
        description="The organization's own clock, and the periods its books are kept in."
      />

      {error ? (
        <Card>
          <CardContent className="py-4 text-sm text-destructive">
            {error}
          </CardContent>
        </Card>
      ) : null}

      {loading && !calendar ? (
        <Card>
          <CardContent className="py-4 text-sm text-muted-foreground">
            Loading…
          </CardContent>
        </Card>
      ) : null}

      {calendar ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile
              label="Business date"
              value={calendar.business_date}
              hint={calendar.timezone}
              icon={<CalendarDays className="size-4" />}
            />
            <StatTile
              label="Today"
              value={calendar.is_working_day ? "Working day" : "Non-working"}
              hint="from the organization calendar"
              icon={<Clock className="size-4" />}
            />
            <StatTile
              label="Current month"
              value={`${calendar.month_start} — ${calendar.month_end}`}
              hint="the dairy's month, not UTC's"
              icon={<CalendarDays className="size-4" />}
            />
            <StatTile
              label="Previous month"
              value={`${calendar.previous_month_start} — ${calendar.previous_month_end}`}
              hint="what month-end billing drafts"
              icon={<CalendarDays className="size-4" />}
            />
          </div>

          <Card>
            <CardContent className="space-y-4 py-4">
              <div>
                <h2 className="text-sm font-semibold">Current period</h2>
                <p className="text-xs text-muted-foreground">
                  The financial period today falls in, if the organization has
                  declared one.
                </p>
              </div>
              {calendar.current_period ? (
                <PeriodRow
                  period={calendar.current_period}
                  busy={busy}
                  onClose={() =>
                    act(() => closeFinancialPeriod(calendar.current_period!.id))
                  }
                  onReopen={() =>
                    act(() =>
                      reopenFinancialPeriod(calendar.current_period!.id),
                    )
                  }
                />
              ) : (
                <p className="text-sm text-muted-foreground">
                  No financial period covers {calendar.business_date}. Nothing
                  is restricted — a date outside every declared period is always
                  open.
                </p>
              )}

              <div className="pt-2">
                <h2 className="text-sm font-semibold">Previous period</h2>
              </div>
              {previousPeriod ? (
                <PeriodRow
                  period={previousPeriod}
                  busy={busy}
                  onClose={() =>
                    act(() => closeFinancialPeriod(previousPeriod.id))
                  }
                  onReopen={() =>
                    act(() => reopenFinancialPeriod(previousPeriod.id))
                  }
                />
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">
                    No period declared for {calendar.previous_month_start} —{" "}
                    {calendar.previous_month_end}.
                  </p>
                  {/* The month a dairy actually closes: the one that has
                      ended. Declaring it is the first step, closing it the
                      second — two acts, because declaring must not shut the
                      books by surprise. */}
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={busy}
                    onClick={() =>
                      act(() =>
                        openFinancialPeriod({
                          period_start: calendar.previous_month_start,
                          period_end: calendar.previous_month_end,
                          label: "Previous month",
                        }),
                      )
                    }
                  >
                    Declare previous month
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="py-4">
              <h2 className="mb-1 text-sm font-semibold">
                Calendar exceptions
              </h2>
              <p className="mb-2 text-xs text-muted-foreground">
                Days this organization does not work, or works when it normally
                would not. An absent day is a working day.
              </p>
              {days.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  None declared between {calendar.previous_month_start} and{" "}
                  {calendar.month_end}.
                </p>
              ) : (
                days.map((d) => (
                  <div
                    key={d.id}
                    className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-2 last:border-b-0"
                  >
                    <div>
                      <span className="text-sm font-medium">{d.day}</span>
                      {d.name ? (
                        <span className="ml-2 text-xs text-muted-foreground">
                          {d.name}
                        </span>
                      ) : null}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {d.kind} · {d.working ? "working" : "non-working"}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="py-4">
              <h2 className="mb-2 text-sm font-semibold">
                All financial periods
              </h2>
              {periods.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  None declared yet.
                </p>
              ) : (
                periods.map((p) => (
                  <PeriodRow
                    key={p.id}
                    period={p}
                    busy={busy}
                    onClose={() => act(() => closeFinancialPeriod(p.id))}
                    onReopen={() => act(() => reopenFinancialPeriod(p.id))}
                  />
                ))
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
