// Assignment: configure auto-assignment rules and sweep unassigned leads.
"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { can } from "@/lib/permissions";
import {
  assignUnassignedLeads,
  getAssignmentRule,
  upsertAssignmentRule,
} from "@/services/assignment";
import { listUsers } from "@/services/users";
import type { AssignmentRule, AssignmentStrategy, User } from "@/types";

const STRATEGIES: Array<{ value: AssignmentStrategy; label: string }> = [
  { value: "manual", label: "Manual" },
  { value: "round_robin", label: "Round robin" },
  { value: "rules", label: "Rules" },
];

export default function AssignmentPage() {
  const session = useAuth();
  const [rule, setRule] = useState<AssignmentRule | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [strategy, setStrategy] = useState<AssignmentStrategy>("round_robin");
  const [enabled, setEnabled] = useState(true);
  const [targetIds, setTargetIds] = useState<string[]>([]);
  const [lastResult, setLastResult] = useState<number | null>(null);

  const load = useCallback(() => {
    Promise.all([getAssignmentRule(), listUsers(100)])
      .then(([current, userPage]) => {
        setRule(current);
        setUsers(userPage.items);
        if (current) {
          setName(current.name);
          setStrategy(current.strategy);
          setEnabled(current.enabled);
          setTargetIds(current.target_user_ids);
        }
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load assignment config");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!session) return null;
  if (!can(session.user.role, "lead_assign")) {
    return (
      <p className="text-red-600">
        You do not have permission to manage lead assignment. Contact an administrator.
      </p>
    );
  }

  function toggleTarget(userId: string) {
    setTargetIds((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]
    );
  }

  async function handleSave() {
    if (name.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      const saved = await upsertAssignmentRule({
        name: name.trim(),
        strategy,
        enabled,
        target_user_ids: targetIds,
      });
      setRule(saved);
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to save rule");
    } finally {
      setBusy(false);
    }
  }

  async function handleSweep() {
    setBusy(true);
    setError(null);
    try {
      const result = await assignUnassignedLeads();
      setLastResult(result.assigned);
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to assign leads");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <Spinner label="Loading assignment config…" />;
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Lead assignment"
        description="Configure how new unassigned leads are routed to team members."
        actions={
          <Button variant="outline" onClick={handleSweep} disabled={busy}>
            {busy ? "Assigning…" : "Assign unassigned leads"}
          </Button>
        }
      />

      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {lastResult !== null ? (
        <p className="text-sm text-green-700">{lastResult} lead(s) assigned.</p>
      ) : null}

      <div className="flex flex-col gap-4 rounded-lg border bg-white p-5">
        <Field label="Rule name" required>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Default assignment"
          />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Strategy">
            <Select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as AssignmentStrategy)}
            >
              {STRATEGIES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Enabled">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              {enabled ? "Rule is active" : "Rule is paused"}
            </label>
          </Field>
        </div>

        <Field label="Target assignees">
          <div className="flex flex-col gap-1">
            {users.length === 0 ? (
              <p className="text-sm text-gray-500">No members available.</p>
            ) : (
              users.map((user) => (
                <label key={user.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={targetIds.includes(user.id)}
                    onChange={() => toggleTarget(user.id)}
                  />
                  {user.full_name || user.email}
                </label>
              ))
            )}
          </div>
        </Field>

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={busy || name.trim() === ""}>
            {busy ? "Saving…" : "Save rule"}
          </Button>
        </div>
      </div>

      {rule ? (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Badge tone={rule.enabled ? "green" : "red"}>{rule.enabled ? "Active" : "Paused"}</Badge>
          <span>
            {rule.strategy} · {rule.target_user_ids.length} assignee(s) · index{" "}
            {rule.last_assigned_index}
          </span>
        </div>
      ) : null}
    </div>
  );
}
