"""Growth package: Phase 5D growth agent.

Owns revenue / pipeline analysis, deterministic forecasting, and business
insight generation for the founder assistant. Introduced in M1 as the package
scaffold only — implementation lands in M7 (Growth Agent).

Conventions: growth services are dependency-injected (import repositories,
never endpoints) and read only tenant-scoped data.
"""
