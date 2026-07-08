/**
 * Confidence badge (ADR-0009). Renders the kernel-computed tier + plain-language
 * reasons. The tier is derived from observable signals server-side, never the
 * model's self-report — this component only displays it.
 */
interface Confidence {
  tier: 'well_grounded' | 'partial' | 'speculative';
  badge: string;
  score?: number;
  reasons?: string[];
}

const TONE: Record<Confidence['tier'], string> = {
  well_grounded: 'border-green-500 bg-green-500/10 text-green-700',
  partial: 'border-amber-500 bg-amber-500/10 text-amber-700',
  speculative: 'border-red-500 bg-red-500/10 text-red-700',
};

export function ConfidenceBadge({ confidence }: { confidence?: Confidence | null }) {
  if (!confidence) return null;
  return (
    <div className={`rounded-lg border p-3 text-sm ${TONE[confidence.tier] ?? TONE.speculative}`}>
      <div className="font-semibold">{confidence.badge}</div>
      {confidence.reasons && confidence.reasons.length > 0 && (
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
          {confidence.reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
