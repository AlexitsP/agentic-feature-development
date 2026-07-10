# 03 — Kernel Contract & Ports Specification

**Status:** Draft
**Owner:** Patrik Alexits
**Created:** 2026-07-10
**Last Updated:** 2026-07-10

> Defines what the **kernel** must do and the **ports** it depends on. Ports are abstract; a
> stack supplies **adapters**. Method signatures below are illustrative pseudo-interfaces —
> the *obligations* are normative, the *syntax* is not. Concrete adapter examples are in
> [`05-porting-guide.md`](05-porting-guide.md).

## Overview

The kernel is the small, stable core. It owns: the plugin registry, the run lifecycle,
confidence scoring, entitlement gating, trace fan-out, and the two-protocol boundary. It owns
**no domain logic** and **no concrete technology** — it reaches every external capability
through a **port**. A conformant kernel depends on exactly the seven ports below and nothing
else stack-specific.

## Kernel responsibilities (MUST)

1. **Registry** — hold validated manifests; enforce the field rules in [`02`](02-plugin-manifest.md);
   expose the set of plugins *entitled for the current user*.
2. **Entitlement gate** — before connecting any plugin's capability endpoint, confirm the user
   is entitled; never connect otherwise (Concept Principle 5).
3. **Run lifecycle** — turn a validated request into a durable run; drive it per the plugin's
   agency mode; finalize exactly once with a validated result.
4. **Uniform invocation** — invoke every plugin call inside the Durable-Execution boundary so
   retries/state/accounting/trace are centralized (Concept Principle 3).
5. **Confidence** — compute a confidence value from the manifest's declared **observable**
   signals and attach it to every result (Principle 4).
6. **Trace fan-out** — emit run/step events to the Trace Channel scoped to the run's owner.
7. **Isolation** — persist runs/results via the Run Store with per-owner authorization when the
   plugin is owner-scoped (Principle 6).
8. **Generic failure** — on any error, finalize the run with a non-leaking, generic user-facing
   error; never write provider/internal detail to an owner-readable row.

## Kernel MUST NOT

- Depend on a specific plugin, or import plugin internals.
- Carry UI, data schema, or lifecycle over the Capability Protocol.
- Trust a model's self-reported confidence.
- Connect a capability endpoint for an unentitled user.
- Contain stack-specific code outside a port adapter.

## The seven ports

Each port lists its **obligation** (what a conformant adapter must guarantee). Signatures are
illustrative.

### 1. Durable Execution

```
startRun(runId, plan) -> void          # begins a durable execution
step(name, fn, {retry, idempotent}) -> result   # a retriable durable unit of work
```
- **MUST** persist enough state that a run survives a worker/process restart and resumes.
- **MUST** retry a failed step per policy without duplicating side effects the caller marked
  idempotent; non-idempotent work MUST be guarded by the caller.
- **MUST** guarantee a run is finalized **exactly once** (no lost or double finalization).
- **MUST** allow bounding a step by timeout (used for `self_agent.invoke`).

### 2. Run Store

```
createRun(run{owner, plugin, request}) -> runId
appendTrace(runId, event) -> void      # may also fan out via Trace Channel
finalizeRun(runId, result | genericError, confidence) -> void
getRun(runId, asUser) -> run | denied  # owner-scoped read
```
- **MUST** enforce **per-owner authorization** on reads when the plugin is `owner_scoped`: a
  user reads only their own runs.
- **MUST** store results/traces durably and independently of the live Trace Channel (the store
  is the source of truth).
- **MUST NOT** persist secrets or raw provider errors in owner-readable fields.

### 3. Trace Channel

```
publish(runId, event) -> void
subscribe(runId, asUser) -> stream<event>
```
- **MUST** deliver events near-real-time to the run's owner and **only** its owner.
- Loss of the channel **MUST NOT** corrupt the run; the Run Store result remains authoritative.

### 4. Identity & Entitlement

```
authenticate(request) -> principal            # who the user is (verifiable)
entitlements(principal) -> set<entitlement>   # which plugins/rights they hold
tokenFor(principal, plugin) -> capabilityToken # to authorize a capability connection
```
- **MUST** produce a verifiable principal; anonymous/guest identities are allowed **only** where
  a plugin is `open` (not owner-scoped).
- **MUST** resolve an entitlement decision per plugin; the kernel uses it to gate connection.
- **MUST** be able to mint a token the Capability Client presents in its authorization handshake
  (see [`04`](04-auth-and-entitlements.md)).

### 5. Model Access

```
infer(request) -> {output, usage}   # usage = tokens/cost for accounting
```
- **MUST** be provider-isolated behind this one port (swapping providers touches only the adapter).
- **MUST** return usage so the kernel can account cost per run/step.
- Used by the kernel for `thin_toolset` plugins; `self_agent` plugins own their own model and do
  **not** use this port (their model is opaque to the kernel).

### 6. UI Host

```
mount(pluginRoute, viewDescriptor | embedSurface) -> void
launcher(entitledPlugins) -> view
```
- **MUST** show **only entitled** plugins in the launcher.
- **MUST** render each plugin's declared entrypoint (`render: native` from a view descriptor, or
  `embed` from a plugin-served surface).
- **MUST** reflect live run progress from the Trace Channel.

### 7. Capability Client

```
connect(capabilityRef, capabilityToken) -> session   # performs authz handshake
listTools(session) -> tool[]
callTool(session, name, args) -> result               # always wrapped in a Durable step
invoke(session, task) -> result                       # coarse entry for self_agent
```
- **MUST** perform the authorization handshake **before** any tool/invoke call; refuse on
  failure.
- **MUST** present an identical interface for in-process (adapter) and out-of-process (remote)
  plugins.
- **MUST** map protocol/transport errors to a generic failure (no leak) and honor step timeouts.

## Port dependency matrix

| Kernel responsibility | Durable Exec | Run Store | Trace | Identity/Entitlement | Model | UI Host | Cap. Client |
|-----------------------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Registry / entitlement gate |  |  |  | ● |  | ● |  |
| Run lifecycle | ● | ● | ● |  | ○ |  | ● |
| Uniform invocation | ● |  |  |  | ○ |  | ● |
| Confidence |  | ● |  |  |  |  |  |
| Trace fan-out |  | ● | ● |  |  | ● |  |
| Isolation |  | ● |  | ● |  |  |  |

● = required · ○ = required only for `thin_toolset` plugins (kernel-owned model)

## Stability & versioning

- The kernel contract (ports + the manifest schema it accepts) is **versioned**. A breaking
  change is a heavyweight, reviewed decision because **every plugin depends on it** (Concept
  Principle 2) — in the reference repo this is an ADR-worthy change.
- Plugins declare `capability.protocol_min` and their own `version`; the kernel MUST refuse a
  plugin whose required protocol version it cannot speak.

## Acceptance Criteria

- [ ] Every kernel↔stack interaction goes through exactly one of the seven ports; a grep for
      stack SDKs finds them **only** inside adapters.
- [ ] Swapping any single adapter (e.g. a different durable-execution engine) requires **no
      change** to kernel code or to any plugin manifest.
- [ ] A run survives killing the execution worker mid-run and resumes to a correct finalize.
- [ ] An owner-scoped run is unreadable by a different user through the Run Store port.
- [ ] A `self_agent` plugin that hangs is terminated by the `invoke_timeout` and the run
      finalizes as a generic failure.
- [ ] Disabling Model Access breaks only `thin_toolset` plugins; `self_agent` plugins still run.

## References

- Ports mapped to concrete tech: [`05-porting-guide.md`](05-porting-guide.md)
- Manifest fields these ports consume: [`02-plugin-manifest.md`](02-plugin-manifest.md)
- Auth handshake detail: [`04-auth-and-entitlements.md`](04-auth-and-entitlements.md)
