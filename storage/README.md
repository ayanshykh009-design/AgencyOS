# Storage

Local artifact storage for the AgencyOS platform. Everything here is
git-ignored except the `.gitkeep` files.

| Folder     | Purpose                                                  |
| ---------- | -------------------------------------------------------- |
| `uploads/` | User-uploaded files (CSV leads, attachments, avatars).   |
| `exports/` | Generated exports (reports, campaign archives, CSV dumps). |
| `logs/`    | Application log files (rotated).                         |
| `backups/` | Manual/scripted backups before destructive operations.   |

Production note: in a real deployment, replace local disk with object storage
(S3/GCS) for uploads/exports and a proper log aggregator. These folders exist
to keep local development deterministic.
