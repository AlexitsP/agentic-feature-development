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
  fail_kind?: 'not_tracking' | 'slacking' | null;
  mode?: 'guided' | 'agentic';
  headline: string;
  spoken_line: string;
  gif_url: string | null;
  sound: 'hype' | 'shame';
  reason: string;
  persona?: string;
  audio_b64?: string | null;
  steps?: Array<{ tool: string; args: Record<string, unknown>; result: { query?: string; source?: string } }>;
}

interface GainsPlan {
  goal_label: string;
  persona?: string;
  summary: string;
  calorie_guidance?: string;
  protein_guidance?: string;
  training_focus?: string;
  weekly_steps: string[];
  resources: { title: string; url: string }[];
  panel?: { title: string; headline: string; points: string[] }[];
}

// Explainer shown under the engine toggle — swaps with the selected mode.
const MODE_INFO: Record<'guided' | 'agentic', { title: string; purpose: string; rows: [string, string][] }> = {
  guided: {
    title: '🎛️ Guided — a pipeline with an LLM inside it',
    purpose: 'Predictable and demo-safe: the same inputs give consistent, on-brand results every time.',
    rows: [
      [
        'How it works',
        'The AI makes ONE structured decision — pass / fail and why — against explicit rules written into the prompt. Everything you then see (the GIF, the meme quote) is chosen by ordinary code from a curated library. One model call, no tool loop.',
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
        'No fixed formula. The model judges your numbers on its own and has a real GIF-search tool it decides when and how to call — its own search terms, as many times as it likes. It picks the GIF, writes the headline and spoken line, and even chooses the voice style. A true reason → search → decide loop (watch the trace above).',
      ],
      [
        'Why have it',
        'When you want adaptability, creativity and genuine tool use — the model can react to unusual inputs a fixed rule never anticipated — and you can accept more variability in exchange.',
      ],
      ['What it means', 'The model drives; code just runs the tools it asks for. That’s a real agent trajectory — occasionally an off-brand GIF is the honest price of the autonomy.'],
    ],
  },
};

const PERSONAS = [
  { key: 'gymbro', emoji: '🗣️', label: 'Gym Bro', blurb: 'Loud hype, all caps' },
  { key: 'sergeant', emoji: '🎖️', label: 'Drill Sergeant', blurb: 'No excuses, soldier' },
  { key: 'wholesome', emoji: '🤗', label: 'Wholesome Coach', blurb: 'Kind & encouraging' },
] as const;

const STEP_LABELS = ['Engine', 'Coach', 'Your numbers', 'Result', 'Goal', 'Plan'] as const;

const GOALS = [
  { key: 'recomp', emoji: '⚖️', label: 'Body recomposition', blurb: 'Lose fat, keep/gain muscle' },
  { key: 'weight_loss', emoji: '📉', label: 'Weight loss', blurb: 'Calorie deficit, solid macros' },
  { key: 'build_muscle', emoji: '💪', label: 'Build muscle', blurb: 'Lean bulk / hypertrophy' },
  { key: 'get_lean', emoji: '🔪', label: 'Get lean', blurb: 'Cut down body fat' },
] as const;

// TTS is off for now (kept in code — flip to re-enable once the backend
// AZURE_SPEECH_ENABLED flag is on too).
const TTS_ENABLED = false;

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
  const [step, setStep] = useState(0); // wizard: 0 Engine · 1 Coach · 2 Numbers · 3 Result
  const [inputMode, setInputMode] = useState<'choose' | 'numbers' | 'freeform'>('choose');
  const [freeform, setFreeform] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [result, setResult] = useState<GainsResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkId, setCheckId] = useState<string | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [goal, setGoal] = useState<string | null>(null);
  const [goalDetail, setGoalDetail] = useState('');
  const [planStatus, setPlanStatus] = useState<Status>('idle');
  const [planResult, setPlanResult] = useState<GainsPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [planCheckId, setPlanCheckId] = useState<string | null>(null);
  const [planEvents, setPlanEvents] = useState<TraceEvent[]>([]);
  const startingRef = useRef(false);
  const resultRef = useRef<HTMLDivElement | null>(null);

  const num = (v: string) => (v.trim() === '' ? null : Number(v));

  const start = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    setResult(null);
    setError(null);
    setEvents([]);
    setStatus('pending');
    const input =
      inputMode === 'freeform'
        ? { freeform: freeform.trim(), persona, mode }
        : {
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
  }, [form, persona, mode, inputMode, freeform]);

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
            if (TTS_ENABLED) playResult(row.result);
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

  // Live subscription for the plan run (separate gains_plans row).
  useEffect(() => {
    if (!planCheckId) return;
    const applyRow = (row: { status: Status; result: GainsPlan | null; error: string | null }) => {
      setPlanStatus(row.status);
      if (row.error) setPlanError(row.error);
      if (row.result) setPlanResult(row.result);
    };
    const mergePlanEvent = (e: TraceEvent) =>
      setPlanEvents((prev) => (prev.some((p) => p.seq === e.seq) ? prev : [...prev, e].sort((a, b) => a.seq - b.seq)));
    const channel = supabase
      .channel(`gains-plan-${planCheckId}`)
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'gains_plans', filter: `id=eq.${planCheckId}` },
        (payload) => applyRow(payload.new as { status: Status; result: GainsPlan | null; error: string | null }),
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'gains_plan_events', filter: `plan_id=eq.${planCheckId}` },
        (payload) => mergePlanEvent(payload.new as TraceEvent),
      )
      .subscribe();
    supabase
      .from('gains_plans')
      .select('status,result,error')
      .eq('id', planCheckId)
      .single()
      .then(({ data }) => data && applyRow(data as { status: Status; result: GainsPlan | null; error: string | null }));
    supabase
      .from('gains_plan_events')
      .select('seq,stage,label,detail,tokens')
      .eq('plan_id', planCheckId)
      .order('seq')
      .then(({ data }) => (data as TraceEvent[] | null)?.forEach(mergePlanEvent));
    return () => {
      supabase.removeChannel(channel);
    };
  }, [planCheckId]);

  const generatePlan = useCallback(async () => {
    setPlanResult(null);
    setPlanError(null);
    setPlanEvents([]);
    setPlanStatus('pending');
    const numberInput =
      inputMode === 'freeform'
        ? { freeform: freeform.trim() }
        : {
            weight_kg: num(form.weight_kg),
            body_fat_pct: num(form.body_fat_pct),
            calories: num(form.calories),
            protein_g: num(form.protein_g),
          };
    const input = {
      goal: goal ?? 'custom',
      goal_detail: goalDetail.trim(),
      ...numberInput,
      passed: result?.passed ?? null,
      fail_kind: result?.fail_kind ?? null,
      persona,
      mode,
    };
    const { data, error: insErr } = await supabase.from('gains_plans').insert({ input, status: 'pending' }).select().single();
    if (insErr || !data) {
      setPlanStatus('error');
      setPlanError(insErr?.message ?? 'Could not start.');
      return;
    }
    setPlanCheckId(data.id as string);
  }, [goal, goalDetail, inputMode, freeform, form, result, persona, mode]);

  const resetAll = () => {
    setResult(null);
    setError(null);
    setEvents([]);
    setStatus('idle');
    setCheckId(null);
    setInputMode('choose');
    setFreeform('');
    setGoal(null);
    setGoalDetail('');
    setPlanResult(null);
    setPlanError(null);
    setPlanStatus('idle');
    setPlanCheckId(null);
    setPlanEvents([]);
    setStep(0);
  };

  const busy = status === 'pending' || status === 'running';
  const planBusy = planStatus === 'pending' || planStatus === 'running';

  const planSteps = planEvents.map((e) => {
    const d = e.detail ?? {};
    if (e.stage === 'dispatched') return { icon: '⚙️', label: 'Temporal', sub: 'panel dispatched', tokens: null as number | null };
    if (e.stage === 'agent') return { icon: '🧠', label: e.label.replace('Agent · ', ''), sub: 'specialist agent', tokens: e.tokens };
    if (e.stage === 'synth') return { icon: '🧩', label: 'Head coach', sub: `synthesis · ${d.resources ?? 0} links`, tokens: e.tokens };
    if (e.stage === 'finalized') return { icon: '💾', label: 'Supabase', sub: 'plan saved', tokens: null as number | null };
    return { icon: '•', label: e.label, sub: e.stage, tokens: e.tokens };
  });
  const planTokens = planEvents.reduce((n, e) => n + (e.tokens ?? 0), 0);
  const planLastIndex = planSteps.length - 1;

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

  // When the verdict lands, scroll down to it.
  useEffect(() => {
    if (status === 'done' && result) {
      resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [status, result]);

  return (
    <div className="mx-auto max-w-2xl">
      <style>{`@keyframes gainsflash{0%,49%{opacity:1}50%,100%{opacity:.15}}@keyframes stepfade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}`}</style>

      <div className="mb-4">
        <h1 className="text-3xl font-bold tracking-tight">💪 Gains Check</h1>
        <p className="text-muted-foreground">Track your macros? The coach will let you know.</p>
      </div>

      {/* Step indicator (click a completed step to go back) */}
      <ol className="mb-5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        {STEP_LABELS.map((label, i) => (
          <li key={label} className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => !busy && !planBusy && i <= step && setStep(i)}
              disabled={busy || planBusy || i > step}
              className={`flex items-center gap-1.5 rounded-full px-2 py-1 transition-colors disabled:cursor-default ${
                i === step
                  ? 'bg-primary/10 font-medium text-foreground'
                  : i < step
                    ? 'text-foreground hover:bg-muted/50'
                    : 'text-muted-foreground'
              }`}
            >
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${
                  i <= step ? 'bg-primary text-primary-foreground' : 'border'
                }`}
              >
                {i < step ? '✓' : i + 1}
              </span>
              {label}
            </button>
            {i < STEP_LABELS.length - 1 && <span className="text-muted-foreground">›</span>}
          </li>
        ))}
      </ol>

      {/* Floating side trace navigator for the check (steps 0–3). */}
      {showTrace && step <= 3 && (
        <nav
          aria-label="Request trace"
          className="group fixed right-3 top-1/2 z-40 hidden -translate-y-1/2 flex-col items-end gap-1.5 lg:flex"
        >
          <div className="mb-0.5 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            trace {busy && <span className="animate-pulse text-primary">●</span>}
          </div>
          {steps.map((s, i) => {
            const active = i === lastDoneIndex && status !== 'done';
            return (
              <div key={i} className="flex items-center gap-2">
                <span
                  className={`max-w-[16rem] truncate rounded bg-background/90 px-1.5 py-0.5 text-[11px] shadow-sm backdrop-blur transition-all duration-200 ${
                    active ? 'opacity-100' : 'pointer-events-none opacity-0 group-hover:opacity-100'
                  } ${s.done ? 'text-foreground' : 'text-muted-foreground'}`}
                >
                  {s.icon} {s.label} · {s.sub}
                  {s.tokens != null && <span className="ml-1 text-muted-foreground">({s.tokens} tok)</span>}
                </span>
                <span
                  className={`h-1 rounded-full transition-all duration-300 ${
                    active ? 'w-8 bg-primary' : s.done ? 'w-5 bg-primary/60' : 'w-3 bg-muted-foreground/30'
                  }`}
                />
              </div>
            );
          })}
          <div className="mt-0.5 text-[10px] text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
            {totalTokens > 0 ? `${totalTokens} tokens` : ''}
          </div>
        </nav>
      )}

      {/* Floating side trace navigator for the plan panel (step 5) — agents + token usage. */}
      {step === 5 && planSteps.length > 0 && (
        <nav
          aria-label="Plan trace"
          className="group fixed right-3 top-1/2 z-40 hidden -translate-y-1/2 flex-col items-end gap-1.5 lg:flex"
        >
          <div className="mb-0.5 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            plan panel {planBusy && <span className="animate-pulse text-primary">●</span>}
          </div>
          {planSteps.map((s, i) => {
            const active = planBusy && i === planLastIndex;
            return (
              <div key={i} className="flex items-center gap-2">
                <span
                  className={`max-w-[16rem] truncate rounded bg-background/90 px-1.5 py-0.5 text-[11px] text-foreground shadow-sm backdrop-blur transition-all duration-200 ${
                    active ? 'opacity-100' : 'pointer-events-none opacity-0 group-hover:opacity-100'
                  }`}
                >
                  {s.icon} {s.label} · {s.sub}
                  {s.tokens != null && <span className="ml-1 text-muted-foreground">({s.tokens} tok)</span>}
                </span>
                <span className={`h-1 rounded-full transition-all duration-300 ${active ? 'w-8 bg-primary' : 'w-5 bg-primary/60'}`} />
              </div>
            );
          })}
          <div className="mt-0.5 text-[10px] text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
            {planTokens > 0 ? `${planTokens} tokens` : ''}
          </div>
        </nav>
      )}

      {/* Step panel — fades in on every forward/back change (keyed by step) */}
      <div key={step} style={{ animation: 'stepfade .25s ease' }} className="min-h-[16rem]">
        {step === 0 && (
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
                  className={`flex flex-col gap-0.5 rounded-md border px-3 py-3 text-left transition-colors ${
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

            <details className="mt-3 rounded-md border bg-muted/30 text-sm">
              <summary className="cursor-pointer select-none px-3 py-2 font-medium">What this does?</summary>
              <div className="border-t px-3 py-2">
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
            </details>
          </div>
        )}

        {step === 1 && (
          <div className="rounded-lg border p-4">
            <div className="mb-2 text-sm text-muted-foreground">Pick your coach</div>
            <div className="grid grid-cols-3 gap-2">
              {PERSONAS.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => setPersona(p.key)}
                  className={`flex flex-col items-center gap-0.5 rounded-md border px-2 py-3 text-center transition-colors ${
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
        )}

        {step === 2 && (
          <div className="rounded-lg border p-4">
            {inputMode === 'choose' && (
              <>
                <div className="mb-3 text-sm text-muted-foreground">How do you want to give your stats?</div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => setInputMode('numbers')}
                    className="flex flex-col gap-1 rounded-md border px-3 py-4 text-left transition-colors hover:bg-muted/50"
                  >
                    <span className="text-sm font-medium">🔢 I know my numbers</span>
                    <span className="text-xs leading-snug text-muted-foreground">
                      Enter your bodyweight (kg), body fat (%), daily calories (kcal) and protein (g).
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setInputMode('freeform')}
                    className="flex flex-col gap-1 rounded-md border px-3 py-4 text-left transition-colors hover:bg-muted/50"
                  >
                    <span className="text-sm font-medium">💬 I don't know my numbers</span>
                    <span className="text-xs leading-snug text-muted-foreground">
                      A prompt opens where you describe your eating &amp; training in plain words — the coach makes sense of it.
                    </span>
                  </button>
                </div>
              </>
            )}

            {inputMode === 'numbers' && (
              <>
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">
                    Your tracked numbers <span className="text-xs">(leave blank what you don't log)</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => setInputMode('choose')}
                    className="shrink-0 rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-muted/50"
                  >
                    ← Change method
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-4">
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
              </>
            )}

            {inputMode === 'freeform' && (
              <>
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Describe your eating &amp; training in your own words</span>
                  <button
                    type="button"
                    onClick={() => setInputMode('choose')}
                    className="shrink-0 rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-muted/50"
                  >
                    ← Change method
                  </button>
                </div>
                <textarea
                  value={freeform}
                  onChange={(e) => setFreeform(e.target.value)}
                  rows={5}
                  placeholder="e.g. I'm around 90 kg, eat roughly 3000 calories and about 180 g of protein most days, lift 4x a week — no idea on my body fat."
                  className="w-full rounded-md border px-3 py-2 text-sm"
                />
                <p className="mt-1 text-xs text-muted-foreground">The coach interprets this — the more detail, the sharper the verdict.</p>
              </>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="space-y-6">
            {error && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>
            )}

            {busy && (
              <div className="rounded-xl border p-8 text-center">
                <div className="animate-bounce text-4xl">🏋️</div>
                <p className="mt-3 text-lg font-medium">COACH IS LOOKING…</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Running the {mode === 'agentic' ? 'agentic' : 'guided'} pipeline.
                  <span className="hidden lg:inline"> Watch the live trace on the right →</span>
                </p>
                <div className="mt-4 lg:hidden">
                  <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                    <span className="truncate">
                      {steps[lastDoneIndex]?.icon} {steps[lastDoneIndex]?.label} · {steps[lastDoneIndex]?.sub}
                      <span className="ml-1 animate-pulse">●</span>
                    </span>
                    <span className="shrink-0 pl-2">{totalTokens > 0 ? `${totalTokens} tok` : ''}</span>
                  </div>
                  <div className="h-1 w-full overflow-hidden rounded bg-muted">
                    <div className="h-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              </div>
            )}

            {result && status === 'done' && (
              <div className={`rounded-xl border-4 p-6 text-center ${verdictTheme(result).border} ${verdictTheme(result).bg}`}>
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
                {TTS_ENABLED && (
                  <button type="button" onClick={() => playResult(result)} className="mt-3 text-xs underline">
                    replay sound
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {step === 4 && (
          <div className="space-y-4">
            <div className="rounded-lg border p-4">
              <div className="mb-2 text-sm text-muted-foreground">
                What's your goal? A coach panel (nutrition · training · recovery) drafts a research-based starter plan.
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {GOALS.map((g) => (
                  <button
                    key={g.key}
                    type="button"
                    onClick={() => setGoal(g.key)}
                    disabled={planBusy}
                    className={`flex flex-col gap-0.5 rounded-md border px-3 py-3 text-left transition-colors disabled:opacity-50 ${
                      goal === g.key ? 'border-primary bg-primary/10' : 'hover:bg-muted/50'
                    }`}
                  >
                    <span className="text-sm font-medium">
                      {g.emoji} {g.label}
                    </span>
                    <span className="text-xs leading-snug text-muted-foreground">{g.blurb}</span>
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setGoal('custom')}
                  disabled={planBusy}
                  className={`flex flex-col gap-0.5 rounded-md border px-3 py-3 text-left transition-colors disabled:opacity-50 sm:col-span-2 ${
                    goal === 'custom' ? 'border-primary bg-primary/10' : 'hover:bg-muted/50'
                  }`}
                >
                  <span className="text-sm font-medium">💬 Let me explain</span>
                  <span className="text-xs leading-snug text-muted-foreground">Describe your goal in your own words.</span>
                </button>
              </div>
              {goal === 'custom' && (
                <textarea
                  value={goalDetail}
                  onChange={(e) => setGoalDetail(e.target.value)}
                  rows={3}
                  placeholder="e.g. I want to look good for a wedding in 3 months but keep my strength up."
                  className="mt-2 w-full rounded-md border px-3 py-2 text-sm"
                />
              )}
            </div>

            {planError && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{planError}</div>
            )}
          </div>
        )}

        {step === 5 && (
          <div className="space-y-4">
            {planError && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{planError}</div>
            )}

            {planBusy && (
              <div className="rounded-xl border p-8 text-center">
                <div className="animate-pulse text-4xl">🧠</div>
                <p className="mt-3 text-lg font-medium">THE COACH PANEL IS RESEARCHING…</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  A nutrition, a training and a recovery specialist are weighing in — then the head coach synthesizes your plan.
                </p>
              </div>
            )}

            {planResult && planStatus === 'done' && (
              <div className="space-y-4">
                <div className="rounded-xl border-2 border-primary/50 p-5">
                  <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                    🎯 {planResult.goal_label}
                    {planResult.persona ? ` · ${planResult.persona}` : ''}
                  </div>
                  <p className="text-base">{planResult.summary}</p>
                  <div className="mt-4 grid gap-2 text-sm">
                    {planResult.calorie_guidance && (
                      <div>
                        <span className="font-semibold">🔥 Calories:</span> {planResult.calorie_guidance}
                      </div>
                    )}
                    {planResult.protein_guidance && (
                      <div>
                        <span className="font-semibold">🥩 Protein:</span> {planResult.protein_guidance}
                      </div>
                    )}
                    {planResult.training_focus && (
                      <div>
                        <span className="font-semibold">🏋️ Training:</span> {planResult.training_focus}
                      </div>
                    )}
                  </div>
                  {planResult.weekly_steps?.length > 0 && (
                    <div className="mt-4">
                      <div className="mb-1 text-sm font-semibold">This week</div>
                      <ol className="list-decimal space-y-1 pl-5 text-sm">
                        {planResult.weekly_steps.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ol>
                    </div>
                  )}
                  {planResult.resources?.length > 0 && (
                    <div className="mt-4">
                      <div className="mb-1 text-sm font-semibold">Resources</div>
                      <ul className="space-y-1 text-sm">
                        {planResult.resources.map((r, i) => (
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
                </div>

                {planResult.panel && planResult.panel.length > 0 && (
                  <details className="rounded-lg border bg-muted/30 text-sm">
                    <summary className="cursor-pointer select-none px-3 py-2 font-medium">
                      🧩 How this was made — the coach panel ({planResult.panel.length} agents + a head-coach synthesis)
                    </summary>
                    <div className="space-y-3 border-t px-3 py-3">
                      {planResult.panel.map((p, i) => (
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
              </div>
            )}
          </div>
        )}
      </div>

      {/* Wizard navigation */}
      <div className="mt-6 flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0 || busy || planBusy}
          className="rounded-md border px-4 py-2 text-sm disabled:opacity-40"
        >
          ← Back
        </button>

        {step < 2 && (
          <button
            type="button"
            onClick={() => setStep((s) => s + 1)}
            className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground"
          >
            Next: {STEP_LABELS[step + 1]} →
          </button>
        )}
        {step === 2 && (
          <button
            type="button"
            onClick={() => {
              start();
              setStep(3);
            }}
            disabled={busy || inputMode === 'choose'}
            className="rounded-md bg-primary px-6 py-2 text-base font-bold text-primary-foreground disabled:opacity-50"
          >
            {busy ? 'COACH IS LOOKING…' : '💪 CHECK MY GAINS'}
          </button>
        )}
        {step === 3 && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={resetAll}
              disabled={busy}
              className="rounded-md border px-4 py-2 text-sm disabled:opacity-40"
            >
              ↻ Start over
            </button>
            {status === 'done' && (
              <button
                type="button"
                onClick={() => setStep(4)}
                className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground"
              >
                Next: Goal →
              </button>
            )}
          </div>
        )}
        {step === 4 && (
          <button
            type="button"
            onClick={() => {
              generatePlan();
              setStep(5);
            }}
            disabled={planBusy || !goal}
            className="rounded-md bg-primary px-6 py-2 text-base font-bold text-primary-foreground disabled:opacity-50"
          >
            🎯 Create my plan
          </button>
        )}
        {step === 5 && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={resetAll}
              disabled={planBusy}
              className="rounded-md border px-4 py-2 text-sm disabled:opacity-40"
            >
              ↻ Start over
            </button>
            <button
              type="button"
              onClick={() => generatePlan()}
              disabled={planBusy || !goal}
              className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {planBusy ? 'PANEL WORKING…' : '↻ Regenerate'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
