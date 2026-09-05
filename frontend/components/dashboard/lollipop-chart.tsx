import { useLocale } from '@/lib/i18n/context';

/**
 * Revenue per technician as a lollipop chart — a thin stem topped by a
 * round knob, height scaled to each technician's real revenue relative
 * to the group's max. The signature device from the reference material,
 * applied to data that's actually comparable across categories (unlike
 * the day-by-day series the reference charted, which this product has
 * no equivalent of — no daily granularity exists in the API, so this
 * reads technician-to-technician instead of day-to-day).
 */
export function LollipopChart({
  data,
  loading,
}: {
  data: { id: string; label: string; value: number; formattedValue: string }[];
  loading: boolean;
}) {
  const { t } = useLocale();

  if (loading) {
    return <p className="font-mono text-2xl font-semibold text-card-foreground">···</p>;
  }

  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('dashboard.noPaidRevenue')}</p>;
  }

  const max = Math.max(...data.map((d) => d.value), 1);
  // The stem itself never exceeds `stemHeight`; the box reserves extra
  // headroom above that for the knob + value badge, so the tallest
  // column's badge sits inside the scroll container's bounds instead of
  // being clipped by the `overflow-x-auto` box (setting overflow on one
  // axis makes the other axis clip too, per the CSS overflow spec).
  const stemHeight = 110;
  const boxHeight = stemHeight + 40;

  return (
    <div className="flex items-end gap-6 overflow-x-auto pb-1">
      {data.map((d) => {
        const height = Math.max((d.value / max) * stemHeight, 6);
        return (
          <div
            key={d.id}
            className="flex shrink-0 flex-col items-center gap-2"
            style={{ width: 84 }}
          >
            <div className="relative" style={{ height: boxHeight }}>
              <span
                className="absolute bottom-0 left-1/2 w-[3px] -translate-x-1/2 rounded-full bg-foreground/15"
                style={{ height }}
              />
              <span
                className="absolute left-1/2 -translate-x-1/2 rounded-full bg-primary px-2 py-0.5 font-mono text-[10px] font-semibold whitespace-nowrap text-primary-foreground"
                style={{ bottom: height + 14 }}
              >
                {d.formattedValue}
              </span>
              <span
                className="absolute left-1/2 h-3.5 w-3.5 -translate-x-1/2 translate-y-1/2 rounded-full bg-primary"
                style={{ bottom: height }}
              />
            </div>
            <p
              className="w-full truncate text-center text-xs text-muted-foreground"
              title={d.label}
            >
              {d.label}
            </p>
          </div>
        );
      })}
    </div>
  );
}
