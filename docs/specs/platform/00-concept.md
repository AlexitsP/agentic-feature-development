# 00 — Concept Specification: The Agentic Plugin Platform

**Status:** Draft
**Owner:** Patrik Alexits
**Created:** 2026-07-10
**Last Updated:** 2026-07-10

> This is a **stack-agnostic concept spec**. It defines *what* the platform is, *why* it is
> shaped this way, the principles it must obey, and the vocabulary the rest of the set uses.
> No technology is prescribed here. Concrete bindings live in [`05-porting-guide.md`](05-porting-guide.md).

## Overview

An **Agentic Plugin Platform** is a small, stable **kernel** whose product *is* being a host
for pluggable **agentic apps** ("plugins"). The kernel owns the generic, boring, safety-critical
machinery every agentic app needs — running a task durably, talking to a model, streaming
progress, scoring answer confidence, authenticating the user, and rendering an entrypoint.
Each plugin supplies only what is unique to it: its domain tools, its data shape, and its UI.

The defining move is that a plugin is consumed through **two protocols**, because one protocol
cannot honestly carry both halves of an "app":

1. A **Capability Protocol** — a *machine* protocol for the agent's brain: the tools,
   resources, and prompts the kernel's (or the plugin's) reasoning loop calls. This is where a
   standard belongs; the reference binding is **MCP (Model Context Protocol)**.
2. An **App Contract** — a *declarative* descriptor for everything the Capability Protocol
   does **not** carry: the plugin's UI entrypoint, its persistent data shape and ownership
   rules, its run/lifecycle wiring, its auth requirement, and its answer-quality contract.

Keeping these separate is the whole point: it lets the agent-tooling half ride an
interoperable standard while the app half stays a small contract the host fully controls.

## Problem Statement

### The problem

Teams keep rebuilding the same agentic scaffolding — durable execution, model access, live
tracing, auth, result-quality signals — once per app. And when they *do* factor it into a
shared core, they usually couple every app to that core at **build time**: adding an app means
editing the core's registration lists and rebuilding one shared binary. That coupling blocks
the thing we actually want: letting a **separate team, or an autonomous agent, author and ship
a whole app without touching the core**.

### Why the obvious fix is a trap

The tempting fix is "make everything an MCP server and call it a day." But MCP (and any
capability protocol like it) describes **tools, resources, and prompts** — the agent's
machine surface. It has **no concept of a UI, a data schema, ownership/row-authorization, or a
durable run lifecycle**. An agentic *app* has all of those. Forcing one protocol to carry the
UI and data surface produces a non-standard dialect and forfeits the interoperability that was
the only reason to adopt a standard.

### Desired state

A host where:
- Adding an app is a **runtime, declarative** act (register a manifest + connect a capability
  endpoint), not a core-code edit and rebuild.
- Apps can live **out-of-process, in any language, deployed on their own cadence** — or
  in-process when latency matters — behind the *same* contract.
- **Who can use which app is decided by the user's rights**, enforced at connection time.
- The core's guarantees (durability, tracing, confidence, data isolation) hold **uniformly**
  across every app, local or remote.

## Goals

- Define a **kernel/plugin boundary** where a plugin is a self-contained unit consumed through
  the two protocols, and adding/removing/toggling one touches only that plugin + one
  declarative registration.
- Make the concept **portable**: expressed as abstract *ports* (durable execution, run store,
  trace channel, identity/entitlement, model access, UI host) that any stack fills with
  *adapters*.
- Support **per-plugin agency**: a plugin may be a *thin toolset* the kernel's loop drives, or
  a *self-contained agent* that owns its own reasoning and model.
- Support a **hybrid boundary**: in-process and out-of-process plugins behind one contract, so
  migration is incremental.
- Make **entitlement** first-class: connection to a plugin is gated on the user's rights via a
  standard authorization flow.
- Preserve **uniform guarantees** — durability, observability, answer-confidence, and data
  isolation — regardless of where a plugin runs.

## Non-Goals

- Prescribing any technology (database, workflow engine, UI framework, model provider, cloud,
  or language). All of that is adapter detail.
- Specifying the *internal* implementation of a plugin's domain logic — only its contract with
  the kernel.
- A marketplace, billing, or plugin-signing/distribution system — additive, out of scope here.
- Replacing the Capability Protocol standard — this set binds to MCP by reference but the
  architecture survives swapping it, provided the replacement carries tools/resources/prompts
  and an authorization story.
- Cross-plugin composition by direct import — plugins never depend on each other; any
  composition flows through the kernel's run substrate.

## Principles (the invariants a conformant platform must not violate)

1. **Two protocols, never one.** The agent-tooling surface and the app surface are separate
   contracts. Do not push UI/data/lifecycle onto the Capability Protocol.
2. **The kernel is small and stable; plugins are many and volatile.** The kernel never depends
   on a specific plugin. Changing the kernel contract is a heavyweight, reviewed decision
   because every plugin depends on it.
3. **Durability is centralized.** However a plugin runs (thin or self-agent, local or remote),
   the kernel invokes it behind its **durable-execution boundary**, so retries, state,
   token/cost accounting, and the trace are owned by the kernel — not duplicated per plugin.
4. **Confidence is computed from observable signals, never the model's self-report.** Answer
   quality is derived from things the kernel can see (grounding coverage, input completeness,
   source count), not from the model claiming it is confident.
5. **Entitlement gates connection.** A user who lacks the right to a plugin never has its
   capability endpoint connected; therefore its tools and its UI entry are simply absent —
   not merely hidden.
6. **Data isolation is the kernel's job.** Persistent run/result data and its per-owner
   authorization live behind the kernel's **run-store port**, so isolation guarantees do not
   change when a plugin moves out-of-process.
7. **A plugin declares, it does not reach in.** Everything the kernel needs to host a plugin is
   in its App Contract. A plugin cannot edit kernel internals to install itself.

## Vocabulary (used across the whole set)

| Term | Meaning |
|------|---------|
| **Kernel** | The stable host and the product. Owns the ports and the two-protocol boundary. |
| **Plugin / Agentic App** | A self-contained unit of capability consumed via the two protocols. |
| **Capability Protocol** | The machine protocol for agent tools/resources/prompts. Reference binding: **MCP**. |
| **App Contract / Manifest** | The declarative descriptor carrying UI + data + lifecycle + auth. See [`02`](02-plugin-manifest.md). |
| **Port** | An abstract capability the kernel requires from the host stack (see below). |
| **Adapter** | A concrete implementation of a port on a specific stack. |
| **Agency mode** | Whether a plugin is a *thin toolset* (kernel drives the loop) or a *self-agent* (plugin owns the loop). |
| **Kind** | Where a plugin runs: *in-process* or *out-of-process (remote capability endpoint)*. |
| **Run** | One durable execution of a plugin task, from request to final result, with a trace. |
| **Entitlement** | A user's right to connect to and use a given plugin. |
| **Confidence** | An observable-signal score attached to every result (Principle 4). |

### The ports (detailed in [`03-kernel-contract.md`](03-kernel-contract.md))

- **Durable Execution** — run a long agentic task with retries and durable state.
- **Run Store** — persist run rows, results, and traces; enforce per-owner authorization.
- **Trace Channel** — stream run progress/steps to the UI in near-real-time.
- **Identity & Entitlement** — establish who the user is and which plugins they may use.
- **Model Access** — perform model inference (used by the kernel and/or by plugins).
- **UI Host** — render each plugin's declared entrypoint and the launcher.
- **Capability Client** — speak the Capability Protocol to (remote or local) plugins,
  including its authorization handshake.

## Success Criteria (how you know a build of this concept is correct)

- [ ] A new plugin can be added with **no edit to kernel source** — only a manifest
      registration and (for remote plugins) a reachable capability endpoint.
- [ ] The **same plugin contract** admits both an in-process plugin and an out-of-process one;
      swapping a plugin's *kind* does not change the kernel.
- [ ] A user **without entitlement** to a plugin sees no UI entry and cannot invoke its tools,
      because its capability endpoint is never connected for that session.
- [ ] Every result carries a **confidence value derived from observable signals**; a
      no-grounding / empty-input result is never classified High.
- [ ] Durability, tracing, and per-owner data isolation hold identically for a thin in-process
      plugin and a self-agent remote plugin.
- [ ] The Capability Protocol binding can be named and pointed at a spec (MUST be a real
      standard, reference = MCP), and the App Contract is fully specified by [`02`](02-plugin-manifest.md).

## References

- Architecture: [`01-architecture.md`](01-architecture.md)
- App Contract: [`02-plugin-manifest.md`](02-plugin-manifest.md)
- Kernel & ports: [`03-kernel-contract.md`](03-kernel-contract.md)
- Auth & entitlement: [`04-auth-and-entitlements.md`](04-auth-and-entitlements.md)
- Porting: [`05-porting-guide.md`](05-porting-guide.md)
- Stack-bound lineage: ADR-0008 (feature-plugin architecture), ADR-0012 (plugins as MCP servers).
