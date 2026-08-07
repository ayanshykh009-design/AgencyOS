"""Memory package: Phase 5D AI memory layer.

Owns long-term memory (founder / business / CRM / knowledge) and working
memory (conversation / research / workflow / shared context), plus the
retrieval and write flows built on the ``ai_memories`` store. Introduced in M1
as the package scaffold only — implementation lands in M4 (AI Memory).

Conventions: memory services are dependency-injected (import repositories,
never endpoints) and scope everything by ``organization_id``.
"""
