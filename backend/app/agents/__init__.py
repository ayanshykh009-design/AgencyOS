"""Agents package: Phase 5D AI agent runtime.

Owns the agent registry, the run loop, and the ``agent_runs`` / ``agent_state``
bookkeeping for the core and future agent set (see the approved Phase 5D
architecture). Introduced in M1 as the package scaffold only — the runtime is
implemented in M5 (Agent Runtime).

Conventions: agents are dependency-injected (import repositories and services,
never endpoints) and the package exports only the public agent manager API.
"""
