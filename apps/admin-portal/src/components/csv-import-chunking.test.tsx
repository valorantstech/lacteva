/**
 * Large imports (P1-SCALE-RACE-001).
 *
 * The platform refuses more than `MAX_IMPORT_ROWS` (500) in one request, and
 * the portal used to send the whole file regardless — so a dairy's actual
 * 2,000-farmer spreadsheet was refused outright with "import limited to 500
 * rows". The feature failed on precisely the file it exists for.
 *
 * What these pin is not just "it chunks", but the three things that make a
 * chunked import trustworthy to the operator holding the spreadsheet:
 *
 *  - the row numbers in the receipt are the file's own, not each batch's;
 *  - a failure stops, and says where, instead of guessing;
 *  - nothing is retried, because a retried batch could create every farmer in
 *    it twice and the portal sends no idempotency key.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/suppliers/import",
}));

import SupplierImportPage from "@/app/suppliers/import/page";
import { IMPORT_CHUNK_ROWS, importInChunks } from "@/lib/api";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/** The platform's answer for a batch: one "created" verdict per row given. */
const createdFor = (batch: Array<Record<string, unknown>>) =>
  json(
    batch.map((_, i) => ({ row: i, status: "created", supplier_id: `s${i}` })),
  );

const rowsOf = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ full_name: `Farmer ${i}` }));

const bodyRows = (call: unknown[]) =>
  JSON.parse(String((call[1] as RequestInit)?.body)).rows as unknown[];

beforeEach(() => vi.unstubAllGlobals());

describe("a file larger than the platform's per-request limit", () => {
  it("goes out in batches the platform will accept", async () => {
    const spy = vi.fn(async (_url: string, init: RequestInit) =>
      createdFor(JSON.parse(String(init.body)).rows),
    );
    vi.stubGlobal("fetch", spy);

    const outcome = await importInChunks("suppliers", rowsOf(1200));

    expect(spy).toHaveBeenCalledTimes(3);
    expect(spy.mock.calls.map((c) => bodyRows(c).length)).toEqual([
      500, 500, 200,
    ]);
    expect(outcome.stoppedAt).toBeNull();
    expect(outcome.results).toHaveLength(1200);
  });

  it("numbers the receipt by the operator's file, not by the batch", async () => {
    const spy = vi.fn(async (_url: string, init: RequestInit) =>
      createdFor(JSON.parse(String(init.body)).rows),
    );
    vi.stubGlobal("fetch", spy);

    const outcome = await importInChunks("suppliers", rowsOf(1200));

    // Every batch answers "row 0, row 1, …"; the operator has one file.
    expect(outcome.results.map((r) => r.row)).toEqual(
      Array.from({ length: 1200 }, (_, i) => i),
    );
    expect(new Set(outcome.results.map((r) => r.row)).size).toBe(1200);
  });

  it("reports progress as each batch lands", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) =>
        createdFor(JSON.parse(String(init.body)).rows),
      ),
    );
    const seen: number[] = [];

    await importInChunks("suppliers", rowsOf(1200), (p) => seen.push(p.sent));

    expect(seen).toEqual([500, 1000, 1200]);
  });

  it("still sends a small file as a single request", async () => {
    const spy = vi.fn(async (_url: string, init: RequestInit) =>
      createdFor(JSON.parse(String(init.body)).rows),
    );
    vi.stubGlobal("fetch", spy);

    await importInChunks("suppliers", rowsOf(IMPORT_CHUNK_ROWS));

    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("when a batch fails half way through", () => {
  const failingSecondBatch = () => {
    let call = 0;
    return vi.fn(async (_url: string, init: RequestInit) => {
      call += 1;
      if (call === 2)
        return json({ detail: "the platform is unavailable" }, 503);
      return createdFor(JSON.parse(String(init.body)).rows);
    });
  };

  it("keeps what was imported and says exactly where it stopped", async () => {
    vi.stubGlobal("fetch", failingSecondBatch());

    const outcome = await importInChunks("suppliers", rowsOf(1200));

    // The first batch really was created; the receipt must survive.
    expect(outcome.results).toHaveLength(500);
    expect(outcome.stoppedAt).toBe(500);
    expect(outcome.error).toContain("the platform is unavailable");
  });

  it("does not retry the batch that failed", async () => {
    const spy = failingSecondBatch();
    vi.stubGlobal("fetch", spy);

    await importInChunks("suppliers", rowsOf(1200));

    // Two calls: the one that worked and the one that did not. A third would
    // mean a resend of rows that may already exist.
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("shows the operator the receipt and the boundary, on the page", async () => {
    vi.stubGlobal("fetch", failingSecondBatch());
    render(<SupplierImportPage />);

    const box = screen.getByLabelText("CSV content");
    await userEvent.click(box);
    await userEvent.paste(
      "full_name\n" +
        Array.from({ length: 600 }, (_, i) => `Farmer ${i}`).join("\n") +
        "\n",
    );

    await userEvent.click(
      await screen.findByRole("button", { name: /import 600 rows/i }),
    );

    // 500 created and listed, and the file line the run stopped at — 502,
    // because row 501 of the data is line 502 of the file.
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("alert").textContent).toMatch(
      /line 502 onward was sent/,
    );
    expect(await screen.findByText(/500 created/)).toBeInTheDocument();
  });
});
