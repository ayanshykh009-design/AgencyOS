# Scripts

Maintenance, setup, database, and deployment scripts.

| Folder     | Purpose                                                  |
| ---------- | -------------------------------------------------------- |
| `setup/`   | One-time environment bootstrap (env files, storage dirs).|
| `db/`      | Migrate / seed / backup database helpers.                |
| `deploy/`  | Deployment and release helpers.                          |
| `utils/`   | Misc helpers (env checks, git hooks).                    |

Conventions:

- Provide `.sh` (Unix/WSL) and `.ps1` (Windows PowerShell) equivalents where
  it matters. The `.sh` versions are what the Makefile invokes.
- Scripts are idempotent and fail loudly (exit non-zero) on error.
