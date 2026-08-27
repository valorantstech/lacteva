import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * One select for the whole portal (LACTEVA-ADMIN-008).
 *
 * Fifty native `<select>`s carried six different class strings between them,
 * and the differences were not decisions — they were the order the pages were
 * written in. Two heights, two radii, two border tokens, two background
 * tokens and two paddings, distributed across the tree by accident.
 *
 * The background was the one that actually showed. `--background` is a warm
 * off-white and `--card` is pure white, so forty-three of these rendered a
 * faintly grey panel inside a white card — beside an `Input`, which uses
 * `bg-transparent` and therefore did not. In dark mode the same mismatch is
 * wider (0.165 against 0.215) and reads as a hole. So the shared control takes
 * the tokens `Input` already took: same border, same background, same focus
 * ring, same disabled treatment. A select and a text input in one filter row
 * are the same kind of thing and should stop arguing about it.
 *
 * It stays a REAL `<select>` with real `<option>`s — no popover, no portal, no
 * headless dependency. The native listbox is what works on a handset, what
 * works with a screen reader, and what already works here; the defect was
 * never the element.
 */
const selectVariants = cva(
  // Everything that is not a width or a height, settled once. The native
  // chevron is deliberately kept — `appearance-none` would trade a working
  // affordance for a hand-drawn one.
  "border border-input bg-transparent text-sm transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:bg-input/30 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
  {
    variants: {
      /**
       * The two sizes that were really in the tree: the compact filter bar and
       * everything else. Radius travels with height, as it does on `Button`.
       */
      size: {
        default: "h-9 rounded-md px-2.5",
        sm: "h-8 rounded-lg px-2.5",
      },
      /**
       * Width is a prop because it was a class string on six sites and an
       * accident on the rest. Anything narrower than these two — a `max-w-*`
       * chosen for reading — is still a caller's `className`.
       */
      width: {
        auto: "",
        full: "w-full",
      },
    },
    defaultVariants: { size: "default", width: "auto" },
  },
);

/**
 * `size` shadows the native attribute (the number of visible rows), which no
 * site in this portal uses. Omitting it is what makes `size="sm"` mean what a
 * reader of `Button` would expect it to mean.
 */
type SelectProps = Omit<React.ComponentProps<"select">, "size"> &
  VariantProps<typeof selectVariants>;

function Select({ className, size, width, ...props }: SelectProps) {
  return (
    <select
      data-slot="select"
      className={cn(selectVariants({ size, width }), className)}
      {...props}
    />
  );
}

export { Select, selectVariants };
