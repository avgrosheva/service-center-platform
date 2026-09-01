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
 */

import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RequireRole } from '@/components/shell/require-role';
import { ApiError, browserApiClient } from '@/lib/api-client';
import type { DashboardMetrics, DashboardSummary } from '@/types/api';

type DateRange = { from: string; to: string };

const EMPTY_RANGE: DateRange = { from: '', to: '' };

function formatDecimal(value: string | null): string {
  if (value === null) return '—';
  return Number(value).toFixed(2);
}

function formatHours(value: number | null): string {
  if (value === null) return '—';
  return `${value.toFixed(1)} h`;
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
        setError(err instanceof ApiError ? err.detail : 'Failed to load dashboard data.');
      } finally {
        setLoading(false);
      }
    },
    [fetchDashboard],
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
          setError(err instanceof ApiError ? err.detail : 'Failed to load dashboard data.');
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
  }, [fetchDashboard]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="date-from">From</Label>
          <Input
            id="date-from"
            type="date"
            value={range.from}
            max={range.to || undefined}
            onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))}
            className="w-40"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="date-to">To</Label>
          <Input
            id="date-to"
            type="date"
            value={range.to}
            min={range.from || undefined}
            onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))}
            className="w-40"
          />
        </div>
        <Button variant="outline" onClick={() => void load(range)} disabled={loading}>
          Apply
        </Button>
        {(range.from || range.to) && (
          <Button
            variant="ghost"
            onClick={() => {
              setRange(EMPTY_RANGE);
              void load(EMPTY_RANGE);
            }}
            disabled={loading}
          >
            Clear
          </Button>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <SummaryCard label="Active jobs" value={summary?.active_jobs} loading={loading} />
        <SummaryCard label="Delayed jobs" value={summary?.delayed_jobs} loading={loading} />
        <SummaryCard label="Completed jobs" value={summary?.completed_jobs} loading={loading} />
        <SummaryCard
          label="Unbilled additional work"
          value={summary?.unbilled_additional_work}
          loading={loading}
        />
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Avg. completion time</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {loading ? '…' : formatHours(metrics?.avg_completion_time_hours ?? null)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Average order value</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {loading ? '…' : formatDecimal(metrics?.average_order_value ?? null)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Repeat-customer rate</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {loading ? '…' : formatPercent(metrics?.repeat_customer_rate ?? 0)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Warranty cases</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {loading ? '…' : (metrics?.warranty_case_count ?? '—')}
          </CardContent>
        </Card>
        <Card className="md:col-span-2 lg:col-span-2">
          <CardHeader>
            <CardTitle>Revenue per technician</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              '…'
            ) : metrics && metrics.revenue_per_technician.length > 0 ? (
              <ul className="flex flex-col gap-2 text-sm">
                {metrics.revenue_per_technician.map((row) => (
                  <li key={row.technician_id} className="flex items-center justify-between">
                    <span>{row.technician_name}</span>
                    <span className="font-medium">{formatDecimal(row.revenue)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                No paid revenue recorded for this period yet.
              </p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  loading,
}: {
  label: string;
  value: number | undefined;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-zinc-500 dark:text-zinc-400">{label}</CardTitle>
      </CardHeader>
      <CardContent className="text-3xl font-semibold">{loading ? '…' : (value ?? '—')}</CardContent>
    </Card>
  );
}
