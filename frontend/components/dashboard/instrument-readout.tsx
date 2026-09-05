import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

/**
 * A metric readout styled like a gauge card rather than a tag: the dashed
 * rule under the label is the "dial baseline" the reading sits on. Kept
 * visually distinct from InspectionTag (no status band, no grommet) so the
 * two families read as two systems within one grammar, not one repeated
 * card shape.
 */
export function InstrumentReadout({
  label,
  value,
  unit,
  loading,
  wide = false,
  children,
}: {
  label: string;
  value?: ReactNode;
  unit?: string;
  loading: boolean;
  wide?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className={cn('rounded-3xl bg-card px-5 py-4', wide && 'md:col-span-2')}>
      <p className="font-stamp text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">
        {label}
      </p>
      {children ?? (
        <p className="mt-2 flex items-baseline gap-1.5 border-t border-dashed border-border pt-2.5 font-mono text-2xl font-semibold tabular-nums text-card-foreground">
          {loading ? '···' : value}
          {unit && !loading && (
            <span className="font-sans text-sm font-normal text-muted-foreground">{unit}</span>
          )}
        </p>
      )}
    </div>
  );
}
