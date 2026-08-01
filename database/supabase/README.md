# Supabase project configuration

This directory is the Supabase project root. It defines the managed database
project that production deployments target.

| Entry         | Purpose                                          |
| ------------- | ------------------------------------------------ |
| `config.toml` | Supabase local CLI + project configuration.      |
| `functions/`  | Edge Functions (Deno) — webhooks, RLS-safe ops.   |
| `policies/`   | Row Level Security policies, one file per table.  |

Run the full local Supabase stack with the Supabase CLI:

```bash
cd database/supabase
supabase start
```

Note: `database/supabase/.branches`, `.temp`, and `.local` are git-ignored.
