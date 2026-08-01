# Enum types (centralized)

Canonical, readable definitions of every PostgreSQL `ENUM` used by AgencyOS.
`0001_core_enums.sql` in the parent folder materializes these types in the
correct order — **keep the migration and these files in sync.**

| File                  | Enum(s)                                        |
| --------------------- | ---------------------------------------------- |
| `01_channel.sql`      | `outreach_channel`                             |
| `02_status.sql`       | `lead_status`, `outreach_status`, `import_status` |
| `03_activity.sql`     | `activity_event_type`                          |
| `04_identity.sql`     | `user_role`                                    |
| `05_conversation.sql` | `conversation_sender`                          |

Rules:

- Enum labels are lowercase `snake_case`, stored exactly as written here.
- Never reorder or rename labels once a migration is applied — add new values
  with a new migration (`ALTER TYPE ... ADD VALUE`).
- The backend mirrors these in `backend/app/models/enums.py`.
