# The Stack Kit (docs-only)

A portable, **docs-only** kit for bootstrapping the standard stack — **Supabase + Temporal +
Vite/React + a hosted LLM** — in a **fresh, empty repo**, faster and more securely, by driving an
agent with our lessons-learned playbook and guardrails.

**What it is:** a small set of documents you copy into a new repo, plus prompts. Dropped in, they
make an agent (a) load a binding governance base, (b) scaffold the stack from the playbook, and
(c) add features the same disciplined way every time — with the security defaults baked in.

**What it is NOT:** it ships **no stack code**. The agent generates the scaffold from
`PLAYBOOK.md` "Phase 0". (If you'd rather start from a ready-made scaffold instead of generating
one, that's a different choice than the docs-only kit — start from a stack template repo and just
copy the governance + playbook on top.)

---

## What's in the kit (copy these into the new repo)

| From this repo | To the new repo | Purpose |
|---|---|---|
| `kit/CLAUDE.template.md` | `./CLAUDE.md` (then **fill the Repo-facts block**) | The binding governance base every agent auto-loads |
| — | `./AGENTS.md` (one line: "canonical base is `CLAUDE.md` — read it") | Entry point for non-Claude tools |
| `docs/PLAYBOOK.md` | `docs/PLAYBOOK.md` | The build procedure: Phase 0 scaffold, §3 feature recipe, §4 landmines, the Guardrails |
| `docs/adrs/TEMPLATE.md`, `docs/adrs/README.md` | `docs/adrs/` | ADR template + process (record decisions as you make them) |
| `docs/specs/TEMPLATE.md` | `docs/specs/` | Spec template for feature slices |

That's the whole kit. The knowledge + guardrails live in `PLAYBOOK.md`; `CLAUDE.md` is the thin
binding pointer that makes the agent follow it.

---

## How to use it in a naked repo

1. **Copy** the files above into the empty repo.
2. **Paste the bootstrap prompt** below to your agent.
3. It installs the governance, scaffolds the stack per Phase 0, and verifies it runs **before** any
   feature.
4. After that, use the **per-session** and **feature** prompts for day-to-day work.

### Bootstrap prompt (paste once, in the fresh repo)

```
This is a fresh/empty repo. We're bootstrapping the standard stack (Supabase + Temporal +
Vite/React + a hosted LLM) using the kit in ./kit and docs/PLAYBOOK.md.

1. Read docs/PLAYBOOK.md — its "Guardrails (MUST / MUST-NOT)" are BINDING.
2. Install governance: copy kit/CLAUDE.template.md to ./CLAUDE.md and FILL its "Repo facts" for
   our choices (ask me if unsure):
     - LLM host / model / auth  (e.g. Azure OpenAI / Bedrock / OpenAI-direct)
     - Supabase: local CLI or cloud; ports; where keys come from
     - container runtime; merge strategy; RLS posture; deployment posture
   Add a one-line AGENTS.md pointing to CLAUDE.md.
3. Scaffold the stack per PLAYBOOK "Phase 0": docker-compose, Supabase config + a first migration
   (RLS + grants + realtime), the Temporal worker skeleton (model client + model_chat + poller +
   worker registration), a Vite/React shell wired to the Supabase anon key, Makefile, .env.example,
   and the CI test gate that FAILS if no tests exist. Bake in the security defaults from step one.
4. Verify Phase 0: `make up` runs and a trivial insert -> poll round-trips through a stub workflow.
   Do NOT build a feature until this passes.

Follow the guardrails throughout. Stop and show me the result after Phase 0 verifies, before
building any feature.
```

### Per-session activation prompt (paste at the start of each session, once bootstrapped)

```
Before doing anything: read CLAUDE.md at the repo root and treat it as binding (it points to
docs/PLAYBOOK.md — the Guardrails there are binding too). Confirm you loaded them by replying with
(1) the non-negotiable guardrails, one line each, and (2) this repo's facts. Then operate under
that governance: PLAYBOOK §3 before a feature, §4 before debugging; branch off main + PR; never
reuse a merged branch; verify end-to-end, not on CI-green. If you can't see CLAUDE.md, stop.
```

### Feature prompt (day-to-day)

```
New agentic feature `<name>`: <one line of what it does>. Follow CLAUDE.md + PLAYBOOK §3 and the
guardrails. Tools it needs: <…>. Terminal output/schema: <…>. Namespace everything as `<name>`.
Verify end-to-end, then open a PR.
```

---

## Why this makes it faster *and* more secure

- **Faster:** the agent doesn't re-derive the architecture — Phase 0 + §3 are a fixed recipe, and
  §4 pre-empts the traps that otherwise eat hours (port collisions, missing API grants, provider
  SDK pins, reasoning-model tool-forcing, poller races, empty bind mounts).
- **More secure:** the guardrails + Phase 0 defaults are enforced from the first commit — RLS +
  explicit grants on every table, secrets server-side only, the browser limited to the anon key,
  and "verify end-to-end, not CI-green." Security is the default, not a later audit.
