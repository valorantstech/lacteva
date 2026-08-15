import { cn } from "@/lib/utils";

/**
 * Interim Lacteva mark: a milk drop in a rounded field, drawn inline so the
 * page ships no binary asset. No logo exists anywhere in the workspace
 * (Shared/Logos is empty) — when Marketing/Logo delivers the real mark, this
 * component is the single place to swap it.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden="true"
      className={cn("size-8", className)}
    >
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <path
        d="M16 6.5c3.6 4.9 6.5 8.6 6.5 12.4a6.5 6.5 0 1 1-13 0c0-3.8 2.9-7.5 6.5-12.4Z"
        className="fill-primary-foreground"
      />
      <path
        d="M12.4 19.2a3.6 3.6 0 0 0 3.3 3.8"
        fill="none"
        strokeWidth="1.6"
        strokeLinecap="round"
        className="stroke-primary"
      />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    // Text color inherits, so a dark band recolors the wordmark by setting
    // its own text class; `text-foreground` here is only the default.
    <span
      className={cn("flex items-center gap-2.5 text-foreground", className)}
    >
      <LogoMark />
      <span className="text-lg font-semibold tracking-tight">Lacteva</span>
    </span>
  );
}
