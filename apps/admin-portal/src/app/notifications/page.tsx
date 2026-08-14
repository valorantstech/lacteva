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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ApiError,
  Notification,
  NotificationPage,
  NotificationStats,
  NotificationTemplate,
  RenderedPreview,
  getNotificationStats,
  listNotificationTemplates,
  listNotifications,
  previewNotificationTemplate,
  retryNotification,
  retryPendingNotifications,
} from "@/lib/api";

const PAGE_SIZE = 15;
const STATUSES = ["", "sent", "failed", "dead", "pending"] as const;
const CHANNELS = ["", "sms", "email"] as const;

const statusVariant = (s: string) =>
  s === "sent" ? "default" : s === "dead" ? "destructive" : "secondary";

export default function NotificationsPage() {
  const [page, setPage] = useState<NotificationPage | null>(null);
  const [stats, setStats] = useState<NotificationStats | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [channel, setChannel] = useState("");
  const [templateKey, setTemplateKey] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Notification | null>(null);
  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [result, summary] = await Promise.all([
        listNotifications({ q, status, channel, template_key: templateKey, limit: PAGE_SIZE, offset }),
        getNotificationStats(),
      ]);
      setPage(result);
      setStats(summary);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load notifications");
    }
  }, [q, status, channel, templateKey, offset]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 150);
    return () => clearTimeout(t);
  }, [refresh]);

  useEffect(() => {
    listNotificationTemplates()
      .then(setTemplates)
      .catch(() => setTemplates([]));
  }, []);

  async function retryOne(id: string) {
    try {
      const updated = await retryNotification(id);
      setNote(`Retried — now ${updated.status}.`);
      setError(null);
      if (selected?.id === id) setSelected(updated);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Retry failed");
    }
  }

  async function sweep() {
    try {
      const result = await retryPendingNotifications();
      setNote(`Swept ${result.retried}: ${result.sent} sent, ${result.failed} still failing.`);
      setError(null);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Sweep failed");
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const templateKeys = [...new Set(templates.map((t) => t.key))].sort();

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Notifications</h1>
          <p className="text-sm text-muted-foreground">
            Every message the platform sent, why it was sent, and whether it arrived
          </p>
        </div>
        <Button variant="outline" onClick={sweep}>
          Retry all due
        </Button>
      </header>

      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Total" value={stats.total} />
          <StatCard label="Delivered" value={stats.by_status.sent ?? 0} />
          <StatCard
            label="Failing"
            value={stats.by_status.failed ?? 0}
            tone={(stats.by_status.failed ?? 0) > 0 ? "warn" : undefined}
          />
          <StatCard
            label="Dead letters"
            value={stats.by_status.dead ?? 0}
            tone={(stats.by_status.dead ?? 0) > 0 ? "bad" : undefined}
          />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search recipient or message text…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
          className="max-w-xs"
        />
        <Select
          value={status}
          onChange={(v) => {
            setStatus(v);
            setOffset(0);
          }}
          options={[...STATUSES]}
          allLabel="All statuses"
        />
        <Select
          value={channel}
          onChange={(v) => {
            setChannel(v);
            setOffset(0);
          }}
          options={[...CHANNELS]}
          allLabel="All channels"
        />
        <Select
          value={templateKey}
          onChange={(v) => {
            setTemplateKey(v);
            setOffset(0);
          }}
          options={["", ...templateKeys]}
          allLabel="All templates"
        />
        {stats && stats.retryable > 0 && (
          <Badge variant="outline" className="ml-auto">
            {stats.retryable} awaiting retry
          </Badge>
        )}
      </div>

      {note && <p className="text-sm text-muted-foreground">{note}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Sent</TableHead>
                <TableHead>Template</TableHead>
                <TableHead>Channel</TableHead>
                <TableHead>Recipient</TableHead>
                <TableHead>Message</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-end">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((n) => (
                <TableRow key={n.id}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {n.created_at.slice(0, 16).replace("T", " ")}
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{n.template_key}</TableCell>
                  <TableCell>
                    {n.channel}
                    {n.language !== "en" && (
                      <span className="ms-1 text-xs text-muted-foreground">{n.language}</span>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{n.recipient ?? "—"}</TableCell>
                  <TableCell className="max-w-sm truncate text-muted-foreground">
                    {n.rendered_text ?? n.error ?? "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(n.status)}>{n.status}</Badge>
                    {n.attempt_count > 1 && (
                      <span className="ms-1 text-xs text-muted-foreground">
                        ×{n.attempt_count}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" onClick={() => setSelected(n)}>
                      Inspect
                    </Button>
                    {(n.status === "failed" || n.status === "dead") && (
                      <Button size="sm" onClick={() => retryOne(n.id)}>
                        Retry
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {page && page.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    No notifications match.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {selected && (
        <NotificationDetailCard
          notification={selected}
          onRetry={() => retryOne(selected.id)}
          onClose={() => setSelected(null)}
        />
      )}

      <footer className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {page ? `${page.total} notification${page.total === 1 ? "" : "s"}` : "Loading…"}
        </span>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </Button>
          <span>
            {Math.floor(offset / PAGE_SIZE) + 1} / {totalPages}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={!page || offset + PAGE_SIZE >= page.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      </footer>

      <TemplateCatalog templates={templates} />
    </main>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "warn" | "bad";
}) {
  return (
    <Card>
      <CardContent className="py-4">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p
          className={
            tone === "bad"
              ? "text-2xl font-semibold text-destructive"
              : "text-2xl font-semibold"
          }
        >
          {value}
        </p>
      </CardContent>
    </Card>
  );
}

function Select({
  value,
  onChange,
  options,
  allLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  allLabel: string;
}) {
  return (
    <select
      className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o === "" ? allLabel : o}
        </option>
      ))}
    </select>
  );
}

function NotificationDetailCard({
  notification: n,
  onRetry,
  onClose,
}: {
  notification: Notification;
  onRetry: () => void;
  onClose: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-3">
          {n.template_key}
          <Badge variant={statusVariant(n.status)}>{n.status}</Badge>
          <Badge variant="outline">{n.channel}</Badge>
        </CardTitle>
        <CardDescription>
          Triggered by <span className="font-mono">{n.event_name}</span> · attempt{" "}
          {n.attempt_count}
          {n.provider && ` · via ${n.provider}`}
          {n.provider_reference && ` · ref ${n.provider_reference}`}
          {n.next_attempt_at && ` · next retry ${n.next_attempt_at.slice(0, 16).replace("T", " ")}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <div>
          <Label>Recipient</Label>
          <p className="font-mono">{n.recipient ?? "unresolved"}</p>
        </div>
        <div>
          <Label>Rendered message</Label>
          {n.title && <p className="font-medium">{n.title}</p>}
          <p className="whitespace-pre-wrap text-muted-foreground">{n.rendered_text ?? "—"}</p>
        </div>
        {n.error && (
          <div>
            <Label>Last error</Label>
            <p className="text-destructive">{n.error}</p>
          </div>
        )}
        <div>
          <Label>Event payload</Label>
          <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs">
            {JSON.stringify(n.payload, null, 2)}
          </pre>
        </div>
        <div className="flex gap-2">
          {(n.status === "failed" || n.status === "dead") && (
            <Button size="sm" onClick={onRetry}>
              Retry now
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TemplateCatalog({ templates }: { templates: NotificationTemplate[] }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<NotificationTemplate | null>(null);
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<RenderedPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  function choose(t: NotificationTemplate) {
    setSelected(t);
    setPreview(null);
    setError(null);
    // Seed each placeholder with its own name so a preview always renders.
    setVariables(Object.fromEntries(t.variables.map((v) => [v, v.toUpperCase()])));
  }

  async function render() {
    if (!selected) return;
    try {
      setPreview(
        await previewNotificationTemplate(selected.key, {
          channel: selected.channel,
          language: selected.language,
          variables,
        }),
      );
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Preview failed");
    }
  }

  if (!open) {
    return (
      <Button variant="ghost" className="self-start" onClick={() => setOpen(true)}>
        Show template catalog ({templates.length})
      </Button>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Template catalog</CardTitle>
        <CardDescription>
          Every message the platform can send. Nothing is hardcoded — preview any template with
          your own values.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Key</TableHead>
              <TableHead>Channel</TableHead>
              <TableHead>Language</TableHead>
              <TableHead>Variables</TableHead>
              <TableHead className="text-end">Preview</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {templates.map((t) => (
              <TableRow key={`${t.key}-${t.channel}-${t.language}`}>
                <TableCell>{t.key}</TableCell>
                <TableCell>{t.channel}</TableCell>
                <TableCell>{t.language}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {t.variables.join(", ") || "none"}
                </TableCell>
                <TableCell className="text-end">
                  <Button size="sm" variant="outline" onClick={() => choose(t)}>
                    Preview
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {selected && (
          <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
            <p className="font-medium">
              {selected.key} · {selected.channel} · {selected.language}
            </p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              {selected.variables.map((v) => (
                <div key={v} className="flex flex-col gap-1">
                  <Label htmlFor={`var-${v}`}>{v}</Label>
                  <Input
                    id={`var-${v}`}
                    value={variables[v] ?? ""}
                    onChange={(e) => setVariables({ ...variables, [v]: e.target.value })}
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={render}>
                Render
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>
                Close
              </Button>
            </div>
            {error && <p className="text-destructive">{error}</p>}
            {preview && (
              <div className="rounded-lg bg-muted p-3">
                <p className="font-medium">{preview.title}</p>
                <p className="whitespace-pre-wrap text-muted-foreground">{preview.body}</p>
              </div>
            )}
          </div>
        )}

        <Button variant="ghost" className="self-start" onClick={() => setOpen(false)}>
          Hide catalog
        </Button>
      </CardContent>
    </Card>
  );
}
