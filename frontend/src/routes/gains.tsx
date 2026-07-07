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
  const startingRef = useRef(false);

  const num = (v: string) => (v.trim() === '' ? null : Number(v));

  const start = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    setResult(null);
    setError(null);
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
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [checkId]);

  const busy = status === 'pending' || status === 'running';

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <style>{`@keyframes gainsflash{0%,49%{opacity:1}50%,100%{opacity:.15}}`}</style>
      <div>
        <h1 className="text-3xl font-bold tracking-tight">💪 Gains Check</h1>
        <p className="text-muted-foreground">Track your macros? The coach will let you know.</p>
      </div>

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
