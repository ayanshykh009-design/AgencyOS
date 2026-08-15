// M10 finding F-4: the frontend permission mirror must expose every backend
// permission so UI affordances cannot silently drift from enforcement.
// This test reads the backend Permission enum and asserts the FE matrix +
// PermissionKey union cover it.
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";
import { PERMISSION_MATRIX } from "@/lib/permissions";
import type { PermissionKey } from "@/lib/permissions";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

function backendPermissionValues(): string[] {
  const path = resolve(__dirname, "../../../../backend/app/core/permissions.py");
  const text = readFileSync(path, "utf-8");
  const start = text.indexOf("class Permission(StrEnum):");
  const tail = start === -1 ? "" : text.slice(start);
  // Capture the whole class body: stop at the next top-level (non-indented)
  // line, so internal blank lines between enum members are tolerated.
  const block = tail.split(/\n(?=[A-Za-z])/)[0];
  const re = /^\s*([A-Z][A-Z0-9_]+)\s*=\s*"([a-z0-9_]+)"/gm;
  const values = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(block)) !== null) values.add(m[2]);
  return [...values];
}

describe("frontend/backend permission parity", () => {
  const backend = backendPermissionValues();

  it("discovers backend permission values", () => {
    expect(backend.length).toBeGreaterThan(20);
  });

  it("exposes every backend permission in the FE matrix", () => {
    const missing = backend.filter((k) => !(k in PERMISSION_MATRIX));
    expect(missing).toEqual([]);
  });

  it("exposes every backend permission as a PermissionKey", () => {
    const keys = Object.keys(PERMISSION_MATRIX) as PermissionKey[];
    const missing = backend.filter((k) => !keys.includes(k as PermissionKey));
    expect(missing).toEqual([]);
  });
});
