/**
 * Frontend feature registry (mirrors the backend ADR-0008 plugin registry).
 *
 * The launcher and header nav render one entry per enabled feature. A feature is enabled
 * by its `enabled` flag, OR — if VITE_ENABLED_FEATURES is set (comma-separated keys) — by
 * being in that allowlist (ADR-0010), so features can be toggled via env without code edits.
 */
import type { LinkProps } from '@tanstack/react-router';

export interface FeatureDef {
  key: string;
  title: string;
  description: string;
  emoji: string;
  path: LinkProps['to'];
  enabled: boolean;
}

export const FEATURES: FeatureDef[] = [
  {
    key: 'evaluate',
    title: 'Program Evaluator',
    description: 'Find Swiss higher-education study options (university / UAS / PH) that fit you.',
    emoji: '🎓',
    path: '/evaluate',
    enabled: true,
  },
  {
    key: 'plan',
    title: 'Study Planner',
    description: 'A coaching panel drafts a study plan — including how to study — for your goal.',
    emoji: '🗺️',
    path: '/plan',
    enabled: true,
  },
];

// VITE_ENABLED_FEATURES (comma-separated keys) overrides the built-in flags at build time.
const ENV_ALLOW = (import.meta.env.VITE_ENABLED_FEATURES as string | undefined)
  ?.split(',')
  .map((s) => s.trim())
  .filter(Boolean);

export const enabledFeatures = (): FeatureDef[] =>
  FEATURES.filter((f) => (ENV_ALLOW && ENV_ALLOW.length ? ENV_ALLOW.includes(f.key) : f.enabled));
