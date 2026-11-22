// Credentials: admin-only, write-only vault view.
//
// The backend only returns a value preview. This UI never renders secrets,
// never offers plaintext secret entry, and makes no claim of client-side
// encryption. Create/replace stay disabled pending a founder decision
// (B6-D-01) rather than faking a working encrypted-value flow.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  AutomationListState,
  DisabledActionReason,
  actionDisabledReason,
  formatUtcOrNever,
} from "@/components/automation/automation-states";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Modal,
  PageHeader,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TRow,
} from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { CREDENTIAL_TYPE_LABELS } from "@/lib/format";
import { canManageCredentials } from "@/lib/batch6-permissions";
import { deleteCredential, listCredentials, rotateCredential } from "@/services/credentials";
import type { Credential, UserRole } from "@/types";

export const CREDENTIAL_WRITE_UNAVAILABLE =
  "Credential creation and value replacement are unavailable in this UI. The backend stores values encrypted server-side; this page performs no client-side encryption.";

/** Exported for static-markup tests: denied roles see no action buttons. */
export function CredentialActions({
  role,
  busy,
  onRotate,
  onDelete,
}: {
  role: UserRole;
  busy: boolean;
  onRotate: () => void;
  onDelete: () => void;
}) {
  if (!canManageCredentials(role)) return null;
  const writeReason = actionDisabledReason(
    false,
    "Requires a founder decision on the encrypted-value entry flow."
  );
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Button variant="outline" disabled onClick={() => undefined} title={writeReason ?? undefined}>
        Replace value
      </Button>
      <Button variant="outline" disabled={busy} onClick={onRotate}>
        Rotate
      </Button>
      <Button variant="danger" disabled={busy} onClick={onDelete}>
        Delete
      </Button>
    </div>
  );
}

export default function CredentialsPage() {
  const session = useAuth();
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Credential | null>(null);

  const fetchCredentials = useCallback(() => {
    return listCredentials({ limit: 200 })
      .then((page) => {
        setCredentials(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setCredentials([]);
        setError(err instanceof ApiRequestError ? err.message : "Failed to load credentials");
      })
      .finally(() => setLoading(false));
  }, []);

  const reload = useCallback(() => {
    setLoading(true);
    return fetchCredentials();
  }, [fetchCredentials]);

  useEffect(() => {
    if (session) void fetchCredentials();
  }, [fetchCredentials, session]);

  if (!session) return null;
  const role = session.user.role;
  const canManage = canManageCredentials(role);

  const rotate = (credential: Credential) => {
    setBusyId(credential.id);
    rotateCredential(credential.id)
      .then(() => {
        setError(null);
        return reload();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to rotate credential");
      })
      .finally(() => setBusyId(null));
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setBusyId(target.id);
    deleteCredential(target.id)
      .then(() => {
        setDeleteTarget(null);
        setError(null);
        return reload();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to delete credential");
        setDeleteTarget(null);
      })
      .finally(() => setBusyId(null));
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Credentials"
        description="Admin-only, write-only view of integration credentials. Values are never displayed."
        actions={
          canManage ? (
            <Button disabled title={CREDENTIAL_WRITE_UNAVAILABLE}>
              New credential
            </Button>
          ) : undefined
        }
      />

      <AutomationListState
        denied={!canManage}
        deniedMessage="You do not have permission to view credentials."
        loading={loading}
        loadingLabel="Loading credentials…"
        error={error}
        onRetry={() => void reload()}
        empty={credentials.length === 0}
        emptyTitle="No credentials"
        emptyDescription="No credentials are registered for this organization."
      />

      {canManage ? (
        <Card>
          <CardHeader title="Secret entry unavailable" />
          <CardBody>
            <p className="text-sm text-gray-600">{CREDENTIAL_WRITE_UNAVAILABLE}</p>
            <DisabledActionReason reason="Existing credentials can be rotated or deleted below." />
          </CardBody>
        </Card>
      ) : null}

      {canManage && !loading && !error && credentials.length > 0 ? (
        <Table>
          <THead>
            <tr>
              <TH>Name</TH>
              <TH>Type</TH>
              <TH>Value preview</TH>
              <TH>Key version</TH>
              <TH>Last rotated (UTC)</TH>
              <TH>Updated (UTC)</TH>
              <TH>Actions</TH>
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
                <TD className="font-mono text-xs text-gray-600">{credential.key_version}</TD>
                <TD className="text-xs text-gray-600">
                  {formatUtcOrNever(credential.last_rotated_at)}
                </TD>
                <TD className="text-xs text-gray-600">{formatUtcOrNever(credential.updated_at)}</TD>
                <TD>
                  <CredentialActions
                    role={role}
                    busy={busyId === credential.id}
                    onRotate={() => rotate(credential)}
                    onDelete={() => setDeleteTarget(credential)}
                  />
                </TD>
              </TRow>
            ))}
          </TBody>
        </Table>
      ) : null}

      {deleteTarget ? (
        <Modal
          open
          title="Delete credential"
          onClose={() => setDeleteTarget(null)}
          width="sm"
          footer={
            <>
              <Button
                variant="ghost"
                onClick={() => setDeleteTarget(null)}
                disabled={busyId !== null}
              >
                Cancel
              </Button>
              <Button variant="danger" onClick={confirmDelete} disabled={busyId !== null}>
                Delete
              </Button>
            </>
          }
        >
          <p className="text-sm text-gray-600">
            Delete &ldquo;{deleteTarget.name}&rdquo;? This cannot be undone.
          </p>
        </Modal>
      ) : null}
    </div>
  );
}
