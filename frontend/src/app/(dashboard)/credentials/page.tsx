// Credentials: manage encrypted integration secrets.
// The backend only returns a preview of each value, never the secret.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TRow,
} from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { CREDENTIAL_TYPE_LABELS, formatDateTime } from "@/lib/format";
import { can } from "@/lib/permissions";
import { createCredential, deleteCredential, listCredentials } from "@/services/credentials";
import type { Credential, CredentialType } from "@/types";

export default function CredentialsPage() {
  const session = useAuth();
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Credential | null>(null);

  const [name, setName] = useState("");
  const [credentialType, setCredentialType] = useState<CredentialType>("n8n_api_key");
  const [encryptedValue, setEncryptedValue] = useState("");
  const [valuePreview, setValuePreview] = useState("");
  const [description, setDescription] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const load = useCallback(() => {
    listCredentials({ limit: 200 })
      .then((page) => {
        setCredentials(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load credentials");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!session) return null;
  const canWrite = can(session.user.role, "credential_write");
  const canDelete = can(session.user.role, "credential_delete");

  const handleCreate = () => {
    if (!name.trim() || !encryptedValue.trim() || !valuePreview.trim()) {
      setCreateError("Name, value, and preview are required");
      return;
    }
    setBusy(true);
    setCreateError(null);
    createCredential({
      name: name.trim(),
      credential_type: credentialType,
      encrypted_value: encryptedValue,
      value_preview: valuePreview.trim(),
      description: description.trim() || undefined,
    })
      .then(() => {
        setCreating(false);
        setName("");
        setEncryptedValue("");
        setValuePreview("");
        setDescription("");
        setCredentialType("n8n_api_key");
        load();
      })
      .catch((err: unknown) => {
        setCreateError(
          err instanceof ApiRequestError ? err.message : "Failed to create credential"
        );
      })
      .finally(() => setBusy(false));
  };

  const handleDelete = () => {
    if (!deleteTarget) return;
    setBusy(true);
    deleteCredential(deleteTarget.id)
      .then(() => {
        setDeleteTarget(null);
        load();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to delete credential");
        setDeleteTarget(null);
      })
      .finally(() => setBusy(false));
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Credentials"
        description="Encrypted secrets used by workflow integrations. Values are write-only."
        actions={
          canWrite ? <Button onClick={() => setCreating(true)}>New credential</Button> : undefined
        }
      />

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {loading ? (
        <Spinner label="Loading credentials…" />
      ) : credentials.length === 0 ? (
        <EmptyState
          title="No credentials"
          description="Add an API key or n8n credential to enable integrations."
        />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Name</TH>
              <TH>Type</TH>
              <TH>Value</TH>
              <TH>Created</TH>
              <TH />
            </tr>
          </THead>
          <TBody>
            {credentials.map((credential) => (
              <TRow key={credential.id}>
                <TD className="font-medium text-gray-900">{credential.name}</TD>
                <TD>
                  <Badge tone="purple">{CREDENTIAL_TYPE_LABELS[credential.credential_type]}</Badge>
                </TD>
                <TD className="font-mono text-xs text-gray-500">{credential.value_preview}</TD>
                <TD className="text-xs text-gray-400">{formatDateTime(credential.created_at)}</TD>
                <TD className="text-right">
                  {canDelete ? (
                    <Button variant="danger" onClick={() => setDeleteTarget(credential)}>
                      Delete
                    </Button>
                  ) : null}
                </TD>
              </TRow>
            ))}
          </TBody>
        </Table>
      )}

      <Modal
        open={creating}
        title="New credential"
        onClose={() => setCreating(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={busy}>
              {busy ? "Creating…" : "Create"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Name" htmlFor="cred-name" required>
            <Input
              id="cred-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. n8n production API key"
            />
          </Field>
          <Field label="Type" htmlFor="cred-type">
            <Select
              id="cred-type"
              value={credentialType}
              onChange={(e) => setCredentialType(e.target.value as CredentialType)}
            >
              <option value="n8n_api_key">n8n API key</option>
              <option value="api_key">API key</option>
              <option value="basic_auth">Basic auth</option>
            </Select>
          </Field>
          <Field
            label="Encrypted value"
            htmlFor="cred-value"
            required
            hint="Stored encrypted; never returned by the API."
          >
            <Input
              id="cred-value"
              type="password"
              value={encryptedValue}
              onChange={(e) => setEncryptedValue(e.target.value)}
              placeholder="Paste the secret"
            />
          </Field>
          <Field
            label="Value preview"
            htmlFor="cred-preview"
            required
            hint="Short hint shown in listings, e.g. abc…123"
          >
            <Input
              id="cred-preview"
              value={valuePreview}
              onChange={(e) => setValuePreview(e.target.value)}
              placeholder="e.g. abcd…wxyz"
            />
          </Field>
          <Field label="Description" htmlFor="cred-desc">
            <Input
              id="cred-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional"
            />
          </Field>
          {createError ? <p className="text-sm text-red-600">{createError}</p> : null}
        </div>
      </Modal>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete credential"
        message={`Delete "${deleteTarget?.name}"? This cannot be undone.`}
        confirmLabel="Delete"
        busy={busy}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
