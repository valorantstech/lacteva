"use client";

/**
 * A password input with a way to see what was typed (WO-103).
 *
 * Retyping a password on a phone keyboard is where people fail, and a field
 * that hides every character while asking you to type it twice doubles the
 * chance. The toggle is a real button with a real name, so it is reachable
 * from a keyboard and read out by a screen reader; `aria-pressed` says which
 * state it is in.
 */

import { useState } from "react";
import { Input } from "@/components/ui/input";

export function PasswordField({
  id,
  value,
  onChange,
  autoComplete = "new-password",
  minLength,
  required = true,
  "aria-invalid": ariaInvalid,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete?: string;
  minLength?: number;
  required?: boolean;
  "aria-invalid"?: boolean;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div className="flex items-stretch gap-2">
      <Input
        id={id}
        type={shown ? "text" : "password"}
        required={required}
        minLength={minLength}
        autoComplete={autoComplete}
        value={value}
        aria-invalid={ariaInvalid || undefined}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-0 flex-1"
      />
      <button
        type="button"
        aria-pressed={shown}
        aria-controls={id}
        onClick={() => setShown((s) => !s)}
        className="shrink-0 rounded-md border border-input px-3 text-xs text-muted-foreground hover:text-foreground"
      >
        {shown ? "Hide" : "Show"}
      </button>
    </div>
  );
}
