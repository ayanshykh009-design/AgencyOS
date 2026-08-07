"""Communication package: Phase 5D founder communication layer.

Owns per-channel delivery (WhatsApp / email / dashboard / push) and the
approval-request flow that gates workflow execution. Introduced in M1 as the
package scaffold only — implementation lands in M6 (Founder Communication
Layer).

Conventions: channel adapters are dependency-injected and never hold secrets;
sending always flows through the n8n automation platform.
"""
