/**
 * Program Evaluator — Swiss higher-education fit + suggested study options.
 *
 * Run-row + Realtime pattern: insert a `pending`
 * program_evaluations row, then stream status/result and trace events back via
 * Supabase Realtime. The result carries a kernel-computed confidence badge (ADR-0009).
 */
import { createFileRoute } from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import { supabase } from '@/data/supabase';
import { ensureSession } from '@/data/auth';
import { ConfidenceBadge } from '@/components/ConfidenceBadge';

export const Route = createFileRoute('/evaluate')({
  component: ProgramEvaluator,
});

type Status = 'idle' | 'pending' | 'running' | 'done' | 'error';

interface EvalOption {
  field: string;
  institution_type: 'university' | 'uas' | 'ph';
  reason: string;
}

interface Confidence {
  tier: 'well_grounded' | 'partial' | 'speculative';
  badge: string;
  score?: number;
  reasons?: string[];
}

interface EvalResult {
  assessment: string;
  suggested_options: EvalOption[];
  resources: { title: string; url: string }[];
  persona?: string;
  confidence: Confidence;
}

interface TraceEvent {
  seq: number;
  stage: string;
  label: string;
  detail: Record<string, unknown> | null;
  tokens: number | null;
}

const INSTITUTION_LABELS: Record<EvalOption['institution_type'], string> = {
  university: 'University',
  uas: 'University of Applied Sciences (Fachhochschule)',
  ph: 'University of Teacher Education (PH)',
};

const PERSONAS = [
  { key: 'mentor', label: 'Encouraging Mentor' },
  { key: 'advisor', label: 'Straight-talking Advisor' },
  { key: 'analyst', label: 'Detailed Analyst' },
] as const;

const QUALIFICATIONS = ['Gymnasiale Matura', 'Berufsmaturität', 'Fachmaturität', 'Other / none yet'];

function ProgramEvaluator() {
  const [form, setForm] = useState({
    interests: '',
    prior_qualification: '',
    strong_subjects: '',
    target_field: '',
    canton: '',
    language: 'de',
  });
  const [persona, setPersona] = useState<string>('mentor');
  const [status, setStatus] = useState<Status>('idle');
  const [result, setResult] = useState<EvalResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evalId, setEvalId] = useState<string | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const start = async () => {
    setResult(null);
    setError(null);
    setEvents([]);
    setStatus('pending');
    await ensureSession(); // ADR-0007: authenticated (anon) session so the row is owner-scoped
    const input = { ...form, persona };
    const { data, error: insErr } = await supabase
      .from('program_evaluations')
      .insert({ input, status: 'pending' })
      .select()
      .single();
    if (insErr || !data) {
      setStatus('error');
      setError(insErr?.message ?? 'Could not start.');
      return;
    }
    setEvalId(data.id as string);
  };

  useEffect(() => {
    if (!evalId) return;
    let cancelled = false;
    const mergeEvent = (e: TraceEvent) => {
      if (cancelled) return;
      setEvents((prev) => (prev.some((p) => p.seq === e.seq) ? prev : [...prev, e].sort((a, b) => a.seq - b.seq)));
    };
    const channel = supabase
      .channel(`program-eval-${evalId}`)
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'program_evaluations', filter: `id=eq.${evalId}` },
        (payload) => {
          if (cancelled) return;
          const row = payload.new as { status: Status; result: EvalResult | null; error: string | null };
          setStatus(row.status);
          if (row.error) setError(row.error);
          if (row.result) setResult(row.result);
        },
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'program_evaluation_events', filter: `evaluation_id=eq.${evalId}` },
        (payload) => mergeEvent(payload.new as TraceEvent),
      )
      .subscribe();
    supabase
      .from('program_evaluation_events')
      .select('seq,stage,label,detail,tokens')
      .eq('evaluation_id', evalId)
      .order('seq')
      .then(({ data }) => {
        if (!cancelled) (data as TraceEvent[] | null)?.forEach(mergeEvent);
      });
    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, [evalId]);

  const busy = status === 'pending' || status === 'running';

  const reset = () => {
    setStatus('idle');
    setResult(null);
    setError(null);
    setEvalId(null);
    setEvents([]);
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-4">
        <a href="/" className="text-sm text-muted-foreground hover:underline">
          ← All tools
        </a>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">🎓 Program Evaluator</h1>
        <p className="text-muted-foreground">
          Tell us about yourself — we'll suggest Swiss higher-education options that fit, with an honest
          confidence rating.
        </p>
      </div>

      {status === 'idle' && (
        <div className="space-y-3 rounded-lg border p-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Interests</span>
            <input value={form.interests} onChange={set('interests')} className="rounded-md border px-3 py-2" placeholder="e.g. biology, helping people" />
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
              <span className="text-muted-foreground">Target field (optional)</span>
              <input value={form.target_field} onChange={set('target_field')} className="rounded-md border px-3 py-2" placeholder="e.g. medicine" />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Strong subjects</span>
              <input value={form.strong_subjects} onChange={set('strong_subjects')} className="rounded-md border px-3 py-2" placeholder="e.g. biology, chemistry" />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Canton</span>
              <input value={form.canton} onChange={set('canton')} className="rounded-md border px-3 py-2" placeholder="e.g. Zurich" />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Language</span>
              <select value={form.language} onChange={set('language')} className="rounded-md border px-3 py-2">
                <option value="de">German</option>
                <option value="fr">French</option>
                <option value="it">Italian</option>
                <option value="en">English</option>
              </select>
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
          <button
            type="button"
            onClick={start}
            className="rounded-md bg-primary px-6 py-2 text-base font-bold text-primary-foreground"
          >
            🎓 Evaluate my options
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
              <div className="animate-pulse text-4xl">🎓</div>
              <p className="mt-3 text-lg font-medium">EVALUATING YOUR OPTIONS…</p>
              {events.length > 0 && (
                <p className="mt-1 text-sm text-muted-foreground">{events[events.length - 1].label}</p>
              )}
            </div>
          )}

          {result && status === 'done' && (
            <div className="space-y-4" aria-live="polite">
              <div className="rounded-xl border-2 border-primary/50 p-5">
                <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                  Assessment{result.persona ? ` · ${result.persona}` : ''}
                </div>
                <p className="text-base">{result.assessment}</p>
              </div>

              <ConfidenceBadge confidence={result.confidence} />

              {result.suggested_options?.length > 0 && (
                <div className="rounded-xl border p-4">
                  <div className="mb-2 text-sm font-semibold">Suggested study options</div>
                  <ul className="space-y-3">
                    {result.suggested_options.map((o, i) => (
                      <li key={i}>
                        <div className="text-sm font-medium">
                          {o.field} · <span className="text-muted-foreground">{INSTITUTION_LABELS[o.institution_type]}</span>
                        </div>
                        {o.reason && <div className="text-sm text-muted-foreground">{o.reason}</div>}
                      </li>
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
