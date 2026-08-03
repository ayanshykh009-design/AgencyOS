// Notes service: list, create, update, delete, and search lead notes.
import { apiFetch } from "@/lib/api-client";
import type { Note, NoteCreateInput, NoteUpdateInput, Page } from "@/types";

export async function listNotesByLead(
  leadId: string,
  limit = 100,
  offset = 0
): Promise<Page<Note>> {
  return apiFetch<Page<Note>>(
    `/notes?lead_id=${encodeURIComponent(leadId)}&limit=${limit}&offset=${offset}`
  );
}

export async function getNote(noteId: string): Promise<Note> {
  return apiFetch<Note>(`/notes/${noteId}`);
}

export async function createNote(input: NoteCreateInput): Promise<Note> {
  return apiFetch<Note>("/notes", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateNote(noteId: string, patch: NoteUpdateInput): Promise<Note> {
  return apiFetch<Note>(`/notes/${noteId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteNote(noteId: string): Promise<void> {
  await apiFetch<void>(`/notes/${noteId}`, { method: "DELETE" });
}
