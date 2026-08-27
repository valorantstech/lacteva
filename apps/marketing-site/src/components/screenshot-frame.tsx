import { cn } from "@/lib/utils";

/**
 * The one sanctioned way to show product UI on the site.
 *
 * Real screenshots (demo/synthetic data only — never customer data) go in
 * as children, typically a next/image. Until a screen has been captured,
 * `placeholder` renders a state that is unmistakably a placeholder: the
 * site must never fabricate UI or imply functionality that does not exist,
 * so the placeholder deliberately looks like scaffolding, not a mock.
 *
 * Two chromes (LACTEVA-MARKETING-006): `browser` for the portal,
 * `device` for handset captures. A real capture gets a VISIBLE caption —
 * the shots come from a real running dairy, and saying what a screen is
 * (not how big the dairy behind it is) is the honest frame.
 */
export function ScreenshotFrame({
  children,
  label,
  placeholder = false,
  variant = "browser",
  className,
}: {
  children?: React.ReactNode;
  /** What the screenshot shows, e.g. "Daily delivery report". */
  label: string;
  placeholder?: boolean;
  variant?: "browser" | "device";
  className?: string;
}) {
  return (
    <figure
      className={cn(
        "overflow-hidden border border-border bg-card shadow-sm",
        variant === "device" ? "rounded-3xl" : "rounded-xl",
        className,
      )}
    >
      {variant === "browser" ? (
        <div
          aria-hidden
          className="flex items-center gap-1.5 border-b border-border bg-muted px-4 py-2.5"
        >
          <span className="size-2.5 rounded-full bg-border" />
          <span className="size-2.5 rounded-full bg-border" />
          <span className="size-2.5 rounded-full bg-border" />
          <span className="ms-3 hidden h-5 flex-1 rounded-md bg-background sm:block" />
        </div>
      ) : (
        <div
          aria-hidden
          className="flex items-center justify-center border-b border-border bg-muted py-2"
        >
          <span className="h-1.5 w-14 rounded-full bg-border" />
        </div>
      )}
      {placeholder ? (
        <div
          className={cn(
            "flex flex-col items-center justify-center gap-2 border-2 border-dashed border-border/80 bg-secondary/30 p-8 text-center",
            variant === "device" ? "aspect-[3/4]" : "aspect-[16/10]",
          )}
        >
          <p className="text-sm font-medium text-muted-foreground">
            Product screenshot: {label}
          </p>
          <p className="text-xs text-muted-foreground/70">
            Placeholder — to be replaced with a capture from the live demo
            environment.
          </p>
        </div>
      ) : (
        children
      )}
      {placeholder ? (
        <figcaption className="sr-only">{label}</figcaption>
      ) : (
        <figcaption className="border-t border-border bg-muted px-4 py-2.5 text-center text-xs text-muted-foreground">
          {label}
        </figcaption>
      )}
    </figure>
  );
}
