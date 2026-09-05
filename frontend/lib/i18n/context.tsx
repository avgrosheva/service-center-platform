'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { en } from './en';
import { ru } from './ru';

export type Locale = 'en' | 'ru';

const DICTIONARIES = { en, ru };
const STORAGE_KEY = 'fsp_locale';

/** Every dot-joined path down to a string leaf in the English dictionary
 * (the source of truth for keys) — gives `t()` autocomplete + a compile
 * error on a typo'd key, without hand-writing a union of ~200 strings. */
type PathsToStrings<T> = T extends string
  ? never
  : {
      [K in Extract<keyof T, string>]: T[K] extends string ? K : `${K}.${PathsToStrings<T[K]>}`;
    }[Extract<keyof T, string>];

export type TranslationKey = PathsToStrings<typeof en>;

function resolve(dict: Record<string, unknown>, key: string): string | undefined {
  let node: unknown = dict;
  for (const part of key.split('.')) {
    if (typeof node !== 'object' || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === 'string' ? node : undefined;
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}

function detectInitialLocale(): Locale {
  if (typeof window === 'undefined') return 'en';
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'en' || stored === 'ru') return stored;
  } catch {
    // localStorage can throw in a locked-down/private context — fall
    // through to the browser-language guess below.
  }
  return navigator.language.toLowerCase().startsWith('ru') ? 'ru' : 'en';
}

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

/**
 * Wraps the whole app (see app/layout.tsx) so every client component can
 * call `useLocale()`. Locale starts as `'en'` on the server and during
 * the first client render (matching Next's SSR output, avoiding a
 * hydration mismatch), then syncs to the stored/detected preference
 * immediately after mount — a one-frame flash to Russian for a returning
 * Russian-locale visitor is the deliberate trade for that safety.
 */
export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>('en');

  // Deferred one tick (rather than called synchronously in the effect
  // body) — matches this codebase's established pattern elsewhere
  // (jobs/page.tsx's filter-change effect, customers/page.tsx's search
  // effect) for satisfying `react-hooks/set-state-in-effect`, which flags
  // a same-tick setState in an effect body as a cascading-render risk.
  useEffect(() => {
    const handle = setTimeout(() => setLocaleState(detectInitialLocale()), 0);
    return () => clearTimeout(handle);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Non-fatal — the choice just won't persist across reloads.
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => {
      const dict = DICTIONARIES[locale] as unknown as Record<string, unknown>;
      const value = resolve(dict, key) ?? resolve(en as unknown as Record<string, unknown>, key);
      return interpolate(value ?? key, vars);
    },
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error('useLocale must be used within a LocaleProvider');
  return ctx;
}
