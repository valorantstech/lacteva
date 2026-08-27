import { existsSync } from "node:fs";
import { join } from "node:path";
import Image from "next/image";
import { ScreenshotFrame } from "@/components/screenshot-frame";

/**
 * A real product screenshot by name, or an honest placeholder until the
 * capture exists. Drop `public/screenshots/<name>.(png|jpg|webp)` in and
 * rebuild — no code change; names are organized by surface
 * (`portal/dashboard`, `mobile/operator-home`). The existence check runs
 * at build time (pages are static), which is exactly when it needs to be
 * true — and it is why re-shooting the dairy later (cycle 4's populated
 * demo dataset) is a pure image-file swap.
 *
 * Screenshots must come from the demo environment with synthetic data
 * only — never customer data, never fabricated UI.
 */
const EXTENSIONS = ["png", "jpg", "webp"] as const;

export function ProductShot({
  name,
  label,
  width = 1600,
  height = 940,
  variant = "browser",
  priority = false,
  className,
}: {
  name: string;
  label: string;
  width?: number;
  height?: number;
  variant?: "browser" | "device";
  priority?: boolean;
  className?: string;
}) {
  const extension = EXTENSIONS.find((candidate) =>
    existsSync(
      join(process.cwd(), "public", "screenshots", `${name}.${candidate}`),
    ),
  );
  if (!extension) {
    return (
      <ScreenshotFrame
        label={label}
        placeholder
        variant={variant}
        className={className}
      />
    );
  }
  return (
    <ScreenshotFrame label={label} variant={variant} className={className}>
      <Image
        src={`/screenshots/${name}.${extension}`}
        alt={label}
        width={width}
        height={height}
        priority={priority}
        className="w-full"
      />
    </ScreenshotFrame>
  );
}
