/**
 * What these pages say before they know anything (LACTEVA-ADMIN-001, UX-1).
 *
 * The audit called these four pages blank while their first fetch is in
 * flight. Read on the way in, three of them turned out to do something worse
 * than render nothing: they asserted a confident negative they had not yet
 * established.
 *
 *   /admin/roles       "No roles are readable with this session."  — which
 *                      reads as a permission failure, on a page about
 *                      permissions, when nothing has been asked yet.
 *   /admin/operations  "No backup runs recorded."                  — on the
 *                      one page whose whole job is to say whether the
 *                      platform is protected.
 *   /routes            0 routes · 0 vehicles · 0 drivers · 0 runs   — four
 *                      figures presented as counts.
 *
 * Every list on these pages starts `[]`, so emptiness alone cannot tell "none"
 * from "not asked yet". Each test therefore holds the platform's answer OPEN
 * and asserts both halves: the loading construct is present, and the sentence
 * the page must not say yet is absent. Asserting only the skeleton would pass
 * on a page that showed both.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
}));

import * as api from "@/lib/api";
import OperationsPage from "@/app/admin/operations/page";
import RolesPage from "@/app/admin/roles/page";
import RoutesPage from "@/app/routes/page";

/** A request that has left and will not come back during the test. */
const pending = () => new Promise(() => {});

/** The skeleton primitives paint `lacteva-skeleton`; they are aria-hidden. */
const skeletons = (c: HTMLElement) =>
  c.querySelectorAll(".lacteva-skeleton").length;

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("no page states a negative it has not established", () => {
  it("/admin/roles shows a skeleton, not a permission failure", async () => {
    vi.spyOn(api, "listRoles").mockReturnValue(pending() as never);
    vi.spyOn(api, "listPermissions").mockReturnValue(pending() as never);
    vi.spyOn(api, "listPeople").mockReturnValue(pending() as never);
    vi.spyOn(api, "listCenters").mockReturnValue(pending() as never);

    const { container } = render(<RolesPage />);

    await waitFor(() => expect(skeletons(container)).toBeGreaterThan(0));
    expect(
      screen.queryByText("No roles are readable with this session."),
    ).toBeNull();
  });

  it("/admin/operations shows a skeleton, not 'no backup runs'", async () => {
    vi.spyOn(api, "getBackupStatus").mockReturnValue(pending() as never);
    vi.spyOn(api, "listBackupRuns").mockReturnValue(pending() as never);

    const { container } = render(<OperationsPage />);

    await waitFor(() => expect(skeletons(container)).toBeGreaterThan(0));
    expect(screen.queryByText("No backup runs recorded.")).toBeNull();
  });

  it("/routes shows loading, not four counts of zero", async () => {
    vi.spyOn(api, "listRoutes").mockReturnValue(pending() as never);
    vi.spyOn(api, "listVehicles").mockReturnValue(pending() as never);
    vi.spyOn(api, "listDrivers").mockReturnValue(pending() as never);
    vi.spyOn(api, "listDeliveryRuns").mockReturnValue(pending() as never);

    const { container } = render(<RoutesPage />);

    // The four summary metrics carry a shape where the number would go.
    await waitFor(() => expect(skeletons(container)).toBeGreaterThanOrEqual(4));
    // `LoadingState` announces itself; the lists below are covered by it.
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);

    // The sentences the page must not say yet.
    expect(screen.queryByText("No routes yet.")).toBeNull();
    expect(screen.queryByText("No run planned for today yet.")).toBeNull();
    // And no bare count where a metric will land.
    expect(screen.queryAllByText("0")).toHaveLength(0);
  });
});
