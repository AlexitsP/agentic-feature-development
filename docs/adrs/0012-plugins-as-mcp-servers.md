# ADR-0012: Plugins as MCP servers (kernel-as-MCP-host)

- **Status:** Proposed
- **Date:** 2026-07-09
- **Deciders:** Patrik Alexits
- **Supersedes / Superseded by:** Extends ADR-0008 (feature-plugin architecture); does not supersede it.

## Context

ADR-0008 gave us a **kernel + feature-plugin** platform, but the plugin boundary is
**compile-time and in-process**: a feature is a Python package baked into the worker image,
plus one line in `temporal/src/features/registry.py`, plus a mirrored line in
`frontend/src/features/registry.ts`. That couples every plugin to the kernel's build and
deploy pipeline — a new plugin cannot ship without a commit to the kernel repo and a rebuild
of the shared worker/frontend images.

We want to push harder on the platform's actual goal: **enabling agentic development** — a
team (or an autonomous agent, or Claude) authoring a whole "app" and standing it up **without
touching the kernel**, in any language, deployed on its own cadence. The industry standard for
an agent host consuming external capabilities is the **Model Context Protocol (MCP)**, and MCP
now carries an **OAuth 2.1 authorization** spec, which matches the intent that *which plugs a
user sees is driven by that user's rights*.

The trap to avoid: **MCP is a tool/resource/prompt protocol for an agent's brain — it does not
carry an application's UI, data schema, workflow lifecycle, or auth posture.** Our "apps" are
more than tools: each has a route/wizard (UI), a Temporal workflow (durable lifecycle), a
Supabase table + RLS (data), a `requires_auth` gate, and a confidence contract (ADR-0009).
Bending MCP to carry those would forfeit the interoperability that is the whole reason to adopt
a standard.

## Decision

We split the plugin boundary into **two protocols**, and we make the kernel an **MCP host**.

1. **App Contract (ours) — the existing `FeatureManifest`, extended.** Continues to carry the
   *app surface* MCP cannot: UI entrypoint, data tables + RLS posture, `requires_auth`, and the
   confidence contract. Two new fields:
   - `kind: "in_process" | "mcp"` — where the plugin's capabilities live. `in_process` is
     exactly today's behaviour (unchanged, still supported). `mcp` adds
     `{ mcp_url, auth: <oauth_config>, ui: <how the kernel links/renders its entrypoint> }`.
   - `agent: { mode: "thin_toolset" | "self_agent", model_owner: "kernel" | "plugin" }` —
     declares **where the reasoning loop runs** (per the "either, per-plugin" decision):
     - `thin_toolset` → the plugin exposes fine-grained MCP tools; the **kernel's** Temporal
       workflow + LLM loop drives them (kernel owns the model).
     - `self_agent` → the plugin runs its own reasoning loop and owns its own model/creds; it
       exposes a **single coarse `invoke(task)` MCP tool** whose internals are opaque to the
       kernel.

2. **MCP — the agent-tooling leg.** The kernel is an MCP client/host. A remote plugin is an MCP
   server. Regardless of `agent.mode`, **the kernel invokes an MCP plugin from inside a Temporal
   activity**, so durability, retries, token accounting, and the realtime trace (ADR-0009) stay
   centralized: a `thin_toolset` plugin appears as many fine-grained tool-call activities within
   the kernel loop; a `self_agent` plugin appears as one coarse `invoke` activity.

3. **Auth-driven connection via MCP OAuth.** Per-user rights decide *which MCP servers get
   connected for that session*. This maps onto the existing per-feature `requires_auth`
   (ADR-0011): the kernel obtains/propagates the user's token to each MCP server over the MCP
   OAuth flow; a user without the entitlement never has that server connected, so its UI entry
   and tools are simply absent.

4. **Hybrid migration.** Both `kind`s coexist. We migrate **one** existing feature to an MCP
   server as a proof of the seam and leave the other in-process. No big-bang rewrite.

The kernel remains the **Temporal + auth + UI host**; MCP plugins are capabilities it consumes,
not independent runtimes it merely routes to.

## Consequences

- **Easier (the prize):** a plugin can be authored, deployed, and versioned **entirely outside
  the kernel repo**, in any language — the ideal substrate for agent-built plugins. Discovery is
  runtime and auth-gated, not a kernel commit + image rebuild.
- **Runtime cost (accepted):** out-of-process means network hops + serialization + per-plugin
  process/ops overhead vs. an in-process call. We trade latency and operational surface for
  plugin autonomy. In-process `kind` stays available for latency-sensitive or trivial plugins.
- **New obligations on the kernel contract:** it must speak MCP (host/client + OAuth token
  propagation) and wrap MCP calls as durable Temporal activities with trace + token capture.
  This is kernel-contract surface, hence this ADR.
- **Auth across a trust boundary:** entitlement now propagates to external servers; a
  misconfigured plugin OAuth scope is a new failure mode. Mitigated by reusing MCP's spec rather
  than inventing a scheme, and by the kernel refusing to connect a server it can't authorize.
- **Observability discipline:** `self_agent` plugins are opaque inside `invoke`; their internal
  steps won't show in the kernel's trace unless the plugin emits its own. Documented as a known
  limitation of `self_agent` mode.
- **Data stays kernel-side:** run/trace tables + RLS remain in the kernel's Supabase (App
  Contract), so RLS/data-residency guarantees are unchanged by a plugin going remote.

## Alternatives considered

- **One "unified protocol" = MCP for everything (incl. UI/data):** rejected — MCP has no UI or
  data-schema surface; forcing it there produces a non-standard dialect and loses interop.
- **Full microservices, each plugin its own workflow engine (plugin owns the loop entirely):**
  rejected for now — maximal autonomy but duplicates durability/observability per plugin and
  makes auth/trace far harder; `self_agent`-over-a-coarse-`invoke`-activity gets most of the
  autonomy while keeping durability central.
- **Stay in-process only (status quo of ADR-0008):** rejected as the end state — it blocks the
  agentic-development goal — but **retained as one of the two supported `kind`s**.
- **Big-bang migrate all features to MCP:** rejected — hybrid migration de-risks by proving the
  seam on one feature first.

## Evidence

- Extends ADR-0008 (feature-plugin architecture); companions ADR-0009 (confidence),
  ADR-0011 (per-feature auth gate — the `requires_auth` this reuses).
- To be implemented as a spike: extend `FeatureManifest` (`kind`, `agent`) + the frontend
  registry mirror; add an MCP host client to the kernel invoked from a Temporal activity;
  re-express one existing feature (`program_evaluator` or `study_planner`) as an external MCP
  server behind MCP OAuth; keep the other in-process. Verify end-to-end (auth-gated discovery +
  a real run pending→done through the remote plugin).
- Standard: Model Context Protocol (tools/resources/prompts + OAuth 2.1 authorization).
