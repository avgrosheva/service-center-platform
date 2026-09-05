'use client';

import { useLocale } from '@/lib/i18n/context';
import { cn } from '@/lib/utils';

const OTHER: Record<'en' | 'ru', 'en' | 'ru'> = { en: 'ru', ru: 'en' };
const LABEL: Record<'en' | 'ru', string> = { en: 'EN', ru: 'RU' };

/**
 * Shows the *other* language as the button's label — clicking it always
 * reads as "switch to ___", the common convention for a two-language
 * toggle. `compact` drops to icon-rail sizing (h-10 w-10 circle, matching
 * PillNavIcon) for the desktop pill rail; the default size fits standalone
 * placements (mobile drawer, login/register pages).
 */
export function LocaleToggle({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale } = useLocale();
  const target = OTHER[locale];

  return (
    <button
      type="button"
      onClick={() => setLocale(target)}
      aria-label={`Switch to ${target === 'ru' ? 'Russian' : 'English'}`}
      title={target === 'ru' ? 'Русский' : 'English'}
      className={cn(
        'flex shrink-0 items-center justify-center rounded-full font-mono text-[11px] font-semibold tracking-wide transition-colors',
        compact
          ? 'h-10 w-10 text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
          : 'h-8 w-8 border border-border bg-card text-muted-foreground hover:text-foreground',
      )}
    >
      {LABEL[target]}
    </button>
  );
}
