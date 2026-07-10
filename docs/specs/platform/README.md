# Agentic Plugin Platform — Portable Specification Set

**Status:** Draft · **Owner:** Patrik Alexits · **Created:** 2026-07-10

This folder specifies a **stack-agnostic architecture** for an *agentic plugin platform*:
a small stable **kernel** that hosts pluggable **agentic apps ("plugins")**, where each
plugin is consumed through **two protocols** — a machine **Capability Protocol** (the agent's
tools/resources; reference binding = MCP) and a declarative **App Contract** (the plugin's UI,
data, lifecycle, and auth posture, which the Capability Protocol cannot carry).

These specs describe the concept **in abstract roles and ports**, not in any particular
technology. The platform this was extracted from runs on Supabase + Temporal + React +
Azure OpenAI, but **that stack is deliberately treated as one interchangeable reference
mapping** — see [`05-porting-guide.md`](05-porting-guide.md). You can implement every spec
here on a completely different stack and remain conformant.

## Why this exists

To make the concept **understandable, reusable, and adjustable** independent of the original
implementation. Read the specs; map the abstract *ports* to your own stack's *adapters*;
build. Nothing here mandates Supabase, Temporal, React, a specific cloud, or even a specific
programming language.

## How to read this set (in order)

| # | Spec | What it defines | Read if you want to… |
|---|------|-----------------|----------------------|
| 00 | [`00-concept.md`](00-concept.md) | The idea, the problem, the principles, the vocabulary | Understand *what* and *why* |
| 01 | [`01-architecture.md`](01-architecture.md) | Components, the two-protocol split, ports, data flow | Understand *how it fits together* |
| 02 | [`02-plugin-manifest.md`](02-plugin-manifest.md) | The **App Contract** — the declarative plugin descriptor | Author or validate a plugin |
| 03 | [`03-kernel-contract.md`](03-kernel-contract.md) | Kernel responsibilities + the **ports** it requires | Build the host |
| 04 | [`04-auth-and-entitlements.md`](04-auth-and-entitlements.md) | Identity, per-user entitlement, auth-driven connection | Build the trust boundary |
| 05 | [`05-porting-guide.md`](05-porting-guide.md) | Map abstract ports → any concrete stack (+ the reference stack as one example) | Port it to your stack |

## Conformance vocabulary

The specs use **MUST / MUST NOT / SHOULD / MAY** in the RFC-2119 sense. A conformant
implementation satisfies every **MUST**. Acceptance criteria are written as checkboxes so
they can drive spec-driven / test-first development.

## Relationship to the source repo

- Conceptual lineage: this generalises [ADR-0008](../../adrs/0008-education-platform-feature-plugin-architecture.md)
  (kernel + feature-plugin) and [ADR-0012](../../adrs/0012-plugins-as-mcp-servers.md)
  (plugins as MCP servers). Those ADRs are the *stack-bound* decisions; this set is the
  *stack-free* concept behind them.
- The feature specs in the parent folder (`study-pathway-advisor.md`, `study-planner.md`)
  are **example plugins** built on the reference stack, not part of the portable platform.
