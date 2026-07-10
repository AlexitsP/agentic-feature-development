# 05 — Porting Guide: Map the Ports to Your Stack

**Status:** Draft
**Owner:** Patrik Alexits
**Created:** 2026-07-10
**Last Updated:** 2026-07-10

> This is the spec that makes the concept **yours**. The platform is defined by the seven ports
> in [`03`](03-kernel-contract.md) and the App Contract in [`02`](02-plugin-manifest.md). To
> port it, you supply an **adapter** for each port on your chosen stack. Nothing above this
> layer changes. The original stack (Supabase + Temporal + React + Azure OpenAI) is included
> below purely as **one worked example** — it is explicitly interchangeable and not endorsed.

## How porting works

1. Choose a technology for each of the seven ports.
2. Implement each port's **obligations** (from [`03`](03-kernel-contract.md)) as an adapter.
3. Keep the kernel and all plugin manifests unchanged.
4. Run the **conformance checklist** at the bottom. If it passes, your port is faithful.

You do **not** need to port everything at once. The Durable Execution, Run Store, and Capability
Client ports are the load-bearing three; the rest can start as thin implementations.

## Port → capability → candidate technologies

| Port | What you need from it | Candidate techs (pick one) | Reference stack used |
|------|-----------------------|----------------------------|----------------------|
| **Durable Execution** | durable, retriable, resumable task runs; exactly-once finalize; step timeouts | Temporal, Restate, AWS Step Functions, Azure Durable Functions, DBOS, a transactional-outbox + queue, or your own saga runner | Temporal (Python worker) |
| **Run Store** | persist runs/results/traces; **per-owner row authorization**; generic errors | Postgres w/ row-level security, DynamoDB w/ IAM/condition keys, Firestore rules, or an app-layer authz guard over any DB | Supabase (Postgres + RLS) |
| **Trace Channel** | near-real-time, owner-scoped event stream to the UI | Postgres LISTEN/NOTIFY or logical-replication feeds, WebSocket/SSE gateway, Ably/Pusher, Redis pub/sub, Kafka + WS bridge | Supabase Realtime |
| **Identity & Entitlement** | verifiable principal; per-plugin entitlement; user-scoped capability tokens | OIDC/OAuth IdP (Auth0, Entra ID, Keycloak, Cognito), your SSO + an entitlement service/RBAC store | Supabase Auth (+ anon sign-in) |
| **Model Access** | provider-isolated inference w/ usage accounting | Any LLM provider behind one adapter (OpenAI, Anthropic, Azure OpenAI, Bedrock, Vertex, local/vLLM) | Azure OpenAI (`gpt-5-mini`) |
| **UI Host** | render launcher + per-plugin entrypoints; live progress | Any SPA/SSR framework (React, Svelte, Vue, Angular, server-rendered, or native/mobile) | React + TanStack Router |
| **Capability Client** | speak the Capability Protocol + its authz handshake; identical local/remote interface | Any MCP client SDK; for in-process, a local shim presenting the same interface | MCP client (planned) |

> **The point of the table:** every "reference stack" cell is replaceable by any cell to its
> left without touching the kernel or a plugin. If your organisation standardises on, say,
> .NET + Azure Durable Functions + Cosmos DB + SignalR + Entra ID + Bedrock + Blazor, you write
> seven adapters and you are done.

## Adapter contract skeletons (illustrative)

Implement one object per port satisfying the obligations in [`03`](03-kernel-contract.md). E.g.:

```
DurableExecutionAdapter:
  startRun(runId, plan)
  step(name, fn, {retry, idempotent, timeout})   # MUST resume after restart; exactly-once finalize

RunStoreAdapter:
  createRun(run)                                  # returns runId
  finalizeRun(runId, resultOrGenericError, confidence)
  getRun(runId, asUser)                           # MUST enforce owner scoping
  appendTrace(runId, event)

CapabilityClientAdapter:
  connect(capabilityRef, token)                   # MUST do authz handshake first
  callTool(session, name, args)                   # caller wraps in DurableExecution.step
  invoke(session, task)                           # coarse entry for self_agent
```

Keep the adapters the **only** place your stack's SDKs appear. A grep for a stack SDK outside
the adapters is a conformance smell (see [`03`](03-kernel-contract.md) acceptance criteria).

## Minimum viable port (fastest path to a running platform)

If you want the smallest faithful build:

- **Durable Execution:** a single-worker queue + a runs table you update per step, with an
  idempotency key and a "finalized" flag for exactly-once. (Upgrade to a real engine later.)
- **Run Store:** Postgres with RLS (or app-layer owner checks) — this is non-negotiable because
  isolation is a MUST.
- **Trace Channel:** SSE over the runs/trace table changes.
- **Identity & Entitlement:** your existing OIDC IdP + a simple `user → entitlements` table.
- **Model Access:** one provider adapter returning `{output, usage}`.
- **UI Host:** your standard SPA; a launcher that lists entitled manifests + a per-route view.
- **Capability Client:** an MCP client for remote plugins; a local shim for in-process ones.

Start with **one in-process, thin-toolset plugin** end-to-end (request → durable run →
owner-scoped result → live trace → confidence). Then add **one out-of-process plugin** to prove
the boundary and the auth handshake. That two-plugin milestone validates the whole concept.

## What NOT to change when porting (the portable invariants)

Porting swaps *adapters*, never these:

- The **two-protocol split** ([`00`](00-concept.md) Principle 1).
- **Invoke-through-durable-execution** for every plugin call ([`01`](01-architecture.md),
  Principle 3).
- **Observable-signal confidence** (Principle 4).
- **Entitlement gates connection** (Principle 5) and the **`requires_auth ⇔ owner_scoped`**
  invariant ([`04`](04-auth-and-entitlements.md)).
- The **App Contract field rules** ([`02`](02-plugin-manifest.md)).

If a port choice makes one of these impossible, the port choice is wrong — not the invariant.

## Conformance checklist (run this after porting)

- [ ] Kernel + plugin manifests are unchanged from the reference concept; only adapters differ.
- [ ] Stack SDK imports appear **only** inside adapters.
- [ ] A run survives killing the execution worker mid-run and finalizes correctly, exactly once.
- [ ] An owner-scoped run is unreadable by another user via the Run Store adapter.
- [ ] An unentitled user never triggers a capability connection to the plugin.
- [ ] A capability token for plugin A is rejected by plugin B.
- [ ] Every result carries an observable-signal confidence value; empty-input/no-grounding is
      never High.
- [ ] One in-process thin plugin **and** one out-of-process (self-agent or thin) plugin both run
      end-to-end through the identical kernel.

## The reference stack, stated plainly (so you can discard it)

The concept was extracted from a platform running: **Supabase** (Postgres + RLS + Realtime +
Auth) as Run Store / Trace / Identity; **Temporal** (Python worker + poller) as Durable
Execution; **React + TanStack Router** as UI Host; **Azure OpenAI** as Model Access; and a
planned **MCP** client as Capability Client. This mapping is documented only to show the ports
are real and fillable. **Treat every one of those as a swappable adapter choice, not a
requirement** — which is the entire reason these specs are written in ports, not products.

## References

- Ports & obligations: [`03-kernel-contract.md`](03-kernel-contract.md)
- App Contract: [`02-plugin-manifest.md`](02-plugin-manifest.md)
- Concept & invariants: [`00-concept.md`](00-concept.md)
- Stack-bound lineage (what to generalise away from): ADR-0008, ADR-0012.
