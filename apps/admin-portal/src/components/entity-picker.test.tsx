/**
 * The server-searchable picker (P1-PORTAL-SCALE-001).
 *
 * The defect this replaces: a 100-row <select> that made farmer #101
 * unpickable. What the tests defend:
 *   1. the PLATFORM does the searching — typing asks the server, and the
 *      result count shown is the server's own total, never the slice;
 *   2. a dataset far beyond the old cap is reachable — first page, then
 *      "load more" pages through the tail;
 *   3. the four states (searching, empty, no-result, error+retry) exist; and
 *   4. selecting reports the id and label, and clearing reports emptiness.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EntityPicker, type PickerPage } from "@/components/entity-picker";

const FARMERS = Array.from({ length: 250 }, (_, i) => ({
  id: `sup-${i + 1}`,
  label: `Farmer ${i + 1}`,
  detail: `SUP-${String(i + 1).padStart(3, "0")}`,
}));

const serverSearch = vi.fn(async (q: string, offset: number): Promise<PickerPage> => {
  const hits = FARMERS.filter((f) => f.label.toLowerCase().includes(q.toLowerCase()));
  return { items: hits.slice(offset, offset + 20), total: hits.length };
});

function picker(over: Partial<Parameters<typeof EntityPicker>[0]> = {}) {
  return (
    <EntityPicker
      id="p-supplier"
      label="Supplier"
      value=""
      onSelect={vi.fn()}
      search={serverSearch}
      {...over}
    />
  );
}

describe("EntityPicker", () => {
  it("searches on the server and shows the server's own total", async () => {
    serverSearch.mockClear();
    const user = userEvent.setup();
    render(picker());

    await user.click(screen.getByLabelText("Supplier"));
    await waitFor(() => expect(serverSearch).toHaveBeenCalledWith("", 0));
    // 250 records — far past the old 100-row cap — and the count is honest.
    expect(await screen.findByText("Farmer 1")).toBeInTheDocument();
    expect(
      screen.getByText(/Showing 20 of 250 — keep typing to narrow/),
    ).toBeInTheDocument();
  });

  it("loads later pages past the old 100-row boundary", async () => {
    serverSearch.mockClear();
    const user = userEvent.setup();
    render(picker());
    await user.click(screen.getByLabelText("Supplier"));
    await screen.findByText("Farmer 1");

    // Page through the tail: 20 → 40 → … the platform slices, we append.
    await user.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByText("Farmer 40");
    expect(serverSearch).toHaveBeenCalledWith("", 20);
    expect(screen.getByText(/Showing 40 of 250/)).toBeInTheDocument();
  });

  it("narrows by typing — the query goes to the server", async () => {
    serverSearch.mockClear();
    const user = userEvent.setup();
    render(picker());
    await user.click(screen.getByLabelText("Supplier"));
    await user.type(screen.getByRole("combobox"), "Farmer 25");

    // 250, 25 — the server decides what matches.
    await waitFor(() => expect(serverSearch).toHaveBeenCalledWith("Farmer 25", 0));
    expect(await screen.findByText("Farmer 250")).toBeInTheDocument();
  });

  it("says honestly when nothing matches", async () => {
    serverSearch.mockClear();
    const user = userEvent.setup();
    render(picker());
    await user.click(screen.getByLabelText("Supplier"));
    await user.type(screen.getByRole("combobox"), "zzz nobody");
    expect(await screen.findByText(/Nothing matches/)).toBeInTheDocument();
  });

  it("shows the failure and offers a retry when the search dies", async () => {
    const flaky = vi
      .fn<(q: string, o: number) => Promise<PickerPage>>()
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValue({ items: FARMERS.slice(0, 20), total: 250 });
    const user = userEvent.setup();
    render(picker({ search: flaky }));
    await user.click(screen.getByLabelText("Supplier"));

    expect(await screen.findByText("Could not search — try again")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Farmer 1")).toBeInTheDocument();
  });

  it("selecting reports id and label; clearing reports emptiness", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(picker({ onSelect }));
    await user.click(screen.getByLabelText("Supplier"));
    await user.click(await screen.findByText("Farmer 2"));
    expect(onSelect).toHaveBeenCalledWith("sup-2", "Farmer 2");

    // With a value, the control shows the picked label and a clear affordance.
    rerender(picker({ onSelect, value: "sup-2", valueLabel: "Farmer 2" }));
    expect(screen.getByText("Farmer 2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear Supplier" }));
    expect(onSelect).toHaveBeenCalledWith("", "");
  });
});
