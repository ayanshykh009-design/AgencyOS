# Schema definitions

Table-by-table DDL for the AgencyOS database. One `.sql` file per domain:

- `users.sql` — agency users, roles, tenancy
- `campaigns.sql` — outreach campaigns
- `prospects.sql` — leads/prospects and enrichment data
- `sequences.sql` — outreach sequences, steps, and messages
- `activities.sql` — contact events (sent, opened, replied)
- `integrations.sql` — connected tool credentials (n8n, SMTP, LinkedIn)

Define a table here, then:

1. create a migration in `../migrations/`,
2. mirror the model in `../../backend/app/models/`.
