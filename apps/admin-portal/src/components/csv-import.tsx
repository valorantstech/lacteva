"use client";

/**
 * Business-data import (P0-PILOT-003).
 *
 * The dairy hands over a spreadsheet; the operator saves it as CSV and loads
 * it here. Three honesty rules, enforced by shape:
 *
 * 1. NOTHING is invented or repaired. Rows go to the platform exactly as
 *    parsed; the SERVER validates each one and answers per row, so a bad
 *    line fails alone with its reason, never silently and never the batch.
 * 2. PREVIEW BEFORE SEND. The operator sees every parsed row — and which
 *    ones are missing their one required column — before anything is posted.
 * 3. THE RESULT IS THE RECEIPT. Every row's outcome (created code or the
 *    server's own error text, including "duplicate of existing customer
 *    CUS-…") stays on screen for the operator to act on.
 *
 * XLSX is deliberately not parsed here — "File → Save as CSV" is one step in
 * the dairy's spreadsheet tool, and a CSV is inspectable by everyone.
 */

import { useMemo, useState } from "react";
import { Upload } from "lucide-react";
import { type ImportRowOutcome, importCustomers, importSuppliers, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

/** Minimal CSV parser: quoted fields, embedded commas/quotes, CR/LF. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        field += c;
      }
    } else if (c === '"') {
      quoted = true;
    } else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i += 1;
      row.push(field);
      field = "";
      if (row.some((f) => f.trim() !== "")) rows.push(row);
      row = [];
    } else {
      field += c;
    }
  }
  row.push(field);
  if (row.some((f) => f.trim() !== "")) rows.push(row);
  return rows;
}

type Kind = "suppliers" | "customers";

const SPEC: Record<
  Kind,
  {
    required: string;
    columns: string[];
    hint: string;
    toRow: (r: Record<string, string>) => Record<string, unknown>;
  }
> = {
  suppliers: {
    required: "full_name",
    columns: ["code", "full_name", "phone", "village", "center_codes"],
    hint: "center_codes separates multiple centres with ; — codes must already exist.",
    toRow: (r) => ({
      ...(r.code ? { code: r.code } : {}),
      full_name: r.full_name ?? "",
      phone: r.phone ?? "",
      village: r.village ?? "",
      center_codes: (r.center_codes ?? "")
        .split(";")
        .map((c) => c.trim())
        .filter(Boolean),
    }),
  },
  customers: {
    required: "name",
    columns: [
      "name",
      "customer_type",
      "phone",
      "address",
      "plan_product",
      "plan_quantity",
      "plan_unit",
      "plan_price",
    ],
    hint:
      "customer_type e.g. shop/household. The plan_* columns together create the standing order (e.g. RAW-COW-MILK, 20, L, 58.00); leave all four empty for no order.",
    toRow: (r) => ({
      name: r.name ?? "",
      ...(r.customer_type ? { customer_type: r.customer_type } : {}),
      phone: r.phone ?? "",
      address: r.address ?? "",
      ...(r.plan_product && r.plan_quantity && r.plan_price
        ? {
            plan: {
              product: r.plan_product,
              default_quantity: r.plan_quantity,
              quantity_unit: r.plan_unit || "L",
              unit_price: r.plan_price,
            },
          }
        : {}),
    }),
  },
};

export function CsvImport({ kind }: { kind: Kind }) {
  const spec = SPEC[kind];
  const [csv, setCsv] = useState("");
  const [results, setResults] = useState<ImportRowOutcome[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const parsed = useMemo(() => {
    const table = parseCsv(csv);
    if (table.length < 2) return null;
    const header = table[0].map((h) => h.trim().toLowerCase());
    const rows = table.slice(1).map((cells) => {
      const record: Record<string, string> = {};
      header.forEach((name, i) => {
        record[name] = (cells[i] ?? "").trim();
      });
      return record;
    });
    return { header, rows };
  }, [csv]);

  const missingRequired = useMemo(
    () =>
      parsed
        ? parsed.rows
            .map((r, i) => ({ line: i + 2, ok: (r[spec.required] ?? "") !== "" }))
            .filter((x) => !x.ok)
        : [],
    [parsed, spec.required],
  );

  const submit = async () => {
    if (!parsed) return;
    setBusy(true);
    setError(null);
    setResults(null);
    try {
      const rows = parsed.rows.map(spec.toRow);
      const send = kind === "suppliers" ? importSuppliers : importCustomers;
      setResults(await send(rows));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "the import request failed");
    } finally {
      setBusy(false);
    }
  };

  const created = results?.filter((r) => r.status === "created").length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">1 · Load the CSV</CardTitle>
          <CardDescription>
            First line must be the column headers. Recognised columns:{" "}
            <code className="text-xs">{spec.columns.join(", ")}</code> —{" "}
            <span className="font-medium">{spec.required}</span> is required.{" "}
            {spec.hint} From Excel/Sheets use File → Save as CSV.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <input
            type="file"
            accept=".csv,text/csv"
            aria-label="CSV file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              void file.text().then(setCsv);
            }}
          />
          <textarea
            aria-label="CSV content"
            className="min-h-40 w-full rounded-md border bg-background p-2 font-mono text-xs"
            placeholder={`${spec.columns.join(",")}\n…`}
            value={csv}
            onChange={(e) => {
              setCsv(e.target.value);
              setResults(null);
            }}
          />
        </CardContent>
      </Card>

      {parsed ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              2 · Preview — {parsed.rows.length} row
              {parsed.rows.length === 1 ? "" : "s"}
            </CardTitle>
            <CardDescription>
              {missingRequired.length > 0
                ? `${missingRequired.length} row(s) are missing “${spec.required}” (line${
                    missingRequired.length === 1 ? "" : "s"
                  } ${missingRequired.map((x) => x.line).join(", ")}) — they will be sent and will fail individually with the server's reason.`
                : "Every row carries the required column. Nothing has been sent yet."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-start text-muted-foreground">
                    <th className="p-1 text-start">#</th>
                    {parsed.header.map((h) => (
                      <th key={h} className="p-1 text-start">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {parsed.rows.slice(0, 50).map((r, i) => (
                    <tr key={i} className="border-t">
                      <td className="p-1 tabular-nums text-muted-foreground">
                        {i + 1}
                      </td>
                      {parsed.header.map((h) => (
                        <td key={h} className="p-1">
                          {r[h]}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {parsed.rows.length > 50 ? (
                <p className="p-2 text-xs text-muted-foreground">
                  … and {parsed.rows.length - 50} more (all will be sent).
                </p>
              ) : null}
            </div>
            <div className="mt-4">
              <Button type="button" onClick={submit} disabled={busy}>
                <Upload aria-hidden className="me-1.5 size-4" />
                {busy ? "Importing…" : `Import ${parsed.rows.length} rows`}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          The import could not run — {error}
        </p>
      ) : null}

      {results ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              3 · Result — {created} created, {results.length - created} failed
            </CardTitle>
            <CardDescription>
              Failed rows were not imported and changed nothing. Fix them in
              the CSV and import just those lines again.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-1 text-sm">
              {results.map((r) => (
                <li key={r.row} className="flex items-baseline gap-2">
                  <span className="tabular-nums text-muted-foreground">
                    row {r.row + 1}
                  </span>
                  {r.status === "created" ? (
                    <span>created {r.code ?? ""}</span>
                  ) : (
                    <span className="text-destructive">{r.error}</span>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
