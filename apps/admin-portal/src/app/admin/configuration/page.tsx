"use client";

import { useState } from "react";
import { AdminPage } from "@/components/admin-page";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {getConfig, setConfig,
  describeError,
} from "@/lib/api";

/**
 * Tenant configuration (PORTAL-001 / F-10).
 *
 * Key-by-key rather than a browsable list, because the platform's contract is
 * `GET /v1/config/{key}` — there is no enumeration endpoint, and inventing one
 * is backend work this order excludes. Values are JSON: the API stores
 * arbitrary JSON, so a text box that silently coerced everything to a string
 * would write the wrong type into a live setting.
 */
export default function ConfigurationPage() {
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [scope, setScope] = useState<"tenant" | "global">("tenant");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function load() {
    setError(null);
    setNote(null);
    try {
      const result = await getConfig(key);
      setValue(JSON.stringify(result.value, null, 2));
      setNote(`Loaded ${key}.`);
    } catch (err) {
      setError(
        describeError(err, "Failed to read the setting"),
      );
    }
  }

  async function save() {
    setError(null);
    setNote(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(value);
    } catch {
      setError(
        'The value is not valid JSON. Use "text" for a string, 12 for a number.',
      );
      return;
    }
    try {
      await setConfig(key, parsed, scope);
      setNote(`Saved ${key} at ${scope} scope.`);
    } catch (err) {
      setError(
        describeError(err, "The platform refused the change"),
      );
    }
  }

  return (
    <AdminPage
      title="Configuration"
      description="Read and write a platform setting by key. Values are JSON, and the scope decides who sees the change."
      error={error}
      note={note}
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="key">Key</Label>
          <Input
            id="key"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="platform.consumers.notification-dispatch.enabled"
            className="min-w-80"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="scope">Scope</Label>
          <Select
            id="scope"
            value={scope}
            onChange={(e) => setScope(e.target.value as "tenant" | "global")}
          >
            <option value="tenant">tenant</option>
            <option value="global">global</option>
          </Select>
        </div>
        <Button variant="secondary" disabled={!key} onClick={() => void load()}>
          Load
        </Button>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="value">Value (JSON)</Label>
        <textarea
          id="value"
          rows={8}
          className="rounded-md border border-input bg-transparent p-3 font-mono text-sm"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      </div>
      <div>
        <Button disabled={!key || !value} onClick={() => void save()}>
          Save
        </Button>
      </div>
    </AdminPage>
  );
}
