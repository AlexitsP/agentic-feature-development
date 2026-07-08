# Architecture Overview

This directory holds the **cross-cutting architecture documentation** for this
project — the diagrams and narrative that tie the subsystems together. It
complements, and does not replace:

- [`docs/adrs/`](../adrs/) — **why** each decision was made (the binding record).
- [`docs/specs/`](../specs/) — the **detailed designs** for individual slices.

Read this when you want the *shape of the whole system*; drop into the ADRs and
specs when you need the depth on a particular decision.

> All diagrams below render natively on GitHub (Mermaid). Replace the placeholder
> labels with your system's real containers, then let each subsystem page go deeper.

## What this system is

This repository ships **a product plus the factory that builds it**:

1. **The product** — a Supabase + Temporal + Vite/React app: the **Gains Check** demo (check +
   multi-agent plan). See [`product-architecture.md`](./product-architecture.md) for the shape.
   (The repo was trimmed to Gains-only — [ADR-0006](../adrs/0006-trim-to-gains-only-minimal-repo.md);
   Entity Insights references in these docs are historical.)
2. **The Software Factory** — GitHub Actions + role-based AI agents (see
   [`.github/agents/`](../../.github/agents/)) that triage, design, build, review,
   and ship the product. Configured via [`.github/factory.yml`](../../.github/factory.yml).
3. _(Optional)_ **The Operations Factory** — scheduled agentic workflows that
   automate back-office operations for the people who use the product.

```mermaid
flowchart TB
    subgraph Builds["🏭 Software Factory — builds the product"]
        direction LR
        GHA["GitHub Actions<br/>cadence pipelines"] --> Agents["Role-based agents<br/>(PM, reviewers, architect…)"]
        Agents --> Copilot["Coding agent<br/>(implements)"]
    end

    subgraph Product["📦 The Product — <APP_NAME>"]
        direction LR
        FE["Frontend"]
        DB[("Database")]
        WORKER["Worker / orchestration"]
        FE --> DB
        WORKER --> DB
    end

    Builds -->|ships code & images| Product
    Users(["End users"]) --> FE
    Maintainers(["Maintainers"]) -.->|epics & guardrails| Builds
```

## C4 Level 1 — System context

```mermaid
flowchart TB
    user(["End users"])
    maint(["Maintainers"])
    gh(["GitHub<br/>(issues · PRs · Actions)"])

    sys["<b><APP_NAME></b><br/>_\<one-line system description\>_"]

    user -->|uses| sys
    maint -->|files epics, sets guardrails| sys
    sys -->|orchestrates issues/PRs| gh
    gh -->|runs agents & CI| sys
```

## C4 Level 2 — Containers

```mermaid
flowchart TB
    subgraph cluster["Cluster (<AKS_CLUSTER_NONPROD>)"]
        subgraph nsapp["ns: <DEV_NAMESPACE> / <TEST_NAMESPACE>"]
            fe["frontend"]
            worker["worker"]
        end
    end

    fe --> worker
```

## The pages

| Page | What it covers |
|------|----------------|
| [Product architecture](./product-architecture.md) | **The main page** — request lifecycle, components, data model, the two Gains engines, external deps |
| [ADRs](../adrs/) | The binding record of *why* each decision was made |
| [Specs](../specs/) | Detailed designs for individual feature slices |
| [Onboarding](../../ONBOARDING.md) | Get a fresh clone running and make a first change |

> The Software-Factory / multi-env AKS content above is inherited from the template. This fork
> runs the **product locally** and keeps the factory/deploy pipelines disabled — see
> [ADR-0004](../adrs/0004-deployment-posture-local-only.md).
