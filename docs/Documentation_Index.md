# Documentation Index

Welcome to the **SLH AI Hub** documentation. This index helps you locate the
architecture, decisions, tech stack, testing manifesto, and per-feature manifestos.
(Structure mirrors the `evento-process-ui` conventions, sized for this smaller repo.)

---

## 📝 Architecture Decision Records (ADR)

The reference point for every architectural choice — see [`docs/adrs/`](./adrs/) and its
[index](./adrs/README.md). Highlights:

| ADR | Title | Status |
|---|---|---|
| [0003](./adrs/0003-testing-strategy.md) | Testing strategy — CI fails loud if tests vanish | Accepted |
| [0004](./adrs/0004-deployment-posture-local-only.md) | Deployment posture — local-only | Accepted |
| [0007](./adrs/0007-owner-scoped-rls-and-auth.md) | Owner-scoped RLS + auth (SEC-1) | Accepted |
| [0008](./adrs/0008-education-platform-feature-plugin-architecture.md) | Education platform + feature-plugin architecture | Accepted |
| [0009](./adrs/0009-confidence-signal-observable-not-self-reported.md) | Confidence signal from observable factors | Accepted |
| [0010](./adrs/0010-frontend-nav-and-feature-flags.md) | Frontend nav + env feature flags | Accepted |
| [0011](./adrs/0011-per-feature-auth-gate.md) | Per-feature auth gate (`requiresAuth`) | Accepted |
| [0012](./adrs/0012-plugins-as-mcp-servers.md) | Plugins as MCP servers (kernel-as-MCP-host) | Proposed |

## 📂 Architecture & Stack

| Document | Description |
|---|---|
| [Product Architecture](./architecture/product-architecture.md) | The kernel + feature-plugin platform, run-row lifecycle, data model, cross-cutting concerns. |
| [Tech Stack](./TECH_STACK.md) | Every technology, version, and why it's here. |
| [Testing Manifesto](./TESTING.md) | What we test, where, and how (Python/Temporal + frontend + live RLS). |
| [PLAYBOOK](./PLAYBOOK.md) | The binding build recipe + guardrails for changing this repo. |

## 🧩 Feature & library manifestos

Each library carries a `README.md` (what it is) and a `MANIFESTO.md` (the binding rules —
file roles, boundaries, forbidden imports). These **override** generic root guidance for
that library.

| Library | Type | Docs |
|---|---|---|
| **kernel** | shared platform | [README](../temporal/src/kernel/README.md) · [MANIFESTO](../temporal/src/kernel/MANIFESTO.md) |
| **program_evaluator** | feature | [README](../temporal/src/features/program_evaluator/README.md) · [MANIFESTO](../temporal/src/features/program_evaluator/MANIFESTO.md) |
| **study_planner** | feature | [README](../temporal/src/features/study_planner/README.md) · [MANIFESTO](../temporal/src/features/study_planner/MANIFESTO.md) |

## 📐 Specs

Approved feature specs live in [`docs/specs/`](./specs/): the
[study-pathway-advisor](./specs/study-pathway-advisor.md) (platform + evaluator) and the
[study-planner](./specs/study-planner.md).

**Portable platform spec set** — [`docs/specs/platform/`](./specs/platform/) (start at its
[README](./specs/platform/README.md)) documents the kernel + agentic-plugin concept in a
**stack-agnostic, ports-and-adapters** form so it can be understood, reused, and ported to a
different tech stack. Reading order: [concept](./specs/platform/00-concept.md) →
[architecture](./specs/platform/01-architecture.md) →
[plugin manifest](./specs/platform/02-plugin-manifest.md) →
[kernel contract](./specs/platform/03-kernel-contract.md) →
[auth & entitlements](./specs/platform/04-auth-and-entitlements.md) →
[porting guide](./specs/platform/05-porting-guide.md). Generalises ADR-0008 + ADR-0012; the
current Supabase/Temporal/React/Azure stack is one interchangeable reference mapping.

---

> 💡 Tip: for *why*, read the ADRs first. For *how to build a feature*, read PLAYBOOK + the
> feature manifestos. For *what a library may and may not do*, its `MANIFESTO.md` is binding.
