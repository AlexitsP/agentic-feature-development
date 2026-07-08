/**
 * Frontend feature registry (mirrors the backend ADR-0008 plugin registry).
 *
 * The launcher renders one card per enabled feature. Toggling `enabled` (or adding
 * an entry) is the only change needed to show/hide a feature in the UI — the
 * disabled entry below proves a feature can be registered but turned off without
 * touching anything else.
 */
export interface FeatureDef {
  key: string;
  title: string;
  description: string;
  emoji: string;
  path: string;
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

export const enabledFeatures = (): FeatureDef[] => FEATURES.filter((f) => f.enabled);
