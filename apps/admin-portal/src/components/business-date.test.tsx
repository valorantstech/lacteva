/**
 * Which day is it, for a dairy? (DEMO-019)
 *
 * The backend answers this in `core/business_time.py` and pins it in
 * `test_business_date_boundaries.py`. The portal has to answer the SAME
 * question independently — it decides which window to ask the server for
 * before the server is involved at all — so the same boundaries are asserted
 * here. If the two ever disagree, a manager asks for "today" and the server
 * aggregates a different day.
 *
 * Every test fixes the instant. A test that used the real clock would pass all
 * afternoon and fail at night, which is exactly how DEMO-019's defect survived
 * to production: the wrong branch is only reachable for part of the day.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  resolveRange,
  todayIn,
  useBusinessToday,
  useDefaultRange,
} from "@/components/date-range";
import { LocaleProvider } from "@/lib/i18n";

const INDIA = "Asia/Kolkata"; // UTC+5:30
const KENYA = "Africa/Nairobi"; // UTC+3
const QATAR = "Asia/Qatar"; // UTC+3

afterEach(() => {
  vi.useRealTimers();
});

/** Freeze the wall clock at a known instant. */
function at(iso: string) {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(iso));
}

describe("the dairy's today", () => {
  it("is not the same date in every dairy at the same instant", () => {
    // 20:00 UTC on the 14th: India is already on the 15th (01:30 IST); Kenya
    // and Qatar are still on the 14th (23:00).
    at("2026-08-14T20:00:00Z");
    expect(todayIn(INDIA)).toBe("2026-08-15");
    expect(todayIn(KENYA)).toBe("2026-08-14");
    expect(todayIn(QATAR)).toBe("2026-08-14");
  });

  it("moves all three past midnight while UTC is still on yesterday", () => {
    // 21:30 UTC: every dairy has turned over, UTC has not. This is the window
    // in which the old `new Date().toISOString()` was wrong for EVERY tenant,
    // not just the Indian one.
    at("2026-08-14T21:30:00Z");
    for (const zone of [INDIA, KENYA, QATAR]) {
      expect(todayIn(zone)).toBe("2026-08-15");
    }
    expect(new Date().toISOString().slice(0, 10)).toBe("2026-08-14");
  });

  it("turns over exactly at local midnight, not before", () => {
    // Local midnight in Bengaluru is 18:30 UTC.
    at("2026-08-14T18:29:59Z");
    expect(todayIn(INDIA)).toBe("2026-08-14");
    at("2026-08-14T18:30:00Z");
    expect(todayIn(INDIA)).toBe("2026-08-15");

    // and 21:00 UTC in Nairobi and Doha.
    at("2026-08-14T20:59:59Z");
    expect(todayIn(KENYA)).toBe("2026-08-14");
    at("2026-08-14T21:00:00Z");
    expect(todayIn(KENYA)).toBe("2026-08-15");
  });

  it("falls back to UTC when the organization has no zone", () => {
    // The server's `FALLBACK_TIMEZONE` is UTC too, so a missing setting means
    // the same thing on both sides rather than two different days.
    at("2026-08-14T21:30:00Z");
    expect(todayIn(null)).toBe("2026-08-14");
  });
});

describe("the range the server is asked for", () => {
  it("asks for the dairy's day, not UTC's", () => {
    at("2026-08-14T21:30:00Z");
    const today = resolveRange("today", KENYA);
    expect(today).toEqual({
      key: "today",
      from: "2026-08-15",
      to: "2026-08-15",
    });

    // "Yesterday" is the dairy's yesterday, which is UTC's today — the case
    // most likely to look right by accident.
    const yesterday = resolveRange("yesterday", KENYA);
    expect(yesterday.from).toBe("2026-08-14");
    expect(yesterday.to).toBe("2026-08-14");
  });

  it("counts back whole calendar days from the dairy's today", () => {
    at("2026-08-14T21:30:00Z");
    // Seven days INCLUDING today: the 9th through the 15th.
    expect(resolveRange("7d", INDIA)).toEqual({
      key: "7d",
      from: "2026-08-09",
      to: "2026-08-15",
    });
    expect(resolveRange("30d", INDIA)).toEqual({
      key: "30d",
      from: "2026-07-17",
      to: "2026-08-15",
    });
  });

  it("crosses a month boundary on the dairy's calendar", () => {
    // 31 Jul 21:30 UTC is already 1 August in every one of these zones. A
    // UTC-built "today" would open the month-end report on July.
    at("2026-07-31T21:30:00Z");
    expect(resolveRange("today", INDIA).from).toBe("2026-08-01");
    expect(resolveRange("yesterday", KENYA).from).toBe("2026-07-31");
  });
});

/**
 * The half that made the previous fix INERT.
 *
 * `resolveRange` was already correct and the screens still showed UTC's day,
 * because the app shell mounts pages before the session probe answers: the
 * organization's timezone arrives on a LATER render, and a `useState`
 * initializer had already frozen the UTC fallback. Nothing failed — the tests
 * above all pass against that code, because they never render a component.
 */
describe("a timezone that arrives after the first render", () => {
  function Screen() {
    const today = useBusinessToday();
    const [range, setRange] = useDefaultRange("7d");
    return (
      <div>
        <span data-testid="today">{today}</span>
        <span data-testid="from">{range.from}</span>
        <span data-testid="to">{range.to}</span>
        <button
          onClick={() =>
            setRange({ key: "custom", from: "2026-01-01", to: "2026-01-31" })
          }
        >
          pick
        </button>
      </div>
    );
  }

  it("corrects the default once the organization is known", () => {
    at("2026-08-14T21:30:00Z"); // Nairobi is on the 15th, UTC on the 14th.

    // First render is what the shell actually does: signed-in state unknown,
    // so no timezone. This is the UTC fallback, and it is not yet wrong.
    const view = render(
      <LocaleProvider locale="en" currency={null} timezone={null}>
        <Screen />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("today")).toHaveTextContent("2026-08-14");

    // The probe answers. The window must MOVE — this is the assertion the
    // whole file exists for, and the one a pure-function test cannot make.
    view.rerender(
      <LocaleProvider locale="en" currency={null} timezone={KENYA}>
        <Screen />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("today")).toHaveTextContent("2026-08-15");
    expect(screen.getByTestId("to")).toHaveTextContent("2026-08-15");
    expect(screen.getByTestId("from")).toHaveTextContent("2026-08-09");
  });

  it("does not overwrite a window the reader chose", () => {
    at("2026-08-14T21:30:00Z");

    const view = render(
      <LocaleProvider locale="en" currency={null} timezone={null}>
        <Screen />
      </LocaleProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "pick" }));
    expect(screen.getByTestId("from")).toHaveTextContent("2026-01-01");

    // A late-arriving timezone corrects a DEFAULT. It must not reach in and
    // replace a window somebody deliberately asked for.
    view.rerender(
      <LocaleProvider locale="en" currency={null} timezone={KENYA}>
        <Screen />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("from")).toHaveTextContent("2026-01-01");
    expect(screen.getByTestId("to")).toHaveTextContent("2026-01-31");
  });
});
