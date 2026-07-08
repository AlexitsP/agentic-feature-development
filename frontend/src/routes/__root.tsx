/**
 * Root Route — app shell with a registry-driven header nav (ADR-0010). Links are
 * TanStack `<Link>`, so navigation is client-side, preloads on intent, and uses the
 * per-route lazy chunks (autoCodeSplitting). The nav renders from enabledFeatures(),
 * so every plug-in appears automatically.
 */
import { createRootRoute, Link, Outlet } from '@tanstack/react-router';
import { TanStackRouterDevtools } from '@tanstack/router-devtools';
import { enabledFeatures } from '@/features/registry';

export const Route = createRootRoute({
  component: RootComponent,
});

function RootComponent() {
  const features = enabledFeatures();
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <nav className="mx-auto flex max-w-3xl flex-wrap items-center gap-x-4 gap-y-1 px-6 py-3 text-sm">
          <Link to="/" className="font-semibold">
            🎓 Plan my studies
          </Link>
          <span className="text-muted-foreground">·</span>
          {features.map((f) => (
            <Link
              key={f.key}
              to={f.path}
              className="text-muted-foreground transition-colors hover:text-foreground"
              activeProps={{ className: 'font-medium text-foreground' }}
            >
              {f.emoji} {f.title}
            </Link>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-3xl p-6">
        <Outlet />
      </main>
      {import.meta.env.DEV && <TanStackRouterDevtools position="bottom-right" />}
    </div>
  );
}
