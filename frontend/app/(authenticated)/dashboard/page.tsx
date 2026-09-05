'use client';

/**
 * Milestone F4 — the owner/dispatcher landing page. Replaces F2's
 * placeholder entirely.
 *
 * Date range: a single `{from, to}` pair, sent as `date_from`/`date_to`
 * query params to BOTH `/dashboard/summary` and `/dashboard/metrics` —
 * deliberately, even though the roadmap doc's own prose says the range
 * only affects "the metrics section, not the summary section". Reading
 * app/services/dashboard_service.py directly (not just the roadmap)
 * shows the real, more precise behavior: `get_summary` itself accepts
 * and partially honors the range — `active_jobs`/`delayed_jobs` are
 * always a current-state snapshot regardless of what's passed (there's
 * no meaningful date-range reading of "how many jobs are active right
 * now"), while `completed_jobs`/`unbilled_additional_work` DO filter by
 * their own natural timestamp. Sending the range to both endpoints
 * reproduces that exact per-field backend behavior for free — the two
 * snapshot fields simply won't move when the range changes, which is
 * correct, not a bug — rather than the frontend re-deriving which two
 * fields are and aren't date-scoped and only special-casing those.
 *
 * Visual direction: "Studio Console" (see
 * .impeccable/surfaces/…dashboard-page-tsx.md, direction v3 — a second
 * user-pinned reference, superseding v2's dark "Night Ops Console").
 * Soft sage ground, floating black icon rail, bold display type, one
 * bright accent color (#04CA8B, the user's own pick) doing all the
 * pointing. Originated here, then promoted to the whole app's default
 * palette (globals.css `:root`) once the user confirmed the direction.
 */

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Receipt, Wrench } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { MetricCard } from '@/components/dashboard/metric-card';
import { InstrumentReadout } from '@/components/dashboard/instrument-readout';
import { PercentRing } from '@/components/dashboard/percent-ring';
import { LollipopChart } from '@/components/dashboard/lollipop-chart';
import { RequireRole } from '@/components/shell/require-role';
import { useLocale } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import type { DashboardMetrics, DashboardSummary } from '@/types/api';

type DateRange = { from: string; to: string };

const EMPTY_RANGE: DateRange = { from: '', to: '' };

function formatDecimal(value: string | null): string {
  if (value === null) return '—';
  return Number(value).toFixed(2);
}

function formatHours(value: number | null, unit: string): string {
  if (value === null) return '—';
  return `${value.toFixed(1)} ${unit}`;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function DashboardPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher']}>
      <DashboardContent />
    </RequireRole>
  );
}

function DashboardContent() {
  const { t } = useLocale();
  const [range, setRange] = useState<DateRange>(EMPTY_RANGE);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchDashboard = useCallback(async (r: DateRange) => {
    const params = { date_from: r.from || undefined, date_to: r.to || undefined };
    const [summaryData, metricsData] = await Promise.all([
      browserApiClient<DashboardSummary>('/dashboard/summary', { params }),
      browserApiClient<DashboardMetrics>('/dashboard/metrics', { params }),
    ]);
    setSummary(summaryData);
    setMetrics(metricsData);
  }, []);

  // User-triggered reload (Apply/Clear below) — setting `loading`/`error`
  // synchronously here is fine, since click handlers aren't Effects.
  const load = useCallback(
    async (r: DateRange) => {
      setLoading(true);
      setError(null);
      try {
        await fetchDashboard(r);
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : t('dashboard.failedToLoad'));
      } finally {
        setLoading(false);
      }
    },
    [fetchDashboard, t],
  );

  // Initial load on mount — `loading`/`error` already start at their
  // correct values (true/null), so nothing is set synchronously here;
  // matches lib/auth.tsx's identical "fetch on mount" shape.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await fetchDashboard(EMPTY_RANGE);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.detail : t('dashboard.failedToLoad'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchDashboard, t]);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            {t('dashboard.title')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('dashboard.subtitle')}</p>
        </div>

        <div className="flex flex-wrap items-end gap-3 rounded-full bg-card px-4 py-2">
          <div className="flex flex-col gap-0.5">
            <Label htmlFor="date-from" className="text-[10px] text-muted-foreground">
              {t('common.from')}
            </Label>
            <Input
              id="date-from"
              type="date"
              value={range.from}
              max={range.to || undefined}
              onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))}
              className="h-6 w-32 border-0 bg-transparent p-0 font-mono text-xs tabular-nums shadow-none focus-visible:ring-0"
            />
          </div>
          <div className="flex flex-col gap-0.5">
            <Label htmlFor="date-to" className="text-[10px] text-muted-foreground">
              {t('common.to')}
            </Label>
            <Input
              id="date-to"
              type="date"
              value={range.to}
              min={range.from || undefined}
              onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))}
              className="h-6 w-32 border-0 bg-transparent p-0 font-mono text-xs tabular-nums shadow-none focus-visible:ring-0"
            />
          </div>
          <Button
            className="rounded-full"
            onClick={() => void load(range)}
            disabled={loading}
            size="sm"
          >
            {t('common.apply')}
          </Button>
          {(range.from || range.to) && (
            <Button
              variant="ghost"
              className="rounded-full"
              size="sm"
              onClick={() => {
                setRange(EMPTY_RANGE);
                void load(EMPTY_RANGE);
              }}
              disabled={loading}
            >
              {t('common.clear')}
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="relative overflow-hidden rounded-3xl bg-card px-4 py-3 pl-5 text-sm text-destructive">
          <span aria-hidden className="absolute inset-y-0 left-0 w-1.5 bg-status-delayed" />
          {error}
        </div>
      )}

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard
          icon={Wrench}
          label={t('dashboard.activeJobs')}
          value={summary?.active_jobs ?? '—'}
          loading={loading}
          variant="accent"
        />
        <MetricCard
          icon={AlertTriangle}
          label={t('dashboard.delayedJobs')}
          value={summary?.delayed_jobs ?? '—'}
          loading={loading}
        />
        <MetricCard
          icon={CheckCircle2}
          label={t('dashboard.completedJobs')}
          value={summary?.completed_jobs ?? '—'}
          loading={loading}
        />
        <MetricCard
          icon={Receipt}
          label={t('dashboard.unbilledAdditionalWork')}
          value={summary?.unbilled_additional_work ?? '—'}
          loading={loading}
        />
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <InstrumentReadout
          label={t('dashboard.avgCompletionTime')}
          value={formatHours(metrics?.avg_completion_time_hours ?? null, t('dashboard.hoursUnit'))}
          loading={loading}
        />
        <InstrumentReadout
          label={t('dashboard.averageOrderValue')}
          value={formatDecimal(metrics?.average_order_value ?? null)}
          loading={loading}
        />
        <InstrumentReadout label={t('dashboard.repeatCustomerRate')} loading={loading}>
          {loading ? (
            <p className="mt-2 font-mono text-2xl font-semibold text-card-foreground">···</p>
          ) : (
            <div className="mt-2 flex items-center gap-3">
              <div className="relative text-primary">
                <PercentRing value={metrics?.repeat_customer_rate ?? 0} />
                <span className="absolute inset-0 flex items-center justify-center font-mono text-[11px] font-semibold text-card-foreground">
                  {formatPercent(metrics?.repeat_customer_rate ?? 0).replace('.0%', '%')}
                </span>
              </div>
              <span className="text-xs text-muted-foreground">
                {t('dashboard.ofJobsAreRepeatCustomers')}
              </span>
            </div>
          )}
        </InstrumentReadout>
        <InstrumentReadout
          label={t('dashboard.warrantyCases')}
          value={metrics?.warranty_case_count ?? '—'}
          loading={loading}
        />
        <InstrumentReadout label={t('dashboard.revenuePerTechnician')} loading={loading} wide>
          <LollipopChart
            loading={loading}
            data={(metrics?.revenue_per_technician ?? []).map((row) => ({
              id: row.technician_id,
              label: row.technician_name,
              value: Number(row.revenue),
              formattedValue: formatDecimal(row.revenue),
            }))}
          />
        </InstrumentReadout>
      </section>
    </div>
  );
}
