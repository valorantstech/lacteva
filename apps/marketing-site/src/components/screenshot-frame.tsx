import { cn } from "@/lib/utils";

/**
 * The one sanctioned way to show product UI on the site.
 *
 * Real screenshots (demo/synthetic data only — never customer data) go in
 * as children, typically a next/image. Until a screen has been captured,
 * `placeholder` renders a state that is unmistakably a placeholder: the
 * site must never fabricate UI or imply functionality that does not exist,
 * so the placeholder deliberately looks like scaffolding, not a mock.
 */
export function ScreenshotFrame({
  children,
  label,
  placeholder = false,
  className,
}: {
  children?: React.ReactNode;
  /** What the screenshot shows, e.g. "Daily delivery report". */
  label: string;
  placeholder?: boolean;
  className?: string;
}) {
  return (
    <figure
      className={cn(
        "overflow-hidden rounded-xl border border-border bg-card shadow-sm",
        className,
      )}
    >
      <div
        aria-hidden
        className="flex items-center gap-1.5 border-b border-border bg-muted px-4 py-2.5"
      >
        <span className="size-2.5 rounded-full bg-border" />
        <span className="size-2.5 rounded-full bg-border" />
        <span className="size-2.5 rounded-full bg-border" />
        <span className="ms-3 hidden h-5 flex-1 rounded-md bg-background sm:block" />
      </div>
      {placeholder ? (
        <div className="flex aspect-[16/10] flex-col items-center justify-center gap-2 border-2 border-dashed border-border/80 bg-secondary/30 p-8 text-center">
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
      <figcaption className="sr-only">{label}</figcaption>
    </figure>
  );
}
