# Database ERD (V1)

Entity-relationship diagram for the 15 core tables. Rendered with Mermaid.

```mermaid
erDiagram
    organizations ||--o{ users : "has"
    organizations ||--o{ lead_sources : "has"
    organizations ||--o{ leads : "owns"
    organizations ||--o{ lead_research : "owns"
    organizations ||--o{ outreach_messages : "owns"
    organizations ||--o{ outreach_attempts : "owns"
    organizations ||--o{ follow_ups : "owns"
    organizations ||--o{ manual_outreach_queue : "owns"
    organizations ||--o{ conversations : "owns"
    organizations ||--o{ conversation_messages : "owns"
    organizations ||--o{ activity_logs : "owns"
    organizations ||--o{ import_jobs : "owns"
    organizations ||--o{ import_row_errors : "owns"
    organizations ||--o{ provider_usage : "owns"

    users ||--o{ leads : "owns/assigns"
    users ||--o{ manual_outreach_queue : "assigned"
    users ||--o{ conversation_messages : "sent by"
    users ||--o{ activity_logs : "acted"
    users ||--o{ import_jobs : "created"

    lead_sources ||--o{ leads : "sources"
    lead_sources ||--o{ import_jobs : "imports to"

    leads ||--o| lead_research : "researched by"
    leads ||--o{ outreach_attempts : "receives"
    leads ||--o{ follow_ups : "receives"
    leads ||--o{ manual_outreach_queue : "queued"
    leads ||--o{ conversations : "chats in"
    leads ||--o{ activity_logs : "logged"

    outreach_messages ||--o{ outreach_attempts : "instantiated by"
    outreach_attempts ||--o{ follow_ups : "spawns"

    conversations ||--o{ conversation_messages : "contains"
    import_jobs ||--o{ import_row_errors : "logs"
```

## Relationships at a glance

| Parent            | Child                 | Cardinality | Notes                                   |
| ----------------- | --------------------- | ----------- | --------------------------------------- |
| `organizations`   | everything else       | 1 → N       | tenant root; `organization_id` everywhere |
| `users`           | `leads.owner_user_id` | 1 → N       | optional owner                          |
| `lead_sources`    | `leads`               | 1 → N       | optional; `ON DELETE SET NULL`          |
| `leads`           | `lead_research`       | 1 → 1       | `UNIQUE (lead_id)`                      |
| `leads`           | `outreach_attempts`   | 1 → N       | `ON DELETE CASCADE`                     |
| `outreach_attempts`| `follow_ups`          | 1 → N       | optional anchor attempt                 |
| `leads`           | `conversations`       | 1 → N       | at most one open per lead/channel       |
| `conversations`   | `conversation_messages` | 1 → N      | append-only; cascade delete             |
| `import_jobs`     | `import_row_errors`   | 1 → N       | append-only; cascade delete             |

## Key constraints

- **Duplicate protection** (`leads`): partial unique indexes on
  `email_normalized`, `phone_normalized` (phone + WhatsApp share a bucket),
  and `website_domain`, each scoped to `organization_id`.
- **One open thread**: partial unique index
  `uq_conversations_open_per_channel (lead_id, channel) WHERE is_open`.
- **Daily rollup**: `uq_provider_usage_daily
  (organization_id, provider, feature, usage_date)`.
- **Non-negative + ranged checks** on scores, priorities, sizes, and token
  counts throughout.

## Enum dependencies

`users.role` → `user_role`; `leads.status` → `lead_status`; `channel` columns
→ `outreach_channel`; `status` on outreach tables → `outreach_status`;
`import_jobs.status` → `import_status`; `activity_logs.event_type` →
`activity_event_type`; `conversation_messages.sender_type` →
`conversation_sender`. See `database/migrations/enums/`.
