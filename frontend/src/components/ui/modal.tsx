// Modal dialog primitive with keyboard/backdrop handling.
"use client";

import { useEffect } from "react";

interface ModalProps {
  open: boolean;
  title?: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: "sm" | "md" | "lg";
}

const WIDTHS: Record<NonNullable<ModalProps["width"]>, string> = {
  sm: "max-w-md",
  md: "max-w-xl",
  lg: "max-w-2xl",
};

export function Modal({ open, title, onClose, children, footer, width = "md" }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-16"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={`w-full ${WIDTHS[width]} rounded-lg bg-white shadow-xl`}>
        {title ? (
          <div className="flex items-center justify-between border-b px-5 py-3">
            <h3 className="text-sm font-semibold">{title}</h3>
            <button
              type="button"
              aria-label="Close"
              className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
              onClick={onClose}
            >
              <span aria-hidden>✕</span>
            </button>
          </div>
        ) : null}
        <div className="px-5 py-4">{children}</div>
        {footer ? (
          <div className="flex items-center justify-end gap-2 border-t px-5 py-3">{footer}</div>
        ) : null}
      </div>
    </div>
  );
}
