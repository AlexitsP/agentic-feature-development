/**
 * EngineInsightsPanel
 *
 * Custom engine component that runs the Entity Insights Assistant and shows the
 * agentic loop live. It inserts a run row, then subscribes to Supabase Realtime
 * for the steps and the final result. Registered as "InsightsPanel".
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { supabase } from '@/data/supabase';
import { useUIEngine } from '@/engine/UIEngineContext';
import type { EngineComponentProps } from '@/engine/types';

interface InsightStep {
  id: string;
  seq: number;
  tool: string;
  args: Record<string, unknown>;
  result_preview: unknown;
}

interface InsightResult {
  summary?: string;
  notable_facts?: Array<{ label: string; value: number | string; unit?: string }>;
  data_completeness?: string;
}

type RunStatus = 'idle' | 'pending' | 'running' | 'done' | 'error';

export function EngineInsightsPanel(_props: EngineComponentProps) {
  const { params } = useUIEngine();
  const entityId = params.id;

  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<RunStatus>('idle');
  const [steps, setSteps] = useState<InsightStep[]>([]);
  const [result, setResult] = useState<InsightResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startingRef = useRef(false);

  const start = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    setSteps([]);
    setResult(null);
    setError(null);
    setStatus('pending');
    const { data, error: insErr } = await supabase
      .from('insight_runs')
      .insert({ entity_id: entityId, question: 'Summarize this entity', status: 'pending' })
      .select()
      .single();
    startingRef.current = false;
    if (insErr || !data) {
      setStatus('error');
      setError(insErr?.message ?? 'Failed to start the insight run.');
      return;
    }
    setRunId(data.id as string);
  }, [entityId]);

  useEffect(() => {
    if (!runId) return;
    const channel = supabase
      .channel(`insight-${runId}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'insight_steps', filter: `run_id=eq.${runId}` },
        (payload) => setSteps((prev) => [...prev, payload.new as InsightStep].sort((a, b) => a.seq - b.seq)),
      )
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'insight_runs', filter: `id=eq.${runId}` },
        (payload) => {
          const row = payload.new as { status: RunStatus; result: InsightResult | null; error: string | null };
          setStatus(row.status);
          if (row.result) setResult(row.result);
          if (row.error) setError(row.error);
        },
      )
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [runId]);

  const busy = status === 'pending' || status === 'running';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Ask the assistant to summarize this entity using its own data.
        </p>
        <button
          type="button"
          onClick={start}
          disabled={busy}
          className="inline-flex items-center rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {busy ? 'Working…' : 'Ask for insights'}
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error} — try again.
        </div>
      )}

      {(busy || steps.length > 0) && (
        <ol className="space-y-2">
          {steps.map((step) => (
            <li key={step.id} className="rounded-md border p-2 text-sm">
              <div className="font-medium">
                {step.seq}. {step.tool}
                {step.args?.entity_id ? (
                  <span className="text-muted-foreground"> ({String(step.args.entity_id)})</span>
                ) : null}
              </div>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
                {JSON.stringify(step.result_preview, null, 2)}
              </pre>
            </li>
          ))}
          {busy && <li className="animate-pulse text-sm text-muted-foreground">Assistant is working…</li>}
        </ol>
      )}

      {status === 'done' && result && (
        <div className="rounded-md border bg-muted/30 p-4">
          <div className="mb-1 flex items-center gap-2">
            <span className="font-medium">Insight</span>
            {result.data_completeness && (
              <span className="rounded bg-secondary px-1.5 py-0.5 text-xs">{result.data_completeness}</span>
            )}
          </div>
          <p className="text-sm">{result.summary}</p>
          {result.notable_facts && result.notable_facts.length > 0 && (
            <ul className="mt-3 space-y-1">
              {result.notable_facts.map((f, i) => (
                <li key={i} className="text-sm">
                  <span className="text-muted-foreground">{f.label}: </span>
                  <span className="font-medium">
                    {f.value}
                    {f.unit ? ` ${f.unit}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
