// Confirm dialog built on Modal (destructive actions).
"use client";

import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message?: string;
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  busy = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      title={title}
      width="sm"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={busy}>
            {busy ? "Working…" : confirmLabel}
          </Button>
        </>
      }
    >
      {message ? <p className="text-sm text-gray-600">{message}</p> : null}
    </Modal>
  );
}
