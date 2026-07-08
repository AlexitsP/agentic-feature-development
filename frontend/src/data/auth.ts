/**
 * Auth (ADR-0007). Ensures a Supabase Auth session so run rows are owner-scoped by
 * RLS. Uses anonymous sign-in so the app works without a full sign-up flow while still
 * giving each visitor their own `auth.uid()` (and thus per-user isolation). Swap in a
 * real email/SSO sign-in later without changing callers — they just await `ensureSession`.
 */
import { supabase } from './supabase';

let sessionPromise: Promise<void> | null = null;

export function ensureSession(): Promise<void> {
  if (!sessionPromise) {
    sessionPromise = (async () => {
      const { data } = await supabase.auth.getSession();
      if (!data.session) {
        await supabase.auth.signInAnonymously();
      }
    })();
  }
  return sessionPromise;
}

/** ADR-0011: ensure a session only for features that declare `requiresAuth`. */
export function ensureSessionIf(required: boolean): Promise<void> {
  return required ? ensureSession() : Promise.resolve();
}
