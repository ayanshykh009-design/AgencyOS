// Lead create/edit form shared by the list and detail pages.
"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { Lead, LeadCreateInput, LeadStatus } from "@/types";

const STATUSES: Array<{ value: LeadStatus; label: string }> = [
  { value: "new", label: "New" },
  { value: "researching", label: "Researching" },
  { value: "contacted", label: "Contacted" },
  { value: "meeting_booked", label: "Meeting booked" },
  { value: "proposal_sent", label: "Proposal sent" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
];

interface LeadFormModalProps {
  open: boolean;
  title: string;
  lead?: Lead | null;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
  onSubmit: (input: LeadCreateInput) => void;
}

interface FormState {
  first_name: string;
  last_name: string;
  company: string;
  position: string;
  location: string;
  email: string;
  phone: string;
  whatsapp: string;
  website: string;
  linkedin_url: string;
  notes: string;
  status: LeadStatus;
  score: string;
  deal_value: string;
}

function toForm(lead?: Lead | null): FormState {
  return {
    first_name: lead?.first_name ?? "",
    last_name: lead?.last_name ?? "",
    company: lead?.company ?? "",
    position: lead?.position ?? "",
    location: lead?.location ?? "",
    email: lead?.email ?? "",
    phone: lead?.phone ?? "",
    whatsapp: lead?.whatsapp ?? "",
    website: lead?.website ?? "",
    linkedin_url: lead?.linkedin_url ?? "",
    notes: lead?.notes ?? "",
    status: lead?.status ?? "new",
    score: lead?.score != null ? String(lead.score) : "0",
    deal_value: lead?.deal_value != null ? String(lead.deal_value) : "",
  };
}

export function LeadFormModal({
  open,
  title,
  lead,
  busy = false,
  error = null,
  onClose,
  onSubmit,
}: LeadFormModalProps) {
  const [form, setForm] = useState<FormState>(() => toForm(lead));
  const [validation, setValidation] = useState<string | null>(null);

  if (open && lead && form.email === "" && lead.email) {
    // Re-sync the form whenever a different lead is opened for editing.
    setForm(toForm(lead));
  }

  function set<K extends keyof FormState>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit() {
    const hasContact = [form.email, form.phone, form.whatsapp, form.website].some(
      (value) => value.trim() !== ""
    );
    if (!hasContact) {
      setValidation(
        "At least one contact channel (email, phone, WhatsApp, or website) is required."
      );
      return;
    }
    setValidation(null);
    onSubmit({
      first_name: form.first_name.trim() || undefined,
      last_name: form.last_name.trim() || undefined,
      company: form.company.trim() || undefined,
      position: form.position.trim() || undefined,
      location: form.location.trim() || undefined,
      email: form.email.trim() || undefined,
      phone: form.phone.trim() || undefined,
      whatsapp: form.whatsapp.trim() || undefined,
      website: form.website.trim() || undefined,
      linkedin_url: form.linkedin_url.trim() || undefined,
      notes: form.notes.trim() || undefined,
      status: form.status,
      score: Number.parseInt(form.score, 10) || 0,
      deal_value: form.deal_value.trim() === "" ? undefined : Number(form.deal_value),
    });
  }

  return (
    <Modal
      open={open}
      title={title}
      width="lg"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={busy}>
            {busy ? "Saving…" : "Save lead"}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="First name">
          <Input value={form.first_name} onChange={(e) => set("first_name", e.target.value)} />
        </Field>
        <Field label="Last name">
          <Input value={form.last_name} onChange={(e) => set("last_name", e.target.value)} />
        </Field>
        <Field label="Company">
          <Input value={form.company} onChange={(e) => set("company", e.target.value)} />
        </Field>
        <Field label="Position">
          <Input value={form.position} onChange={(e) => set("position", e.target.value)} />
        </Field>
        <Field label="Email" required={!lead}>
          <Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
        </Field>
        <Field label="Phone">
          <Input value={form.phone} onChange={(e) => set("phone", e.target.value)} />
        </Field>
        <Field label="WhatsApp">
          <Input value={form.whatsapp} onChange={(e) => set("whatsapp", e.target.value)} />
        </Field>
        <Field label="Website">
          <Input value={form.website} onChange={(e) => set("website", e.target.value)} />
        </Field>
        <Field label="LinkedIn URL">
          <Input value={form.linkedin_url} onChange={(e) => set("linkedin_url", e.target.value)} />
        </Field>
        <Field label="Location">
          <Input value={form.location} onChange={(e) => set("location", e.target.value)} />
        </Field>
        <Field label="Status">
          <Select value={form.status} onChange={(e) => set("status", e.target.value)}>
            {STATUSES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Score">
            <Input
              type="number"
              min={0}
              max={100}
              value={form.score}
              onChange={(e) => set("score", e.target.value)}
            />
          </Field>
          <Field label="Deal value">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.deal_value}
              onChange={(e) => set("deal_value", e.target.value)}
            />
          </Field>
        </div>
        <Field label="Notes" className="sm:col-span-2">
          <Textarea rows={3} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>
      </div>
      {validation ? <p className="mt-3 text-sm text-red-600">{validation}</p> : null}
      {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
    </Modal>
  );
}
