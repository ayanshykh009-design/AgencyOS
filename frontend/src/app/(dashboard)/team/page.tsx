// Team: invite members, manage roles, and revoke pending invites.
"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Field, Input, Modal, PageHeader, Select, Spinner } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { can } from "@/lib/permissions";
import { createInvite, listInvites, revokeInvite } from "@/services/teams";
import { listUsers, updateUser } from "@/services/users";
import type { Page, TeamInvite, TeamInviteCreateInput, User, UserRole } from "@/types";

const ROLES: Array<{ value: UserRole; label: string }> = [
  { value: "owner", label: "Owner" },
  { value: "admin", label: "Admin" },
  { value: "manager", label: "Manager" },
  { value: "member", label: "Member" },
  { value: "sales_agent", label: "Sales agent" },
  { value: "viewer", label: "Viewer" },
];

function statusTone(status: TeamInvite["status"]): "green" | "gray" | "red" | "amber" {
  switch (status) {
    case "accepted":
      return "green";
    case "pending":
      return "amber";
    case "revoked":
    case "expired":
      return "red";
    default:
      return "gray";
  }
}

export default function TeamPage() {
  const session = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [invites, setInvites] = useState<TeamInvite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<UserRole>("member");
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([listUsers(100), listInvites(100)])
      .then(([userPage, invitePage]) => {
        setUsers(userPage.items);
        setInvites(invitePage.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load team");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!session) return null;
  if (!can(session.user.role, "invite_manage")) {
    return (
      <p className="text-red-600">
        You do not have permission to manage the team. Contact an administrator.
      </p>
    );
  }

  async function handleCreateInvite() {
    if (email.trim() === "") return;
    setBusy(true);
    setError(null);
    const input: TeamInviteCreateInput = {
      email: email.trim(),
      full_name: fullName.trim() || undefined,
      role,
    };
    try {
      const created = await createInvite(input);
      setInviteUrl(created.invite_url);
      setEmail("");
      setFullName("");
      setRole("member");
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to create invite");
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(invite: TeamInvite) {
    setBusy(true);
    setError(null);
    try {
      await revokeInvite(invite.id);
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to revoke invite");
    } finally {
      setBusy(false);
    }
  }

  async function handleRoleChange(user: User, next: UserRole) {
    setBusy(true);
    setError(null);
    try {
      await updateUser(user.id, { role: next });
      setUsers((prev) =>
        prev.map((item) => (item.id === user.id ? { ...item, role: next } : item))
      );
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to update role");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleActive(user: User) {
    setBusy(true);
    setError(null);
    try {
      await updateUser(user.id, { is_active: !user.is_active });
      setUsers((prev) =>
        prev.map((item) => (item.id === user.id ? { ...item, is_active: !item.is_active } : item))
      );
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to update member");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Team"
        description={`${users.length} members`}
        actions={
          <Button onClick={() => setInviteOpen(true)} disabled={busy}>
            Invite member
          </Button>
        }
      />

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">Members</h3>
        {loading ? (
          <Spinner label="Loading team…" />
        ) : users.length === 0 ? (
          <p className="text-sm text-gray-500">No members yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="border-b bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Email</th>
                  <th className="px-4 py-2 font-medium">Role</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {users.map((user) => (
                  <tr key={user.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 align-middle text-gray-800">
                      {user.full_name || "—"}
                    </td>
                    <td className="px-4 py-3 align-middle text-gray-600">{user.email}</td>
                    <td className="px-4 py-3 align-middle">
                      <Select
                        value={user.role}
                        disabled={busy || user.role === "owner"}
                        onChange={(e) => handleRoleChange(user, e.target.value as UserRole)}
                        className="w-40"
                      >
                        {ROLES.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </Select>
                    </td>
                    <td className="px-4 py-3 align-middle">
                      <Badge tone={user.is_active ? "green" : "red"}>
                        {user.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 align-middle">
                      {user.role !== "owner" ? (
                        <Button
                          variant="ghost"
                          disabled={busy}
                          onClick={() => handleToggleActive(user)}
                        >
                          {user.is_active ? "Deactivate" : "Activate"}
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">Pending invites</h3>
        {loading ? (
          <Spinner label="Loading invites…" />
        ) : invites.filter((invite) => invite.status === "pending").length === 0 ? (
          <p className="text-sm text-gray-500">No pending invites.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {invites
              .filter((invite) => invite.status === "pending")
              .map((invite) => (
                <li
                  key={invite.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-white p-3 text-sm"
                >
                  <div className="flex flex-col">
                    <span>
                      {invite.full_name || invite.email}
                      {invite.full_name ? (
                        <span className="text-gray-500"> · {invite.email}</span>
                      ) : null}
                    </span>
                    <span className="flex items-center gap-2 text-xs text-gray-400">
                      <Badge tone="amber">{invite.status}</Badge>
                      <Badge tone="gray">{invite.role}</Badge>
                    </span>
                  </div>
                  <Button variant="ghost" disabled={busy} onClick={() => handleRevoke(invite)}>
                    Revoke
                  </Button>
                </li>
              ))}
          </ul>
        )}
      </section>

      <Modal
        open={inviteOpen}
        title="Invite member"
        width="sm"
        onClose={() => setInviteOpen(false)}
      >
        <div className="flex flex-col gap-4">
          <Field label="Email" required>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Full name">
            <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </Field>
          <Field label="Role">
            <Select value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
              {ROLES.filter((option) => option.value !== "owner").map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          {inviteUrl ? (
            <div className="flex flex-col gap-1 rounded-lg border border-gray-200 bg-gray-50 p-3">
              <p className="text-xs text-gray-500">Invitation link (valid 7 days):</p>
              <code className="break-all text-xs text-gray-800">{inviteUrl}</code>
            </div>
          ) : null}
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setInviteOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={handleCreateInvite} disabled={busy || email.trim() === ""}>
              {busy ? "Sending…" : inviteUrl ? "Send another" : "Send invite"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
