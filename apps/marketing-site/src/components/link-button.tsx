import Link from "next/link";
import type { VariantProps } from "class-variance-authority";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * A link that looks like a button. This design system is Base UI, so there
 * is no slot-style prop to graft an anchor into <Button> — the house idiom
 * (admin portal, centers page) is an anchor carrying button classes. This
 * component is that idiom in one place instead of copy-pasted class
 * strings; `variant="onInk"` inverts for dark bands.
 */
type LinkButtonProps = React.ComponentProps<typeof Link> &
  Omit<VariantProps<typeof buttonVariants>, "variant"> & { variant?: Variant };

type Variant =
  | "default"
  | "outline"
  | "secondary"
  | "ghost"
  | "link"
  | "onInk";

export function LinkButton({
  className,
  variant = "default",
  size = "xl",
  ...props
}: LinkButtonProps) {
  return (
    // Every CTA lifts 2px on hover — the DS lacteva-lift rule
    // (LACTEVA-MARKETING-004), defined once in globals.css.
    <Link
      data-slot="link-button"
      className={cn(
        variant === "onInk"
          ? cn(
              buttonVariants({ variant: "default", size }),
              "bg-ink-foreground text-ink hover:bg-ink-foreground/90",
            )
          : buttonVariants({ variant, size }),
        "lacteva-lift",
        className,
      )}
      {...props}
    />
  );
}
