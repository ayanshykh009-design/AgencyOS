# Prompts — AI Prompt Library

Versioned, production-grade prompt templates used across the outreach pipeline:
cold email, follow-ups, LinkedIn messaging, and personalization.

## Structure

| Path                 | Purpose                                                        |
| -------------------- | -------------------------------------------------------------- |
| `cold-email/`        | Ice-breakers and cold email body generators.                   |
| `follow-up/`         | Follow-up / escalation sequences.                              |
| `linkedin/`          | LinkedIn connection requests and direct messages.              |
| `personalization/`   | Research-to-insight and per-prospect personalization prompts.  |
| `system/`            | System prompts for orchestrator/agent roles.                   |

## Versioning convention

Every prompt is a Markdown file with YAML front-matter:

```markdown
---
name: ice-breaker
version: 1.0.0
status: draft            # draft | active | deprecated
model: gpt-4o-mini       # target model
tags: [cold-email, outbound]
---

# Role
...

# Instructions
...

# Output format
...
```

Rules:

- Bump `version` (semver) on any behavior-affecting change. Never edit an
  `active` prompt silently — create a new version and migrate consumers.
- Reference prompts by `name@version` from backend/services and n8n
  workflows so consumers stay pinned to known-good versions.
- Keep prompts free of customer/company data; merge data at render time.
