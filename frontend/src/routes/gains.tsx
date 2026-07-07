/**
 * Gains Check — a fun agentic demo.
 *
 * You enter your tracked numbers; an agent judges whether you're doing it right,
 * fetches a hype/shame GIF on the fly, and returns a verdict. The browser shouts
 * the line (Web Speech API) and flashes the headline.
 */
import { createFileRoute } from '@tanstack/react-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { supabase } from '@/data/supabase';

export const Route = createFileRoute('/gains')({
  component: GainsCheck,
});

interface GainsResult {
  passed: boolean;
  headline: string;
  spoken_line: string;
  gif_url: string | null;
  sound: 'hype' | 'shame';
  reason: string;
  steps?: Array<{ tool: string; args: Record<string, unknown>; result: { query?: string; source?: string } }>;
}

type Status = 'idle' | 'pending' | 'running' | 'done' | 'error';

interface TraceEvent {
  seq: number;
  stage: string;
  label: string;
  detail: Record<string, unknown> | null;
  tokens: number | null;
}

function speak(line: string, hype: boolean) {
  try {
    const synth = window.speechSynthesis;
    if (!synth || !line) return;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(line);
    u.rate = hype ? 1.05 : 1;
    u.pitch = hype ? 1.3 : 0.7;
    u.volume = 1;
    synth.speak(u);
  } catch {
    /* speech not available — the visuals still play */
  }
}

function GainsCheck() {
  const [form, setForm] = useState({ weight_kg: '', body_fat_pct: '', calories: '', protein_g: '' });
  const [status, setStatus] = useState<Status>('idle');
  const [result, setResult] = useState<GainsResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkId, setCheckId] = useState<string | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const startingRef = useRef(false);

  const num = (v: string) => (v.trim() === '' ? null : Number(v));

  const start = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    setResult(null);
    setError(null);
    setEvents([]);
    setStatus('pending');
    const input = {
      weight_kg: num(form.weight_kg),
      body_fat_pct: num(form.body_fat_pct),
      calories: num(form.calories),
      protein_g: num(form.protein_g),
    };
    const { data, error: insErr } = await supabase
      .from('gains_checks')
      .insert({ input, status: 'pending' })
      .select()
      .single();
    startingRef.current = false;
    if (insErr || !data) {
      setStatus('error');
      setError(insErr?.message ?? 'Could not start.');
      return;
    }
    setCheckId(data.id as string);
  }, [form]);

  useEffect(() => {
    if (!checkId) return;
    const mergeEvent = (e: TraceEvent) =>
      setEvents((prev) => (prev.some((p) => p.seq === e.seq) ? prev : [...prev, e].sort((a, b) => a.seq - b.seq)));

    const channel = supabase
      .channel(`gains-${checkId}`)
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'gains_checks', filter: `id=eq.${checkId}` },
        (payload) => {
          const row = payload.new as { status: Status; result: GainsResult | null; error: string | null };
          setStatus(row.status);
          if (row.error) setError(row.error);
          if (row.result) {
            setResult(row.result);
            speak(row.result.spoken_line, row.result.passed);
          }
        },
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'gains_events', filter: `check_id=eq.${checkId}` },
        (payload) => mergeEvent(payload.new as TraceEvent),
      )
      .subscribe();

    // Backfill any events that landed before the subscription was ready.
    supabase
      .from('gains_events')
      .select('seq,stage,label,detail,tokens')
      .eq('check_id', checkId)
      .order('seq')
      .then(({ data }) => (data as TraceEvent[] | null)?.forEach(mergeEvent));

    return () => {
      supabase.removeChannel(channel);
    };
  }, [checkId]);

  const busy = status === 'pending' || status === 'running';

  const backendSteps = events.map((e) => {
    const d = e.detail ?? {};
    if (e.stage === 'dispatched') return { icon: '⚙️', label: 'Temporal', sub: String(d.via ?? 'dispatched'), tokens: null };
    if (e.stage === 'reasoning') return { icon: '🧠', label: 'Azure · gpt-5-mini', sub: `reasoning · round ${d.round ?? ''}`, tokens: e.tokens };
    if (e.stage === 'tool') return { icon: '🎬', label: 'Giphy', sub: `search_gif: ${d.query ?? ''}`, tokens: null };
    if (e.stage === 'finalized') return { icon: '💾', label: 'Supabase', sub: 'verdict saved', tokens: null };
    return { icon: '•', label: e.label, sub: e.stage, tokens: e.tokens };
  });
  const steps: Array<{ icon: string; label: string; sub: string; tokens: number | null; done: boolean }> = [
    { icon: '🖥️', label: 'Browser', sub: 'insert run row', tokens: null, done: status !== 'idle' },
    { icon: '🗂️', label: 'Supabase', sub: 'queued (pending)', tokens: null, done: status !== 'idle' },
    ...backendSteps.map((s) => ({ ...s, done: true })),
    { icon: '📡', label: 'Browser', sub: 'Realtime update', tokens: null, done: status === 'done' },
  ];
  const totalTokens = events.reduce((n, e) => n + (e.tokens ?? 0), 0);
  const pct = status === 'done' ? 100 : Math.min(92, (steps.filter((s) => s.done).length / (steps.length + 1)) * 100);
  const showTrace = status !== 'idle';

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <style>{`@keyframes gainsflash{0%,49%{opacity:1}50%,100%{opacity:.15}}`}</style>
      <div>
        <h1 className="text-3xl font-bold tracking-tight">💪 Gains Check</h1>
        <p className="text-muted-foreground">Track your macros? The coach will let you know.</p>
      </div>

      {showTrace && (
        <div className="rounded-lg border p-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-medium">Request trace</span>
            <span className="text-muted-foreground">
              {totalTokens > 0 ? `${totalTokens} tokens` : '—'}
              {busy && <span className="ml-2 animate-pulse">● live</span>}
            </span>
          </div>
          <div className="mb-3 h-1.5 w-full overflow-hidden rounded bg-muted">
            <div className="h-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <ol className="flex items-stretch gap-1 overflow-x-auto pb-1">
            {steps.map((s, i) => (
              <li key={i} className="flex items-center gap-1">
                {i > 0 && <span className="text-muted-foreground">→</span>}
                <div
                  className={`flex min-w-[128px] flex-col rounded-md border px-3 py-2 text-xs transition-opacity ${
                    s.done ? 'opacity-100' : 'opacity-40'
                  }`}
                >
                  <div className="flex items-center gap-1">
                    <span>{s.icon}</span>
                    <span className="font-medium">{s.label}</span>
                  </div>
                  <span className="text-muted-foreground">{s.sub}</span>
                  {s.tokens != null && (
                    <span className="mt-1 inline-block w-fit rounded bg-secondary px-1.5 py-0.5">{s.tokens} tok</span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 rounded-lg border p-4">
        {(
          [
            ['weight_kg', 'Bodyweight (kg)'],
            ['body_fat_pct', 'Body fat (%)'],
            ['calories', 'Calories (kcal)'],
            ['protein_g', 'Protein (g)'],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">{label}</span>
            <input
              type="number"
              value={form[key]}
              onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
              className="rounded-md border px-3 py-2"
              placeholder="—"
            />
          </label>
        ))}
      </div>

      <button
        type="button"
        onClick={start}
        disabled={busy}
        className="w-full rounded-md bg-primary py-3 text-lg font-bold text-primary-foreground disabled:opacity-50"
      >
        {busy ? 'COACH IS LOOKING…' : 'CHECK MY GAINS'}
      </button>

      {error && <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}

      {result && status === 'done' && (
        <div
          className={`rounded-xl border-4 p-6 text-center ${
            result.passed ? 'border-green-500 bg-green-500/10' : 'border-red-500 bg-red-500/10'
          }`}
        >
          <div
            className={`text-5xl font-extrabold ${result.passed ? 'text-green-500' : 'text-red-500'}`}
            style={result.passed ? undefined : { animation: 'gainsflash 0.5s steps(1) infinite' }}
          >
            {result.headline}
          </div>
          <div className="mt-4 flex justify-center">
            {result.gif_url ? (
              <img src={result.gif_url} alt={result.headline} className="max-h-72 rounded-lg" />
            ) : (
              <div className="text-7xl">{result.passed ? '💪🔥' : '🐕📢'}</div>
            )}
          </div>
          <p className="mt-4 text-lg font-medium">{result.reason}</p>
          <p className="mt-1 text-sm text-muted-foreground">🔊 “{result.spoken_line}”</p>
          {result.steps && result.steps.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              agent fetched: {result.steps.map((s) => `${s.result?.query ?? ''} (${s.result?.source ?? ''})`).join(', ')}
            </p>
          )}
          <button type="button" onClick={() => speak(result.spoken_line, result.passed)} className="mt-3 text-xs underline">
            replay sound
          </button>
        </div>
      )}
    </div>
  );
}
