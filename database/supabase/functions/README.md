# Edge Functions

Supabase Edge Functions (Deno) for operations that must run close to the
database with RLS-aware behavior. Examples (create when implemented):

- `send-webhook` — forward inbound outreach events into n8n
- `reply-classification` — classify prospect replies via AI

Each function is a folder with an `index.ts` (Deno) entrypoint.
Deploy with the Supabase CLI: `supabase functions deploy <name>`.
