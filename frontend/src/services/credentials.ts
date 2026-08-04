// Credentials service: CRUD for encrypted integration credentials.
// The backend never returns the encrypted value — only a preview.
import { apiFetch } from "@/lib/api-client";
import type {
  Credential,
  CredentialCreateInput,
  CredentialUpdateInput,
  CredentialType,
  Page,
} from "@/types";

export interface CredentialQuery {
  credentialType?: CredentialType;
  limit?: number;
  offset?: number;
}

export async function listCredentials(query: CredentialQuery = {}): Promise<Page<Credential>> {
  const params = new URLSearchParams();
  if (query.credentialType) params.set("credential_type", query.credentialType);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<Credential>>(`/credentials${qs ? `?${qs}` : ""}`);
}

export async function getCredential(credentialId: string): Promise<Credential> {
  return apiFetch<Credential>(`/credentials/${credentialId}`);
}

export async function createCredential(input: CredentialCreateInput): Promise<Credential> {
  return apiFetch<Credential>("/credentials", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateCredential(
  credentialId: string,
  patch: CredentialUpdateInput
): Promise<Credential> {
  return apiFetch<Credential>(`/credentials/${credentialId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteCredential(credentialId: string): Promise<void> {
  await apiFetch<void>(`/credentials/${credentialId}`, { method: "DELETE" });
}
