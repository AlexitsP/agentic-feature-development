# 02 — App Contract Specification (the Plugin Manifest)

**Status:** Draft
**Owner:** Patrik Alexits
**Created:** 2026-07-10
**Last Updated:** 2026-07-10

> The **App Contract** is the declarative half of the plugin boundary — everything the
> Capability Protocol cannot carry. This spec defines its fields, their meaning, and the rules
> a conformant manifest MUST satisfy. The schema notation below is **illustrative**; express it
> in whatever your stack prefers (JSON Schema, a typed struct, a config file). The *fields and
> rules* are normative; the *syntax* is not.

## Overview

A plugin registers exactly one **manifest**. The kernel reads it to host the plugin: to show
it in the launcher, connect its capability endpoint, wire its runs, isolate its data, gate its
access, and score its results. **If it is not in the manifest, the kernel does not know about
it.** A plugin MUST NOT need to edit kernel source to install itself (Concept Principle 7).

## Manifest schema (illustrative notation)

```
Manifest {
  # ---- identity ----
  key            : string   # stable, unique, namespace-safe slug (e.g. "program_evaluator")
  title          : string   # human label for the launcher/UI
  version        : semver    # the manifest/contract version of THIS plugin
  description    : string   # one line; shown in the launcher

  # ---- placement ----
  kind           : "in_process" | "out_of_process"
  capability     : CapabilityRef        # how to reach the Capability Protocol surface
  agent          : AgencySpec

  # ---- app surface (what the Capability Protocol can't carry) ----
  ui             : UiEntry              # how the kernel renders/links the plugin entrypoint
  data           : DataSpec             # persistent shape + ownership rule
  run            : RunSpec              # how a request becomes a durable run
  auth           : AuthSpec             # entitlement requirement
  confidence     : ConfidenceSpec       # which observable signals score this plugin's results

  # ---- optional ----
  enabled        : bool = true          # toggle without removing (feature flag)
  tags           : string[] = []
}

CapabilityRef {
  # for out_of_process:
  endpoint       : url?                 # the plugin's Capability (MCP) server URL
  # for in_process:
  adapter        : symbol?              # a local handle the kernel resolves to an in-proc server
  # common:
  protocol       : "mcp"                # the Capability Protocol binding (reference = mcp)
  protocol_min   : semver               # minimum protocol version the plugin requires
}

AgencySpec {
  mode           : "thin_toolset" | "self_agent"
  model_owner    : "kernel" | "plugin"
  # thin_toolset  ⟹ model_owner = "kernel"  (kernel drives the loop)
  # self_agent    ⟹ model_owner = "plugin"  (plugin brings its own model/creds)
  invoke_timeout : duration?            # REQUIRED for self_agent (kernel bounds the invoke step)
}

UiEntry {
  route          : string               # path/slug the UI Host mounts (e.g. "/evaluate")
  render         : "native" | "embed"   # native = UI Host renders from a plugin-provided view
                                        # descriptor; embed = plugin serves its own view surface
  view           : ViewDescriptor?      # for render=native: a stack-neutral description of the
                                        #   input form + result layout (fields, types, labels)
}

DataSpec {
  namespace      : string               # per-plugin prefix for all its persisted entities
  entities       : Entity[]             # logical records the plugin persists via the Run Store
  ownership      : "owner_scoped" | "open"   # owner_scoped ⟹ rows readable only by their owner
}

RunSpec {
  request_shape  : Schema               # the validated input a run starts from
  result_shape   : Schema               # the validated output a run finalizes to
  claim_key      : string               # how the kernel routes/claims this plugin's runs
                                        #   (namespace-unique)
  idempotency    : "idempotent" | "guarded"  # whether steps may be safely retried (see 01 error model)
}

AuthSpec {
  requires_auth  : bool                 # MUST equal (data.ownership == "owner_scoped")
  entitlement    : string?              # the right a user needs (null ⟹ any authenticated user)
  scopes         : string[] = []        # capability-protocol authorization scopes to request
}

ConfidenceSpec {
  signals        : ("grounding_coverage" | "input_completeness" | "source_count" | ...)[]
  # scoring uses ONLY observable signals; the model's self-report is NEVER a signal
}
```

## Field rules (normative)

- **`key`** MUST be globally unique within a kernel and safe as a namespace prefix; it prefixes
  the plugin's data namespace, run claim key, and UI route to prevent collisions.
- **`kind` + `capability`**:
  - `in_process` MUST set `capability.adapter` and MUST NOT require a network endpoint.
  - `out_of_process` MUST set `capability.endpoint` (reachable) and `auth.scopes` sufficient
    for the connection.
  - The kernel MUST treat both identically once connected (an in-process adapter presents the
    same Capability interface).
- **`agent`**:
  - `thin_toolset` ⟹ `model_owner = "kernel"`; the plugin MUST expose fine-grained tools.
  - `self_agent` ⟹ `model_owner = "plugin"`, MUST expose a single coarse `invoke` entry, and
    MUST set `invoke_timeout` (the kernel bounds the step).
- **`auth.requires_auth` MUST equal `data.ownership == "owner_scoped"`.** This is the single
  most common source of silent breakage: an owner-scoped table with an unauthenticated UI can
  never insert. The kernel SHOULD reject a manifest that violates this at registration.
- **`data.ownership = owner_scoped`** ⟹ the Run Store MUST enforce that a row is readable only
  by its owner; the plugin author does not implement this — the kernel/port does.
- **`confidence.signals`** MUST be a non-empty subset of observable signals. A manifest listing
  a self-report signal is non-conformant (Concept Principle 4).
- **`enabled = false`** MUST remove the plugin from the launcher, refuse its runs, and skip its
  capability connection — **without** deleting its data or requiring code changes.

## Lifecycle: register → connect → run → toggle → remove

1. **Register** — the manifest is added to the kernel's registry (one declarative entry). The
   kernel validates it (field rules above). No kernel source edit.
2. **Connect** — on first entitled use, the kernel connects the Capability endpoint (remote) or
   resolves the adapter (in-process), performing the authorization handshake.
3. **Run** — requests validated against `run.request_shape` become durable runs; results
   validated against `run.result_shape`; confidence attached.
4. **Toggle** — `enabled` flips availability with no data loss.
5. **Remove** — deleting the registry entry removes UI/route, capability connection, and run
   wiring. Persistent data removal is a separate, explicit migration (never implicit).

## Worked example (reference plugin, notation only)

```
Manifest {
  key: "program_evaluator"
  title: "Program Evaluator"
  version: "1.0.0"
  kind: "out_of_process"
  capability: { endpoint: "https://plugins.example/program-evaluator/mcp",
                protocol: "mcp", protocol_min: "1.0" }
  agent: { mode: "thin_toolset", model_owner: "kernel" }
  ui: { route: "/evaluate", render: "native",
        view: { input: [{name:"profile", type:"text", label:"Your situation"}],
                result: "recommendation + confidence badge" } }
  data: { namespace: "program_evaluator", ownership: "owner_scoped",
          entities: [ "evaluation" ] }
  run: { request_shape: {...}, result_shape: {...},
         claim_key: "program_evaluator", idempotency: "idempotent" }
  auth: { requires_auth: true, entitlement: "edu.evaluate", scopes: ["run:create"] }
  confidence: { signals: ["grounding_coverage","input_completeness","source_count"] }
}
```

## Acceptance Criteria

- [ ] The kernel can host a plugin **given only its manifest + a reachable capability surface** —
      no kernel code change.
- [ ] A manifest with `requires_auth` not matching `ownership` is **rejected at registration**.
- [ ] A manifest listing a model-self-report confidence signal is **rejected**.
- [ ] Flipping `enabled` removes/restores the plugin end-to-end (launcher, runs, connection)
      with no data loss and no code edit.
- [ ] `self_agent` manifests without `invoke_timeout` are **rejected**.
- [ ] The same manifest schema validates an `in_process` and an `out_of_process` plugin.

## References

- Where these fields are consumed: [`03-kernel-contract.md`](03-kernel-contract.md)
- Auth fields in depth: [`04-auth-and-entitlements.md`](04-auth-and-entitlements.md)
- The two-protocol rationale: [`00-concept.md`](00-concept.md)
