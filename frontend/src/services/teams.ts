// Teams service: invites, revoke, and accept (public acceptance flow).
import { apiFetch } from "@/lib/api-client";
import type { Page, TeamInvite, TeamInviteCreateInput, TeamInviteCreateResponse } from "@/types";

export async function createInvite(
  input: TeamInviteCreateInput
): Promise<TeamInviteCreateResponse> {
  return apiFetch<TeamInviteCreateResponse>("/teams", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function listInvites(limit = 100, offset = 0): Promise<Page<TeamInvite>> {
  return apiFetch<Page<TeamInvite>>(`/teams?limit=${limit}&offset=${offset}`);
}

export async function revokeInvite(inviteId: string): Promise<TeamInvite> {
  return apiFetch<TeamInvite>(`/teams/${inviteId}/revoke`, { method: "POST" });
}

export interface InviteLookup {
  email: string;
  full_name: string | null;
  role: string;
  organization_name: string | null;
}

export async function lookupInvite(token: string): Promise<InviteLookup> {
  return apiFetch<InviteLookup>(`/teams/public/${encodeURIComponent(token)}`, {
    auth: false,
  });
}

export async function acceptInvite(input: {
  token: string;
  full_name: string;
  password: string;
}): Promise<TeamInvite> {
  return apiFetch<TeamInvite>("/teams/accept", {
    auth: false,
    method: "POST",
    body: JSON.stringify(input),
  });
}
