/**
 * Home — the platform launcher, framed kernel-first: the **kernel** is the product
 * (a plugin host for agentic apps), and each enabled feature is an "app" plugged into
 * it. The apps grid renders one card per enabled feature from the frontend registry
 * (ADR-0008); disabled features simply don't appear. Cards are TanStack `<Link>`
 * (client-side nav + intent preload + lazy chunks).
 */
import { createFileRoute, Link } from '@tanstack/react-router';
import { enabledFeatures } from '@/features/registry';
import { AlpacaMark } from '@/components/Logo';

export const Route = createFileRoute('/')({
  component: Launcher,
});

/** The shared primitives every app inherits from the kernel (see temporal/src/kernel/). */
const PRIMITIVES = [
  {
    emoji: '🧩',
    title: 'Registry',
    blurb: 'Apps declare a manifest; the kernel builds the worker, poller, and nav from it. No per-app plumbing.',
  },
  {
    emoji: '📊',
    title: 'Confidence',
    blurb: 'Every result carries a badge computed from observable signals — never the model’s self-report.',
  },
  {
    emoji: '📚',
    title: 'Grounding',
    blurb: 'Answers are grounded in a curated source allowlist; invented links are dropped before they reach a user.',
  },
] as const;

function Launcher() {
  const apps = enabledFeatures();
  return (
    <div className="mx-auto max-w-3xl">
      {/* Hero — AlpacAI, the product */}
      <section className="mb-10">
        <span className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium text-muted-foreground">
          ⚙️ Swiss AI learning platform
        </span>
        <div className="mt-3 flex items-center gap-3">
          <AlpacaMark size={52} />
          <h1 className="text-4xl font-bold tracking-tight">
            Alpac<span style={{ color: '#6C5CE7' }}>AI</span>
          </h1>
        </div>
        <p className="mt-3 text-lg text-muted-foreground">
          A Swiss AI hub for learning — a plugin host for agentic apps. Each app self-registers as a
          plugin and runs on one shared runtime, so a new app is a package, not a rebuild.
        </p>
        <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
          The browser only ever writes a <code className="rounded bg-muted px-1 py-0.5 text-xs">pending</code>{' '}
          row. The kernel’s poller claims it, starts the app’s Temporal workflow, calls the model,
          grounds the answer in a source allowlist, rates its own confidence from observable
          signals, and streams the result back live. Worker, poller, and this launcher are all
          registry-driven.
        </p>
      </section>

      {/* What every app inherits from the kernel */}
      <section className="mb-10">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          What every app inherits
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {PRIMITIVES.map((p) => (
            <div key={p.title} className="rounded-lg border p-4">
              <div className="text-2xl">{p.emoji}</div>
              <div className="mt-1.5 text-sm font-medium">{p.title}</div>
              <div className="mt-0.5 text-sm leading-snug text-muted-foreground">{p.blurb}</div>
            </div>
          ))}
        </div>
      </section>

      {/* The apps currently plugged in */}
      <section>
        <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Apps plugged in
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
            {apps.length}
          </span>
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {apps.map((f) => (
            <Link
              key={f.key}
              to={f.path}
              className="group flex flex-col gap-1 rounded-lg border p-4 transition-colors hover:bg-muted/50"
            >
              <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Agentic app
              </span>
              <span className="text-lg font-medium">
                {f.emoji} {f.title}
              </span>
              <span className="text-sm leading-snug text-muted-foreground">{f.description}</span>
              <span className="mt-1 text-sm font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
                Open →
              </span>
            </Link>
          ))}
        </div>
        <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
          Each app is a self-contained plugin. Adding, removing, or toggling one touches only its
          package and a single line in the registry — the kernel stays untouched.
        </p>
      </section>
    </div>
  );
}
