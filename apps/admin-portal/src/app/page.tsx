"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Overview = {
  centers: number;
  suppliers: number;
  transactions: number;
  draftSettlements: number;
  finalizedSettlements: number;
};

type Readiness = {
  status: "ok" | "degraded";
  checks: Record<string, boolean>;
};

type PlatformStatus =
  | { state: "loading" }
  | { state: "unreachable"; error: string }
  | { state: "ready"; readiness: Readiness };

export default function Home() {
  const [status, setStatus] = useState<PlatformStatus>({ state: "loading" });
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);

  const loadOverview = useCallback(async () => {
    // Procurement snapshot — only renders when a session token exists.
    const token =
      typeof window !== "undefined" ? window.localStorage.getItem("lacteva.access_token") : null;
    if (!token) return;
    const count = async (path: string) => {
      const res = await fetch(`${API_URL}${path}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (!res.ok) throw new Error(String(res.status));
      return ((await res.json()) as { total: number }).total;
    };
    try {
      const [centers, suppliers, transactions, drafts, finalized] = await Promise.all([
        count("/v1/collection-centers?limit=1&offset=0"),
        count("/v1/suppliers?limit=1&offset=0"),
        count("/v1/milk-transactions?limit=1&offset=0"),
        count("/v1/settlements?status=draft&limit=1&offset=0"),
        count("/v1/settlements?status=finalized&limit=1&offset=0"),
      ]);
      setOverview({
        centers,
        suppliers,
        transactions,
        draftSettlements: drafts,
        finalizedSettlements: finalized,
      });
    } catch {
      setOverview(null); // not signed in for this tenant — hide the row
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => void loadOverview(), 0);
    return () => clearTimeout(t);
  }, [loadOverview]);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/health/ready`, { cache: "no-store" });
      const readiness = (await res.json()) as Readiness;
      setStatus({ state: "ready", readiness });
    } catch (err) {
      setStatus({
        state: "unreachable",
        error: err instanceof Error ? err.message : String(err),
      });
    }
    setCheckedAt(new Date().toLocaleTimeString());
  }, []);

  useEffect(() => {
    const tick = () => void refresh();
    const initial = setTimeout(tick, 0); // deferred: no sync setState in effect body
    const timer = setInterval(tick, 10_000);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
    };
  }, [refresh]);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Lacteva Admin Portal
          </h1>
          <p className="text-sm text-muted-foreground">
            Procurement operations dashboard
          </p>
        </div>
        <Button variant="outline" onClick={() => void refresh()}>
          Refresh
        </Button>
      </header>

      {overview && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {(
            [
              ["Centers", overview.centers, "/centers"],
              ["Suppliers", overview.suppliers, "/suppliers"],
              ["Transactions", overview.transactions, "/transactions"],
              ["Draft settlements", overview.draftSettlements, "/settlements"],
              ["Finalized", overview.finalizedSettlements, "/settlements"],
            ] as const
          ).map(([label, value, href]) => (
            <a key={label} href={href}>
              <Card className="transition-colors hover:bg-muted/50">
                <CardContent className="pt-4">
                  <p className="text-2xl font-semibold">{value}</p>
                  <p className="text-xs text-muted-foreground">{label}</p>
                </CardContent>
              </Card>
            </a>
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            platform-core
            {status.state === "loading" && (
              <Badge variant="secondary">checking…</Badge>
            )}
            {status.state === "unreachable" && (
              <Badge variant="destructive">unreachable</Badge>
            )}
            {status.state === "ready" && (
              <Badge
                variant={
                  status.readiness.status === "ok" ? "default" : "destructive"
                }
              >
                {status.readiness.status}
              </Badge>
            )}
          </CardTitle>
          <CardDescription>
            {API_URL} — polled every 10s
            {checkedAt ? ` · last check ${checkedAt}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {status.state === "unreachable" && (
            <p className="text-sm text-muted-foreground">
              Backend not reachable ({status.error}). Start it with{" "}
              <code className="rounded bg-muted px-1">make dev</code> from the
              repository root.
            </p>
          )}
          {status.state === "ready" && (
            <ul className="flex flex-col gap-2">
              {Object.entries(status.readiness.checks).map(([name, healthy]) => (
                <li
                  key={name}
                  className="flex items-center justify-between text-sm"
                >
                  <span>{name}</span>
                  <Badge variant={healthy ? "default" : "destructive"}>
                    {healthy ? "healthy" : "down"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
          <div className="flex gap-4 pt-2 text-sm">
            <a className="text-primary underline-offset-4 hover:underline" href="/login">
              Sign in →
            </a>
            <a className="text-primary underline-offset-4 hover:underline" href="/transactions">
              Transactions →
            </a>
            <a className="text-primary underline-offset-4 hover:underline" href="/suppliers">
              Suppliers →
            </a>
            <a className="text-primary underline-offset-4 hover:underline" href="/centers">
              Collection centers →
            </a>
            <a className="text-primary underline-offset-4 hover:underline" href="/rate-cards">
              Rate cards →
            </a>
            <a className="text-primary underline-offset-4 hover:underline" href="/matrices">
              Pricing matrices →
            </a>
            <a className="text-primary underline-offset-4 hover:underline" href="/resolve">
              Resolution playground →
            </a>
            <a className="text-primary underline-offset-4 hover:underline" href="/settlements">
              Settlements →
            </a>
            <a
              className="text-primary underline-offset-4 hover:underline"
              href={`${API_URL}/docs`}
              target="_blank"
              rel="noreferrer"
            >
              OpenAPI docs ↗
            </a>
            <a
              className="text-primary underline-offset-4 hover:underline"
              href={`${API_URL}/metrics`}
              target="_blank"
              rel="noreferrer"
            >
              Metrics ↗
            </a>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
