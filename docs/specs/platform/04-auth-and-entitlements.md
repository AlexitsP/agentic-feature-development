# 04 — Auth & Entitlement Specification

**Status:** Draft
**Owner:** Patrik Alexits
**Created:** 2026-07-10
**Last Updated:** 2026-07-10

> Defines the trust boundary: how a user is identified, how their **right to use a plugin** is
> decided, and how that right gates the **connection** to a plugin's capability endpoint.
> Stack-agnostic; the reference authorization binding is **OAuth 2.1 as used by MCP**.

## Overview

The core auth idea is **connection is entitlement**: a plugin becomes available to a user only
if the kernel can obtain an authorized capability session for that user against that plugin. If
it cannot, the plugin's tools and its UI entry are **absent**, not merely hidden. This makes
entitlement a structural property, not a cosmetic filter.

Three layers, each with a single responsibility:

1. **Identity** — *who is this?* (the Identity port)
2. **Entitlement** — *which plugins may they use?* (the Entitlement port + manifest `auth`)
3. **Capability authorization** — *prove that right to the plugin at connect time* (the
   Capability Client's authorization handshake; reference = MCP OAuth).

## Layer 1 — Identity

- The kernel MUST establish a **verifiable principal** for a session via the Identity port.
- **Anonymous/guest** principals are permitted **only** for plugins whose manifest is `open`
  (`data.ownership = open`, `auth.requires_auth = false`). Any `owner_scoped` plugin MUST have
  an authenticated principal, because its data is keyed to an owner.
- The principal MUST be the basis for owner-scoping in the Run Store (Concept Principle 6).

## Layer 2 — Entitlement

- The manifest declares `auth.requires_auth`, an optional `entitlement` string, and the
  capability `scopes` it needs (see [`02`](02-plugin-manifest.md)).
- The Entitlement port resolves, for a principal, the set of entitlements they hold.
- A plugin is **available** to a user iff:
  - `auth.requires_auth == false` (open), **or**
  - the user is authenticated **and** (`auth.entitlement == null` **or** the user holds
    `auth.entitlement`).
- The kernel MUST filter the launcher and the connectable-plugin set by availability. An
  unavailable plugin MUST NOT be connected (Layer 3 is never reached for it).

### The auth↔data invariant (do not violate)

`auth.requires_auth` **MUST equal** `data.ownership == "owner_scoped"`. Owner-scoped data with
an unauthenticated UI cannot write; open data behind an auth wall needlessly blocks the demo.
The kernel SHOULD reject a manifest that breaks this at registration time. *(This is the exact
class of bug that bit the reference implementation — an owner-scoped table paired with an
unauthenticated entrypoint.)*

## Layer 3 — Capability authorization (connect time)

When the kernel connects a plugin's capability endpoint, the **Capability Client** performs an
authorization handshake carrying the user's authority. Reference binding: **OAuth 2.1** as
specified by MCP.

```
Kernel                         Authorization                 Plugin (Capability server)
  │  need session for plugin P   │                                  │
  │  (user U is entitled)        │                                  │
  │  tokenFor(U, P) ────────────▶│  mint scoped token (P.scopes)    │
  │◀──────────── capabilityToken │                                  │
  │  connect(P.endpoint, token) ───────────────────────────────────▶│  validate token + scopes
  │◀───────────────────────────── session (or 401/403) ─────────────│
  │  callTool / invoke (only if session established)                │
```

Requirements:

- The kernel MUST NOT call any tool or `invoke` before a session is established.
- The token MUST be **scoped to the plugin and the granted scopes**; a plugin MUST reject calls
  outside its granted scopes.
- For `out_of_process` plugins the token crosses a **trust boundary**; the token MUST be
  short-lived and audience-restricted to that plugin (a leaked token must not grant access to
  other plugins or the kernel).
- For `in_process` plugins the handshake MAY be a local capability check, but the **same
  entitlement decision** MUST gate it (no shortcut that skips entitlement).
- A failed handshake MUST fail closed: the plugin is treated as unavailable for the session.

## Data residency & PII posture (portable requirement)

- The specs do not mandate a region or provider, but a conformant deployment MUST be able to
  state **where run data and model inference occur** and keep them within its required
  jurisdiction. (In the reference implementation this is why the model provider is regionally
  pinned.)
- Owner-scoped data MUST remain readable only by its owner across every port, including in the
  Trace Channel.
- A plugin going `out_of_process` MUST NOT weaken residency: either the plugin runs within the
  same jurisdiction, or the data it receives is minimized/authorized accordingly.

## Threat notes (informative)

- **Confused-deputy:** the kernel must not use its *own* authority to call a plugin on behalf of
  a user who lacks entitlement — always use a user-scoped token.
- **Token replay across plugins:** mitigated by audience-restricting tokens per plugin.
- **Trace leakage:** subscriptions MUST be owner-scoped; a run's events never reach another user.
- **Error leakage:** provider/internal errors MUST be genericized before entering owner-readable
  rows or traces.

## Acceptance Criteria

- [ ] An unauthenticated user cannot start a run on an `owner_scoped` plugin (write denied), and
      the plugin is absent from their launcher.
- [ ] A user without a required `entitlement` never causes the plugin's capability endpoint to
      be connected.
- [ ] A capability token minted for plugin A is **rejected** by plugin B (audience restriction).
- [ ] A tool/`invoke` call attempted before a session is established is refused.
- [ ] Two different users each see only their own runs and only their own trace streams.
- [ ] A manifest violating the `requires_auth ⇔ owner_scoped` invariant is rejected at
      registration.

## References

- Manifest `auth` fields: [`02-plugin-manifest.md`](02-plugin-manifest.md)
- Identity/Entitlement + Capability Client ports: [`03-kernel-contract.md`](03-kernel-contract.md)
- Concept Principle 5 (entitlement gates connection): [`00-concept.md`](00-concept.md)
