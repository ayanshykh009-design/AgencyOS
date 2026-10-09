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
import type { UserRole } from "@/types";

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

// role-set parity: F-4 previously only compared permission KEYS, which let
// `workflow_manage` drift (BE `_MANAGE` vs FE `_ADMIN_ONLY`). The matrix
// VALUES must match the backend PERMISSION_MATRIX exactly.
function backendRoleSets(): Map<string, string[]> {
  const path = resolve(__dirname, "../../../../backend/app/core/permissions.py");
  const text = readFileSync(path, "utf-8");

  // enum member -> string value (e.g. WORKFLOW_MANAGE -> workflow_manage)
  const memberToValue = new Map<string, string>();
  const enumStart = text.indexOf("class Permission(StrEnum):");
  const enumBlock = enumStart === -1 ? "" : text.slice(enumStart).split(/\n(?=[A-Za-z])/)[0];
  let em: RegExpExecArray | null;
  const memberRe = /^\s*([A-Z][A-Z0-9_]+)\s*=\s*"([a-z0-9_]+)"/gm;
  while ((em = memberRe.exec(enumBlock)) !== null) {
    memberToValue.set(em[1], em[2]);
  }

  // named role groups: _READ = { UserRole.OWNER, ... } (single or multi-line)
  const groups = new Map<string, string[]>();
  let gm: RegExpExecArray | null;
  const groupRe = /^(_[A-Z_]+)\s*=\s*\{([^}]*)\}/gm;
  while ((gm = groupRe.exec(text)) !== null) {
    const roles: string[] = [];
    let rm: RegExpExecArray | null;
    const roleRe = /UserRole\.([A-Z_]+)/g;
    while ((rm = roleRe.exec(gm[2])) !== null) roles.push(rm[1].toLowerCase());
    groups.set(gm[1], roles);
  }

  // matrix: Permission.WORKFLOW_MANAGE: _MANAGE,
  const matrix = new Map<string, string[]>();
  let mm: RegExpExecArray | null;
  const matrixRe = /Permission\.([A-Z0-9_]+):\s*(_[A-Z_]+)/g;
  while ((mm = matrixRe.exec(text)) !== null) {
    const value = memberToValue.get(mm[1]);
    if (value) matrix.set(value, groups.get(mm[2]) ?? []);
  }
  return matrix;
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

  it("matches the backend role sets exactly (no FE/BE drift)", () => {
    const backendMatrix = backendRoleSets();
    expect(backendMatrix.size).toBeGreaterThan(20);
    const mismatches: string[] = [];
    for (const [key, backendRoles] of backendMatrix) {
      const feRoles = PERMISSION_MATRIX[key as PermissionKey];
      if (!feRoles) {
        mismatches.push(`${key}: missing in FE matrix`);
        continue;
      }
      const be = new Set(backendRoles as UserRole[]);
      const fe = new Set(feRoles);
      const diff = [...be].filter((r) => !fe.has(r));
      const extra = [...fe].filter((r) => !be.has(r));
      if (diff.length || extra.length) {
        mismatches.push(
          `${key}: backend=[${backendRoles.join(",")}] frontend=[${feRoles.join(",")}]`
        );
      }
    }
    expect(mismatches).toEqual([]);
  });
});
