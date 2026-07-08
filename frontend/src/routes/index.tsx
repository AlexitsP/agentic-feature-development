/**
 * Home — the platform launcher. Renders one card per enabled feature from the
 * frontend feature registry (ADR-0008); disabled features simply don't appear.
 */
import { createFileRoute } from '@tanstack/react-router';
import { enabledFeatures } from '@/features/registry';

export const Route = createFileRoute('/')({
  component: Launcher,
});

function Launcher() {
  const features = enabledFeatures();
  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">🎓 Plan my studies</h1>
        <p className="text-muted-foreground">Tools to help you choose and plan your Swiss studies.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {features.map((f) => (
          <a
            key={f.key}
            href={f.path}
            className="flex flex-col gap-1 rounded-lg border p-4 transition-colors hover:bg-muted/50"
          >
            <span className="text-lg font-medium">
              {f.emoji} {f.title}
            </span>
            <span className="text-sm leading-snug text-muted-foreground">{f.description}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
