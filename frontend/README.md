# AgencyOS Frontend — Next.js + TypeScript

Web application (agency dashboard and client UI) for the AI Outreach Agency
Operating System. Built on the Next.js App Router.

## Structure

| Path                  | Purpose                                                          |
| --------------------- | ---------------------------------------------------------------- |
| `src/app/`            | Route pages (App Router). Route groups: `(auth)`, `(dashboard)`. |
| `src/components/`     | Reusable UI: `ui/` (primitives) and `layouts/` (shells).         |
| `src/lib/`            | Non-React utilities: API client, constants, helpers.             |
| `src/hooks/`          | Custom React hooks (data fetching, UI state).                    |
| `src/services/`       | Backend/API integration modules.                                 |
| `src/stores/`         | Client state (e.g. Zustand) — global UI/session state.           |
| `src/types/`          | Shared TypeScript domain types.                                  |
| `public/`             | Static assets served as-is.                                      |

## Development

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev        # http://localhost:3000
npm run build      # production build
npm run lint       # eslint
npm run typecheck  # tsc --noEmit
```

## Conventions

- **Server components by default**; use `"use client"` only where interactivity
  is needed.
- Keep data-fetching in `src/services/`, never inline in pages.
- All env vars exposed to the browser must be prefixed `NEXT_PUBLIC_`.
