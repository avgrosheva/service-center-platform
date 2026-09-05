import type { ComponentType, ReactNode } from 'react';

import { cn } from '@/lib/utils';

/**
 * The dashboard's summary tile: a bold rounded card with a small icon
 * badge and a big number, in the "studio console" world's two-tone
 * language — most cards are neutral (white-on-sage), exactly one per
 * screen carries the bright accent fill to draw the eye, the way the
 * reference material spends its one accent color on a single hero card
 * rather than scattering it.
 */
export function MetricCard({
  icon: Icon,
  label,
  value,
  loading,
  variant = 'neutral',
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: ReactNode;
  loading: boolean;
  variant?: 'neutral' | 'accent';
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-4 rounded-3xl p-5',
        variant === 'accent'
          ? 'bg-primary text-primary-foreground'
          : 'bg-card text-card-foreground',
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
            variant === 'accent' ? 'bg-primary-foreground/15' : 'bg-background',
          )}
        >
          <Icon className="h-4 w-4" />
        </span>
        <p className="text-sm font-medium">{label}</p>
      </div>
      <p className="font-mono text-4xl font-semibold tabular-nums">{loading ? '···' : value}</p>
    </div>
  );
}
