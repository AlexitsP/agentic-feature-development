# 01 — Architecture Specification

**Status:** Draft
**Owner:** Patrik Alexits
**Created:** 2026-07-10
**Last Updated:** 2026-07-10

> Stack-agnostic. Describes components, the two-protocol split, the ports, and the runtime
> data flow. Notation in diagrams/schemas is illustrative, not prescriptive.

## Overview

The architecture is **hexagonal (ports & adapters)** around a **kernel**. The kernel exposes a
**plugin boundary** made of two protocols and depends on a fixed set of **ports** that the host
stack fills with **adapters**. Plugins plug into the boundary; adapters plug into the ports.
Neither the kernel nor a plugin knows the concrete stack behind a port.

```
                          ┌───────────────────────────────────────────────┐
                          │                    KERNEL                      │
   user ──▶ UI Host ─────▶│  launcher · entitlement gate · run lifecycle   │
     ▲        (port)      │  · confidence scoring · trace fan-out          │
     │                    │                                                │
     │   trace stream     │   ┌────────────── PORTS ──────────────────┐    │
     └────────────────────┤   │ Durable Exec · Run Store · Trace Chan │    │
                          │   │ Identity/Entitlement · Model Access   │    │
                          │   │ Capability Client                     │    │
                          │   └───────────────────────────────────────┘    │
                          │                                                │
                          │        ── plugin boundary (2 protocols) ──     │
                          │   (A) App Contract      (B) Capability Protocol│
                          └──────────┬────────────────────────┬───────────┘
                                     │                         │
                        declarative  │                         │ machine (MCP)
                        manifest     │                         │ tools/resources
                                     ▼                         ▼
                          ┌────────────────────┐   ┌──────────────────────────┐
                          │  in-process plugin  │   │  out-of-process plugin   │
                          │  (same runtime)     │   │  (remote capability      │
                          │                     │   │   endpoint, any language)│
                          └────────────────────┘   └──────────────────────────┘
```

## The plugin boundary: two protocols

### (A) App Contract — declarative

Carries what the Capability Protocol cannot. A plugin registers a **manifest** describing:
its identity, its **kind** (in-process | out-of-process), its **agency** (thin-toolset |
self-agent) and which side owns the model, its **UI entrypoint**, its **data shape + ownership
rule**, its **run wiring** (how a request becomes a durable run), its **auth requirement**, and
its **confidence contract**. Full schema in [`02-plugin-manifest.md`](02-plugin-manifest.md).

### (B) Capability Protocol — machine

The agent-tooling surface: the tools, resources, and prompts the reasoning loop calls, plus the
**authorization handshake** that gates connection. **Reference binding = MCP.** The kernel is a
Capability *client/host*; a plugin exposes a Capability *server* (an in-process plugin exposes
the same interface via a local adapter, so callers cannot tell the difference).

> **Rule:** UI, persistent data, ownership, and run lifecycle travel on (A). Tools, resources,
> prompts, and entitlement travel on (B). Nothing crosses over.

## Agency modes (per-plugin, declared in the manifest)

| Mode | Reasoning loop runs in… | Model owned by… | Capability surface exposed |
|------|-------------------------|-----------------|----------------------------|
| **thin-toolset** | the **kernel** | the kernel | many **fine-grained** tools the kernel's loop calls |
| **self-agent** | the **plugin** | the **plugin** | one **coarse** `invoke(task) → result` entry; internals opaque |

Both modes are legal on either *kind* (in-process or remote). This is the "either, per-plugin"
decision — a plugin author picks the mode that fits their app.

## The invariant that makes it all uniform: invoke through Durable Execution

**However a plugin runs, the kernel invokes it from inside its Durable-Execution boundary.**

- A **thin-toolset** plugin appears as *many fine-grained* durable steps — one per tool call —
  inside the kernel's reasoning loop.
- A **self-agent** plugin appears as *one coarse* durable step — the `invoke` call — whose
  internals the kernel does not see.

Because every plugin call is a durable step, **retries, run state, token/cost accounting, and
the trace are owned by the kernel** and behave identically for local and remote, thin and
self-agent plugins. This is the single most important structural rule (Concept Principle 3).

```
request ──▶ kernel creates RUN (Run Store) ──▶ Durable Execution starts
             │
             ├─ thin-toolset: loop { model turn (Model Access)
             │                       → tool call = durable step → Capability Client → plugin }
             │
             └─ self-agent:  one durable step → Capability Client → plugin.invoke(task)
             │
             ├─ each step emits trace events (Trace Channel) ──▶ UI Host (live)
             ▼
        kernel computes CONFIDENCE from observable signals
             ▼
        kernel finalizes RUN result (Run Store, owner-scoped) ──▶ UI Host
```

## Ports (contract summary; full detail in [`03-kernel-contract.md`](03-kernel-contract.md))

| Port | Kernel uses it to… | MUST guarantee |
|------|--------------------|----------------|
| **Durable Execution** | run a task with retries + durable state | a run survives worker restart; steps are retriable; no lost/duplicated finalization |
| **Run Store** | persist runs/results/traces | per-owner row authorization; a generic (non-leaking) error on failure |
| **Trace Channel** | stream progress to UI | near-real-time delivery scoped to the run's owner |
| **Identity & Entitlement** | know the user + their plugin rights | a verifiable identity; an entitlement decision per plugin |
| **Model Access** | perform inference | provider-isolated; returns token/cost usage for accounting |
| **UI Host** | render entrypoints + launcher | shows only entitled plugins; renders each plugin's declared entry |
| **Capability Client** | speak the Capability Protocol | authorization handshake before any tool call; timeouts/error mapping |

## Data flow — happy path (numbered)

1. User authenticates via **Identity** port; kernel resolves **entitlements**.
2. **UI Host** renders the launcher showing **only entitled** plugins (from their manifests).
3. User opens a plugin's declared **UI entrypoint** and submits a request.
4. Kernel writes a **Run** row (owner = user) via **Run Store** and starts **Durable Execution**.
5. For each plugin the run needs, kernel connects its **Capability** endpoint (authorization
   handshake carries the user's entitlement token). Unentitled → never connected.
6. Execution proceeds per agency mode; every plugin call is a **durable step**; every step
   emits **trace** events.
7. Kernel derives **confidence** from observable signals and finalizes the **Run** result
   (owner-scoped) — UI updates live via the **Trace Channel**.

## Error & failure model (stack-agnostic requirements)

- A failed durable step MUST be retriable without duplicating side effects the plugin declared
  idempotent; non-idempotent effects MUST be guarded by the plugin.
- A plugin (or capability endpoint) that is unreachable or unauthorized MUST fail the run with a
  **generic** user-facing error — never leak provider/internal detail into an owner-readable row.
- A `self-agent` plugin that never returns MUST be bounded by a kernel-side timeout on the
  `invoke` step; the run finalizes as failed on timeout.
- Loss of the Trace Channel MUST NOT corrupt the run; the final result is authoritative and
  readable from the Run Store even if live trace was missed.

## Sequence diagram (self-agent remote plugin)

```
User    UIHost   Kernel        RunStore  DurableExec  CapClient   RemotePlugin  Model
 │  open  │         │              │          │           │            │          │
 │───────▶│ submit  │              │          │           │            │          │
 │        │────────▶│ create run   │          │           │            │          │
 │        │         │─────────────▶│          │           │            │          │
 │        │         │ start        │          │           │            │          │
 │        │         │─────────────────────────▶│          │            │          │
 │        │         │ step: invoke(task)       │          │            │          │
 │        │         │                          │─ authz ─▶│            │          │
 │        │         │                          │          │── invoke ─▶│          │
 │        │         │                          │          │            │─ model ─▶│
 │        │         │                          │          │            │◀─ resp ──│
 │        │         │                          │◀─ result ─────────────│          │
 │        │◀─ trace events (throughout) ───────┤          │            │          │
 │        │         │ confidence + finalize    │          │            │          │
 │        │         │─────────────▶│ (owner-scoped result) │            │          │
 │◀── live result ──┤              │          │           │            │          │
```

## Acceptance Criteria

- [ ] The kernel compiles/runs with **zero references** to any concrete stack technology; all
      stack contact is through the seven ports.
- [ ] A plugin's *kind* and *agency mode* are read from its manifest; changing either requires
      **no kernel code change**.
- [ ] Every plugin invocation is observable as one or more **durable steps** with retry and a
      trace, verifiable for a thin in-process plugin and a self-agent remote plugin alike.
- [ ] Removing a plugin's registration removes its UI entry, its capability connection, and its
      run wiring, with **no other edits**.
- [ ] An unentitled user's session shows the plugin neither in the launcher nor as a callable
      tool (endpoint never connected).

## References

- Concept & principles: [`00-concept.md`](00-concept.md)
- App Contract schema: [`02-plugin-manifest.md`](02-plugin-manifest.md)
- Port contracts: [`03-kernel-contract.md`](03-kernel-contract.md)
- Auth handshake: [`04-auth-and-entitlements.md`](04-auth-and-entitlements.md)
