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
            Platform bootstrap — SPRINT-001
          </p>
        </div>
        <Button variant="outline" onClick={() => void refresh()}>
          Refresh
        </Button>
      </header>

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
