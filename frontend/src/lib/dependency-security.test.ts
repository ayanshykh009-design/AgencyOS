import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

interface Manifest {
  dependencies: Record<string, string>;
  devDependencies: Record<string, string>;
  overrides: Record<string, string>;
}

interface Lockfile {
  packages: Record<string, { version?: string }>;
}

const manifest = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "package.json"), "utf8")
) as Manifest;
const lockfile = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "package-lock.json"), "utf8")
) as Lockfile;

describe("dependency security baseline", () => {
  it("keeps Next.js and its ESLint config on the audited versions", () => {
    expect(manifest.dependencies.next).toBe("16.4.6");
    expect(manifest.devDependencies["eslint-config-next"]).toBe("16.4.0");
  });

  it("pins patched Vitest and Vite versions for applicable GHSA advisories", () => {
    expect(manifest.devDependencies.vitest).toBe("4.1.12");
    expect(manifest.overrides.vite).toBe("8.2.4");
    expect(lockfile.packages["node_modules/vitest"]?.version).toBe("4.1.12");
    expect(lockfile.packages["node_modules/@vitest/mocker"]?.version).toBe("4.1.12");
    expect(lockfile.packages["node_modules/vite"]?.version).toBe("8.2.4");
  });
});
