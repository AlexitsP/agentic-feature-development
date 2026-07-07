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

// "Meta" stats for the whole AI build session (from Claude Code /cost).
// Note: the 171M cache-read tokens are the conversation re-read each turn, not
// unique work — so they're shown separately from newly-generated tokens.
const BUILD_STATS = {
  time: '3h 59m (2h 8m API)',
  cost: '$107.84',
  tokens: '~475k generated · 171M cache reads',
};

interface GainsResult {
  passed: boolean;
  fail_kind?: 'not_tracking' | 'slacking' | null;
  mode?: 'guided' | 'agentic';
  headline: string;
  spoken_line: string;
  gif_url: string | null;
  sound: 'hype' | 'shame';
  reason: string;
  persona?: string;
  audio_b64?: string | null;
  legend?: {
    name: string;
    weight_kg: number | null;
    height_cm: number | null;
    body_fat_pct: number | null;
    fun_fact: string;
    image_url: string | null;
    matched?: boolean | null;
    quip: string;
  } | null;
  steps?: Array<{ tool: string; args: Record<string, unknown>; result: { query?: string; source?: string } }>;
}

// Explainer shown under the engine toggle — swaps with the selected mode.
const MODE_INFO: Record<'guided' | 'agentic', { title: string; purpose: string; rows: [string, string][] }> = {
  guided: {
    title: '🎛️ Guided — a pipeline with an LLM inside it',
    purpose: 'Predictable and demo-safe: the same inputs give consistent, on-brand results every time.',
    rows: [
      [
        'How it works',
        'The AI makes ONE structured decision — pass / fail and why — against explicit rules written into the prompt. Everything you then see and hear (the GIF, the meme quote, the rival legend, the voice style) is chosen by ordinary code from a curated library. One model call, no tool loop.',
      ],
      [
        'Why have it',
        'When results must be reliable — a live demo, a consistent look — you keep the entertainment-critical choices out of the model’s hands, so a pass always shows a real Ronnie/Arnold GIF and nothing ever goes off-brand.',
      ],
      ['What it means', 'The model classifies; deterministic code does the rest. Fast, cheap, repeatable — but not really “an agent.”'],
    ],
  },
  agentic: {
    title: '🤖 Agentic — the model drives',
    purpose: 'Genuine autonomy: the model reasons for itself and uses real tools to build the whole verdict.',
    rows: [
      [
        'How it works',
        'No fixed formula. The model judges your numbers on its own and has a real GIF-search tool it decides when and how to call — its own search terms, as many times as it likes. It picks the GIF, chooses a rival legend and writes the comparison, writes the headline and spoken line, and even chooses the voice style. A true reason → search → decide loop (watch the trace above).',
      ],
      [
        'Why have it',
        'When you want adaptability, creativity and genuine tool use — the model can react to unusual inputs a fixed rule never anticipated — and you can accept more variability in exchange.',
      ],
      ['What it means', 'The model drives; code just runs the tools it asks for. That’s a real agent trajectory — occasionally an off-brand GIF or odd rival is the honest price of the autonomy.'],
    ],
  },
};

const PERSONAS = [
  { key: 'gymbro', emoji: '🗣️', label: 'Gym Bro', blurb: 'Loud hype, all caps' },
  { key: 'sergeant', emoji: '🎖️', label: 'Drill Sergeant', blurb: 'No excuses, soldier' },
  { key: 'wholesome', emoji: '🤗', label: 'Wholesome Coach', blurb: 'Kind & encouraging' },
] as const;

// Verdict theming: pass = green, "slacking" fail = amber, "not tracking" = red.
function verdictTheme(r: GainsResult) {
  if (r.passed) return { border: 'border-green-500', bg: 'bg-green-500/10', text: 'text-green-500', flash: false, emoji: '💪🔥' };
  if (r.fail_kind === 'slacking')
    return { border: 'border-amber-500', bg: 'bg-amber-500/10', text: 'text-amber-500', flash: true, emoji: '😤' };
  return { border: 'border-red-500', bg: 'bg-red-500/10', text: 'text-red-500', flash: true, emoji: '🐕📢' };
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

/** Play the neural-TTS clip if we got one, else fall back to browser speech. */
function playResult(r: GainsResult) {
  if (r.audio_b64) {
    try {
      const audio = new Audio(`data:audio/mpeg;base64,${r.audio_b64}`);
      audio.volume = 1;
      void audio.play();
      return;
    } catch {
      /* fall through to browser TTS */
    }
  }
  speak(r.spoken_line, r.passed);
}

function GainsCheck() {
  const [form, setForm] = useState({ weight_kg: '', body_fat_pct: '', calories: '', protein_g: '' });
  const [persona, setPersona] = useState<string>('gymbro');
  const [mode, setMode] = useState<'guided' | 'agentic'>('guided');
  const [status, setStatus] = useState<Status>('idle');
  const [result, setResult] = useState<GainsResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkId, setCheckId] = useState<string | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const startingRef = useRef(false);
  const activeStepRef = useRef<HTMLLIElement | null>(null);
  const resultRef = useRef<HTMLDivElement | null>(null);

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
      persona,
      mode,
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
  }, [form, persona, mode]);

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
            playResult(row.result);
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
    if (e.stage === 'dispatched')
      return {
        icon: '⚙️',
        label: 'Temporal',
        sub: String(d.via ?? 'dispatched'),
        desc: 'A background worker picked up your request and started the automated workflow.',
        tokens: null,
      };
    if (e.stage === 'reasoning')
      return {
        icon: '🧠',
        label: 'Azure · gpt-5-mini',
        sub: `reasoning · round ${d.round ?? ''}`,
        desc: 'The AI model reads your numbers and decides its next move — look something up, or give the final verdict.',
        tokens: e.tokens,
      };
    if (e.stage === 'legend')
      return {
        icon: '🏆',
        label: `Legend · ${d.name ?? ''}`,
        sub: d.matched ? 'closest match picked' : 'random rival picked',
        desc: d.matched
          ? `Finds the bodybuilding legend whose stats are closest to yours (${d.name ?? ''}) to size you up against.`
          : `Picks a random bodybuilding legend (${d.name ?? ''}) — you gave no stats to match on.`,
        tokens: null,
      };
    if (e.stage === 'tool')
      return {
        icon: '🎬',
        label: 'Giphy',
        sub: `search_gif: ${d.query ?? ''}`,
        desc: `The agent fetches a matching GIF on the fly${d.query ? ` for “${d.query}”` : ''}.`,
        tokens: null,
      };
    if (e.stage === 'speech')
      return {
        icon: '🔊',
        label: 'Azure Speech',
        sub: `neural TTS · ${d.style ?? ''}`,
        desc: 'The verdict line is turned into an expressive spoken voice clip.',
        tokens: null,
      };
    if (e.stage === 'finalized')
      return {
        icon: '💾',
        label: 'Supabase',
        sub: 'verdict saved',
        desc: 'The finished verdict is saved back to the database.',
        tokens: null,
      };
    return { icon: '•', label: e.label, sub: e.stage, desc: '', tokens: e.tokens };
  });
  const steps: Array<{ icon: string; label: string; sub: string; desc: string; tokens: number | null; done: boolean }> = [
    {
      icon: '🖥️',
      label: 'Browser',
      sub: 'insert run row',
      desc: 'Your numbers are packaged in the browser and sent off as a new request.',
      tokens: null,
      done: status !== 'idle',
    },
    {
      icon: '🗂️',
      label: 'Supabase',
      sub: 'queued (pending)',
      desc: 'The request waits in the database until a worker is ready to handle it.',
      tokens: null,
      done: status !== 'idle',
    },
    ...backendSteps.map((s) => ({ ...s, done: true })),
    {
      icon: '📡',
      label: 'Browser',
      sub: 'Realtime update',
      desc: 'The result streams live back to your browser and appears on screen.',
      tokens: null,
      done: status === 'done',
    },
  ];
  const totalTokens = events.reduce((n, e) => n + (e.tokens ?? 0), 0);
  const pct = status === 'done' ? 100 : Math.min(92, (steps.filter((s) => s.done).length / (steps.length + 1)) * 100);
  const showTrace = status !== 'idle';
  const lastDoneIndex = steps.reduce((acc, s, i) => (s.done ? i : acc), 0);

  // Keep the newest active step scrolled into view as the trace advances.
  useEffect(() => {
    activeStepRef.current?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [events.length, status]);

  // When the verdict lands, scroll down to it.
  useEffect(() => {
    if (status === 'done' && result) {
      resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [status, result]);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <style>{`@keyframes gainsflash{0%,49%{opacity:1}50%,100%{opacity:.15}}`}</style>
      <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-lg border bg-muted/30 px-4 py-2 text-sm">
        <span className="w-full text-xs text-muted-foreground">Built by AI in one session (everything, not just this page):</span>
        <span>
          ⏱️ <span className="text-muted-foreground">Built in:</span>{' '}
          <span className="font-semibold">{BUILD_STATS.time}</span>
        </span>
        <span>
          💵 <span className="text-muted-foreground">Cost:</span>{' '}
          <span className="font-semibold">{BUILD_STATS.cost}</span>
        </span>
        <span>
          🪙 <span className="text-muted-foreground">Tokens:</span>{' '}
          <span className="font-semibold">{BUILD_STATS.tokens}</span>
        </span>
      </div>

      <div>
        <h1 className="text-3xl font-bold tracking-tight">💪 Gains Check</h1>
        <p className="text-muted-foreground">Track your macros? The coach will let you know.</p>
      </div>

      <div className="rounded-lg border p-4">
        <div className="mb-2 text-sm text-muted-foreground">Engine</div>
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              ['guided', '🎛️', 'Guided', 'Deterministic pipeline. Rule-based verdict, curated GIFs & quotes. Reliable.'],
              ['agentic', '🤖', 'Agentic', 'The model reasons freely, picks & searches its own GIFs, chooses the rival & voice.'],
            ] as const
          ).map(([key, emoji, label, blurb]) => (
            <button
              key={key}
              type="button"
              onClick={() => setMode(key)}
              disabled={busy}
              className={`flex flex-col gap-0.5 rounded-md border px-3 py-3 text-left transition-colors disabled:opacity-50 ${
                mode === key ? 'border-primary bg-primary/10' : 'hover:bg-muted/50'
              }`}
            >
              <span className="text-sm font-medium">
                {emoji} {label}
              </span>
              <span className="text-xs leading-snug text-muted-foreground">{blurb}</span>
            </button>
          ))}
        </div>

        <div className="mt-3 rounded-md border bg-muted/30 p-3 text-sm">
          <div className="font-medium">{MODE_INFO[mode].title}</div>
          <p className="mt-1 text-muted-foreground">{MODE_INFO[mode].purpose}</p>
          <dl className="mt-3 space-y-2">
            {MODE_INFO[mode].rows.map(([label, text]) => (
              <div key={label} className="grid grid-cols-[7.5rem_1fr] gap-2">
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
                <dd className="leading-snug text-muted-foreground">{text}</dd>
              </div>
            ))}
          </dl>
        </div>
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
          <p className="mb-3 text-xs text-muted-foreground">
            Follow your request as it travels from the browser, through the AI agent and its tools, and back to the screen.
          </p>
          <div className="mb-3 h-1.5 w-full overflow-hidden rounded bg-muted">
            <div className="h-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <ol className="flex items-stretch gap-1 overflow-x-auto pb-1">
            {steps.map((s, i) => (
              <li key={i} ref={i === lastDoneIndex ? activeStepRef : undefined} className="flex items-center gap-1">
                {i > 0 && <span className="text-muted-foreground">→</span>}
                <div
                  className={`flex w-[200px] shrink-0 flex-col rounded-md border px-3 py-2 text-xs transition-opacity ${
                    s.done ? 'opacity-100' : 'opacity-40'
                  }`}
                >
                  <div className="flex items-center gap-1">
                    <span>{s.icon}</span>
                    <span className="font-medium">{s.label}</span>
                  </div>
                  <span className="text-muted-foreground">{s.sub}</span>
                  {s.desc && <span className="mt-1 leading-snug text-muted-foreground">{s.desc}</span>}
                  {s.tokens != null && (
                    <span className="mt-1 inline-block w-fit rounded bg-secondary px-1.5 py-0.5">{s.tokens} tokens used</span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="rounded-lg border p-4">
        <div className="mb-2 text-sm text-muted-foreground">Pick your coach</div>
        <div className="grid grid-cols-3 gap-2">
          {PERSONAS.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => setPersona(p.key)}
              disabled={busy}
              className={`flex flex-col items-center gap-0.5 rounded-md border px-2 py-3 text-center transition-colors disabled:opacity-50 ${
                persona === p.key ? 'border-primary bg-primary/10' : 'hover:bg-muted/50'
              }`}
            >
              <span className="text-2xl">{p.emoji}</span>
              <span className="text-sm font-medium">{p.label}</span>
              <span className="text-xs text-muted-foreground">{p.blurb}</span>
            </button>
          ))}
        </div>
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
        <div ref={resultRef} className={`scroll-mt-4 rounded-xl border-4 p-6 text-center ${verdictTheme(result).border} ${verdictTheme(result).bg}`}>
          <div className="mb-2 flex items-center justify-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
            {result.persona && <span>Coach: {result.persona}</span>}
            <span className="rounded-full border px-2 py-0.5 normal-case">
              {result.mode === 'agentic' ? '🤖 Agentic' : '🎛️ Guided'}
            </span>
          </div>
          <div
            className={`text-5xl font-extrabold ${verdictTheme(result).text}`}
            style={verdictTheme(result).flash ? { animation: 'gainsflash 0.5s steps(1) infinite' } : undefined}
          >
            {result.headline}
          </div>
          <div className="mt-4 flex justify-center">
            {result.gif_url ? (
              <img src={result.gif_url} alt={result.headline} className="max-h-72 rounded-lg" />
            ) : (
              <div className="text-7xl">{verdictTheme(result).emoji}</div>
            )}
          </div>
          <p className="mt-4 text-lg font-medium">{result.reason}</p>
          <p className="mt-1 text-sm text-muted-foreground">🔊 “{result.spoken_line}”</p>
          {result.steps && result.steps.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              agent fetched: {result.steps.map((s) => `${s.result?.query ?? ''} (${s.result?.source ?? ''})`).join(', ')}
            </p>
          )}
          <button type="button" onClick={() => playResult(result)} className="mt-3 text-xs underline">
            replay sound
          </button>
        </div>
      )}

      {result && status === 'done' && result.legend && (
        <div className="rounded-xl border p-4">
          <div className="mb-3 text-sm font-medium">
            🏆 You vs {result.legend.name}
            <span className="ml-2 font-normal text-muted-foreground">
              {result.mode === 'agentic'
                ? "· coach's pick"
                : result.legend.matched
                  ? '· your closest match'
                  : '· random rival'}
            </span>
          </div>
          <div className="flex flex-col gap-4 sm:flex-row">
            {result.legend.image_url && (
              <img
                src={result.legend.image_url}
                alt={result.legend.name}
                className="h-40 w-40 shrink-0 rounded-lg object-cover"
              />
            )}
            <div className="flex-1 space-y-3">
              <p className="text-sm">{result.legend.quip}</p>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="font-medium text-muted-foreground">Metric</div>
                <div className="font-medium">You</div>
                <div className="font-medium">{result.legend.name}</div>

                <div className="text-muted-foreground">Weight (kg)</div>
                <div>{form.weight_kg || '—'}</div>
                <div>{result.legend.weight_kg ?? '—'}</div>

                <div className="text-muted-foreground">Body fat (%)</div>
                <div>{form.body_fat_pct || '—'}</div>
                <div>{result.legend.body_fat_pct ?? '—'}</div>
              </div>
              <p className="text-xs text-muted-foreground">{result.legend.fun_fact}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
