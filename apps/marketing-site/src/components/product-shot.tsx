import { existsSync } from "node:fs";
import { join } from "node:path";
import Image from "next/image";
import { ScreenshotFrame } from "@/components/screenshot-frame";

/**
 * A real product screenshot by name, or an honest placeholder until the
 * capture exists. Drop `public/screenshots/<name>.png` in and rebuild —
 * no code change. The existence check runs at build time (pages are
 * static), which is exactly when it needs to be true.
 *
 * Screenshots must come from the demo environment with synthetic data
 * only — never customer data, never fabricated UI.
 */
export function ProductShot({
  name,
  label,
  width = 1600,
  height = 940,
  priority = false,
  className,
}: {
  name: string;
  label: string;
  width?: number;
  height?: number;
  priority?: boolean;
  className?: string;
}) {
  const file = join(process.cwd(), "public", "screenshots", `${name}.png`);
  if (!existsSync(file)) {
    return <ScreenshotFrame label={label} placeholder className={className} />;
  }
  return (
    <ScreenshotFrame label={label} className={className}>
      <Image
        src={`/screenshots/${name}.png`}
        alt={label}
        width={width}
        height={height}
        priority={priority}
        className="w-full"
      />
    </ScreenshotFrame>
  );
}
