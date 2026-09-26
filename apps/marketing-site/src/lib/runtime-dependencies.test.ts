/**
 * Every package the app imports at runtime is a `dependency`, not a
 * `devDependency` (WO-106 · LACTEVA-BUILD-002). The API's production image
 * could not import a module because its package lived in the dev group; the
 * same class of gap here would be a package `next build` bundles today and a
 * future `serverExternalPackages` entry forgets. So: everything imported
 * outside tests resolves to `dependencies`, Node's own modules, or the two
 * marker packages Next ships (`server-only`, `client-only`).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { builtinModules } from "node:module";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..", "..");
const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8")) as {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
};
const RUNTIME = new Set(Object.keys(pkg.dependencies ?? {}));
const DEV = new Set(Object.keys(pkg.devDependencies ?? {}));
const PROVIDED_BY_NEXT = new Set(["server-only", "client-only"]);
const BUILTIN = new Set(builtinModules.flatMap((m) => [m, `node:${m}`]));

function* sources(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) yield* sources(path);
    else if (/\.(ts|tsx)$/.test(entry) && !/\.test\.(ts|tsx)$/.test(entry) && !path.includes("/test/"))
      yield path;
  }
}

function packageOf(specifier: string): string | null {
  if (specifier.startsWith(".") || specifier.startsWith("@/") || specifier.startsWith("/")) return null;
  const parts = specifier.split("/");
  return specifier.startsWith("@") ? `${parts[0]}/${parts[1]}` : parts[0];
}

describe("runtime imports", () => {
  it("are all declared under dependencies", () => {
    const offenders: string[] = [];
    for (const file of sources(join(ROOT, "src"))) {
      const text = readFileSync(file, "utf8");
      // Import statements only — never the word "from" inside prose or JSX:
      // `import x from "y"`, a multi-line `} from "y"`, `import "y"`, and a
      // dynamic `import("y")`.
      const specifiers = [
        ...text.matchAll(/^[ \t]*(?:import\b[^;"']*|\}[ \t]*)from[ \t]+["']([^"']+)["']/gm),
        ...text.matchAll(/^[ \t]*import[ \t]+["']([^"']+)["']/gm),
        ...text.matchAll(/\bimport\([ \t]*["']([^"']+)["'][ \t]*\)/g),
      ];
      for (const match of specifiers) {
        const name = packageOf(match[1]);
        if (!name || BUILTIN.has(match[1]) || BUILTIN.has(name) || PROVIDED_BY_NEXT.has(name)) continue;
        if (!RUNTIME.has(name)) {
          offenders.push(
            `${relative(ROOT, file)} imports ${name} — ${DEV.has(name) ? "a devDependency" : "undeclared"}`,
          );
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("is actually reading the sources", () => {
    expect([...sources(join(ROOT, "src"))].length).toBeGreaterThan(20);
    expect(RUNTIME.has("next") && RUNTIME.has("react")).toBe(true);
  });
});
