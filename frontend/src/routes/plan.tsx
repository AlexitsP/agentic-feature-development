/**
 * Study Planner — a multi-agent panel drafts a study plan (+ how-to-study) for a goal.
 *
 * Run-row + Realtime pattern: insert a `pending` study_plans row (owner-scoped, so an
 * auth session is ensured first), then stream status/result + trace back via Realtime.
 * The result carries a kernel confidence badge (ADR-0009).
 */
import { createFileRoute } from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import { supabase } from '@/data/supabase';
import { ensureSession } from '@/data/auth';
import { ConfidenceBadge } from '@/components/ConfidenceBadge';

export const Route = createFileRoute('/plan')({
  component: StudyPlanner,
});

type Status = 'idle' | 'pending' | 'running' | 'done' | 'error';

interface Confidence {
  tier: 'well_grounded' | 'partial' | 'speculative';
  badge: string;
  score?: number;
  reasons?: string[];
}

interface PanelEntry {
  title: string;
  headline: string;
  points: string[];
}

interface PlanResult {
  summary: string;
  weekly_steps: string[];
  how_to_study: string[];
  resources: { title: string; url: string }[];
  persona?: string;
  panel?: PanelEntry[];
  confidence: Confidence;
}

interface TraceEvent {
  seq: number;
  stage: string;
  label: string;
  detail: Record<string, unknown> | null;
  tokens: number | null;
}

const PERSONAS = [
  { key: 'mentor', label: 'Encouraging Mentor' },
  { key: 'advisor', label: 'Straight-talking Advisor' },
  { key: 'analyst', label: 'Detailed Analyst' },
] as const;

const QUALIFICATIONS = ['Gymnasiale Matura', 'Berufsmaturität', 'Fachmaturität', 'Other / none yet'];

function StudyPlanner() {
  const [form, setForm] = useState({
    target_field: '',
    prior_qualification: '',
    timeframe: '',
    interests: '',
    canton: '',
  });
  const [persona, setPersona] = useState<string>('mentor');
  const [status, setStatus] = useState<Status>('idle');
  const [result, setResult] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [planId, setPlanId] = useState<string | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const start = async () => {
    setResult(null);
    setError(null);
    setEvents([]);
    setStatus('pending');
    await ensureSession(); // ADR-0007: owner-scoped study_plans needs an authenticated session
    const input = { ...form, persona };
    const { data, error: insErr } = await supabase.from('study_plans').insert({ input, status: 'pending' }).select().single();
    if (insErr || !data) {
      setStatus('error');
      setError(insErr?.message ?? 'Could not start.');
      return;
    }
    setPlanId(data.id as string);
  };

  useEffect(() => {
    if (!planId) return;
    let cancelled = false;
    const mergeEvent = (e: TraceEvent) => {
      if (cancelled) return;
      setEvents((prev) => (prev.some((p) => p.seq === e.seq) ? prev : [...prev, e].sort((a, b) => a.seq - b.seq)));
    };
    const channel = supabase
      .channel(`study-plan-${planId}`)
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'study_plans', filter: `id=eq.${planId}` },
        (payload) => {
          if (cancelled) return;
          const row = payload.new as { status: Status; result: PlanResult | null; error: string | null };
          setStatus(row.status);
          if (row.error) setError(row.error);
          if (row.result) setResult(row.result);
        },
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'study_plan_events', filter: `plan_id=eq.${planId}` },
        (payload) => mergeEvent(payload.new as TraceEvent),
      )
      .subscribe();
    supabase
      .from('study_plan_events')
      .select('seq,stage,label,detail,tokens')
      .eq('plan_id', planId)
      .order('seq')
      .then(({ data }) => {
        if (!cancelled) (data as TraceEvent[] | null)?.forEach(mergeEvent);
      });
    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, [planId]);

  const busy = status === 'pending' || status === 'running';

  const reset = () => {
    setStatus('idle');
    setResult(null);
    setError(null);
    setPlanId(null);
    setEvents([]);
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-4">
        <a href="/" className="text-sm text-muted-foreground hover:underline">
          ← All tools
        </a>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">🗺️ Study Planner</h1>
        <p className="text-muted-foreground">
          A coaching panel drafts a study plan for your goal — including how to study — with an honest
          confidence rating.
        </p>
      </div>

      {status === 'idle' && (
        <div className="space-y-3 rounded-lg border p-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Goal / target field</span>
            <input value={form.target_field} onChange={set('target_field')} className="rounded-md border px-3 py-2" placeholder="e.g. study medicine" />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Prior qualification</span>
              <select value={form.prior_qualification} onChange={set('prior_qualification')} className="rounded-md border px-3 py-2">
                <option value="">—</option>
                {QUALIFICATIONS.map((q) => (
                  <option key={q} value={q}>
                    {q}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Timeframe</span>
              <input value={form.timeframe} onChange={set('timeframe')} className="rounded-md border px-3 py-2" placeholder="e.g. start next year" />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Interests</span>
              <input value={form.interests} onChange={set('interests')} className="rounded-md border px-3 py-2" placeholder="e.g. biology, helping people" />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Canton</span>
              <input value={form.canton} onChange={set('canton')} className="rounded-md border px-3 py-2" placeholder="e.g. Zurich" />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Advisor tone</span>
              <select value={persona} onChange={(e) => setPersona(e.target.value)} className="rounded-md border px-3 py-2">
                {PERSONAS.map((p) => (
                  <option key={p.key} value={p.key}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button type="button" onClick={start} className="rounded-md bg-primary px-6 py-2 text-base font-bold text-primary-foreground">
            🗺️ Draft my study plan
          </button>
        </div>
      )}

      {status !== 'idle' && (
        <div className="space-y-4">
          {error && (
            <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {busy && (
            <div role="status" aria-live="polite" className="rounded-xl border p-8 text-center">
              <div className="animate-pulse text-4xl">🧭</div>
              <p className="mt-3 text-lg font-medium">THE PANEL IS DRAFTING YOUR PLAN…</p>
              {events.length > 0 && <p className="mt-1 text-sm text-muted-foreground">{events[events.length - 1].label}</p>}
            </div>
          )}

          {result && status === 'done' && (
            <div className="space-y-4" aria-live="polite">
              <div className="rounded-xl border-2 border-primary/50 p-5">
                <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                  Study plan{result.persona ? ` · ${result.persona}` : ''}
                </div>
                <p className="text-base">{result.summary}</p>
              </div>

              <ConfidenceBadge confidence={result.confidence} />

              {result.weekly_steps?.length > 0 && (
                <div className="rounded-xl border p-4">
                  <div className="mb-1 text-sm font-semibold">Start this week</div>
                  <ol className="list-decimal space-y-1 pl-5 text-sm">
                    {result.weekly_steps.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ol>
                </div>
              )}

              {result.how_to_study?.length > 0 && (
                <div className="rounded-xl border p-4">
                  <div className="mb-1 text-sm font-semibold">📚 How to study</div>
                  <ul className="list-disc space-y-1 pl-5 text-sm">
                    {result.how_to_study.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.resources?.length > 0 && (
                <div className="rounded-xl border p-4">
                  <div className="mb-1 text-sm font-semibold">Official sources</div>
                  <ul className="space-y-1 text-sm">
                    {result.resources.map((r, i) => (
                      <li key={i}>
                        🔗{' '}
                        <a href={r.url} target="_blank" rel="noreferrer" className="underline">
                          {r.title}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.panel && result.panel.length > 0 && (
                <details className="rounded-lg border bg-muted/30 text-sm">
                  <summary className="cursor-pointer select-none px-3 py-2 font-medium">
                    🧩 How this was made — the coaching panel ({result.panel.length} advisors)
                  </summary>
                  <div className="space-y-3 border-t px-3 py-3">
                    {result.panel.map((p, i) => (
                      <div key={i}>
                        <div className="text-sm font-medium">{p.title}</div>
                        {p.headline && <div className="text-xs text-muted-foreground">{p.headline}</div>}
                        {p.points?.length > 0 && (
                          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                            {p.points.map((pt, j) => (
                              <li key={j}>{pt}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              )}

              <button type="button" onClick={reset} className="rounded-md border px-4 py-2 text-sm hover:bg-muted/50">
                ↻ Start over
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
