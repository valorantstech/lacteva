"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

const VOLUME_OPTIONS = [
  "Under 2,000 L/day",
  "2,000 – 20,000 L/day",
  "20,000 – 200,000 L/day",
  "Over 200,000 L/day",
] as const;

type Status = "idle" | "submitting" | "sent" | "error";

const inputClasses =
  "h-10 w-full rounded-lg border border-input bg-card px-3 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

export function DemoRequestForm() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string>("");

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("submitting");
    setError("");
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      const response = await fetch("/api/demo-request", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(data),
      });
      if (response.ok) {
        setStatus("sent");
        return;
      }
      const problem = (await response.json().catch(() => null)) as {
        detail?: string;
      } | null;
      setError(
        problem?.detail ??
          "We could not record your request right now. Please try again later.",
      );
      setStatus("error");
    } catch {
      setError(
        "We could not record your request right now. Please try again later.",
      );
      setStatus("error");
    }
  }

  if (status === "sent") {
    return (
      <div
        role="status"
        className="flex flex-col gap-2 rounded-xl border border-border bg-card p-8"
      >
        <h2 className="text-lg font-semibold">Request received</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Thank you — we will get back to you to arrange a live demonstration
          of the whole loop, collection to receipt.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-5 rounded-xl border border-border bg-card p-6 sm:p-8"
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Name
          <input name="name" required autoComplete="name" className={inputClasses} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Work email
          <input
            name="email"
            type="email"
            required
            autoComplete="email"
            className={inputClasses}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Organization
          <input name="organization" required autoComplete="organization" className={inputClasses} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Country
          <input name="country" required autoComplete="country-name" className={inputClasses} />
        </label>
      </div>
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Daily milk volume
        <select name="dailyVolume" defaultValue="" className={inputClasses}>
          <option value="" disabled>
            Select a range
          </option>
          {VOLUME_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Anything you want us to know
        <textarea
          name="message"
          rows={4}
          className="w-full rounded-lg border border-input bg-card px-3 py-2 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />
      </label>
      {status === "error" ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div>
        <Button type="submit" size="lg" disabled={status === "submitting"}>
          {status === "submitting" ? "Sending…" : "Request a demo"}
        </Button>
      </div>
    </form>
  );
}
