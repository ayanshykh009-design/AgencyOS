// Notes panel for a single lead: list, pin, create, edit, delete.
"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Button, EmptyState, Spinner, Textarea } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { formatRelative } from "@/lib/format";
import { can } from "@/lib/permissions";
import { createNote, deleteNote, listNotesByLead, updateNote } from "@/services/notes";
import type { Note, NoteCreateInput } from "@/types";

export function LeadNotesPanel({ leadId }: { leadId: string }) {
  const session = useAuth();
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [pinned, setPinned] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    listNotesByLead(leadId)
      .then((page) => setNotes(page.items))
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load notes");
      })
      .finally(() => setLoading(false));
  }, [leadId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!session) return null;
  const canWrite = can(session.user.role, "note_write");

  async function handleCreate() {
    if (body.trim() === "") return;
    setSaving(true);
    setError(null);
    const input: NoteCreateInput = { lead_id: leadId, body: body.trim(), pinned };
    try {
      await createNote(input);
      setBody("");
      setPinned(false);
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to add note");
    } finally {
      setSaving(false);
    }
  }

  async function handleTogglePin(note: Note) {
    try {
      await updateNote(note.id, { pinned: !note.pinned });
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to update note");
    }
  }

  async function handleDelete(note: Note) {
    try {
      await deleteNote(note.id);
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to delete note");
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold">Notes</h3>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {loading ? (
        <Spinner label="Loading notes…" />
      ) : notes.length === 0 ? (
        <EmptyState
          title="No notes yet"
          description="Add a note to capture context about this lead."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {notes.map((note) => (
            <li
              key={note.id}
              className="flex flex-col gap-1 rounded-lg border bg-white p-3 text-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <time className="text-xs text-gray-400">{formatRelative(note.created_at)}</time>
                  {note.pinned ? <Badge tone="amber">Pinned</Badge> : null}
                </span>
                {canWrite ? (
                  <span className="flex gap-1">
                    <button
                      type="button"
                      className="text-xs text-gray-500 underline"
                      onClick={() => handleTogglePin(note)}
                    >
                      {note.pinned ? "Unpin" : "Pin"}
                    </button>
                    <button
                      type="button"
                      className="text-xs text-red-600 underline"
                      onClick={() => handleDelete(note)}
                    >
                      Delete
                    </button>
                  </span>
                ) : null}
              </div>
              <p className="whitespace-pre-wrap text-gray-700">{note.body}</p>
            </li>
          ))}
        </ul>
      )}
      {canWrite ? (
        <div className="flex flex-col gap-2">
          <Textarea
            rows={3}
            placeholder="Add a note…"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-gray-600">
              <input
                type="checkbox"
                checked={pinned}
                onChange={(e) => setPinned(e.target.checked)}
              />
              Pin note
            </label>
            <Button onClick={handleCreate} disabled={saving || body.trim() === ""}>
              {saving ? "Adding…" : "Add note"}
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
