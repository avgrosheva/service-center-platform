'use client';

/**
 * Milestone F14 — day/week list of scheduled jobs, per the Product
 * Definition's explicit "basic — day/week list, not a full calendar
 * widget" scope. Reuses `GET /jobs` (F7) with no query params — the
 * backend has no "scheduled_at IS NULL" filter, and bucketing a modest
 * org's full job list into day/week/unscheduled groups client-side is
 * simpler and cheaper than two separate fetches.
 */

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { RequireRole } from '@/components/shell/require-role';
import { JobStatusBadge } from '@/components/jobs/job-status-badge';
import { useLocale } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import type { Job } from '@/types/api';

type ViewMode = 'day' | 'week';

function dateKey(d: Date): string {
  return d.toLocaleDateString('en-CA'); // YYYY-MM-DD, stable for grouping/sorting
}

function startOfWeek(d: Date): Date {
  const copy = new Date(d);
  const day = copy.getDay(); // 0=Sun
  const diff = day === 0 ? -6 : 1 - day; // Monday-start week
  copy.setDate(copy.getDate() + diff);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

export default function SchedulePage() {
  return (
    <RequireRole allow={['owner', 'dispatcher']}>
      <ScheduleContent />
    </RequireRole>
  );
}

function ScheduleContent() {
  const { t, locale } = useLocale();
  const dateLocale = locale === 'ru' ? 'ru-RU' : 'en-US';
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('day');
  const [anchor, setAnchor] = useState(() => new Date());

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<Job[]>('/jobs');
        if (!cancelled) setJobs(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.detail : t('jobs.failedToLoad'));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { byDay, unscheduled } = useMemo(() => {
    const byDay = new Map<string, Job[]>();
    const unscheduled: Job[] = [];
    for (const job of jobs ?? []) {
      if (!job.scheduled_at) {
        unscheduled.push(job);
        continue;
      }
      const key = dateKey(new Date(job.scheduled_at));
      (byDay.get(key) ?? byDay.set(key, []).get(key)!).push(job);
    }
    for (const list of byDay.values()) {
      list.sort((a, b) => (a.scheduled_at ?? '').localeCompare(b.scheduled_at ?? ''));
    }
    return { byDay, unscheduled };
  }, [jobs]);

  const days: Date[] =
    viewMode === 'day'
      ? [anchor]
      : Array.from({ length: 7 }, (_, i) => {
          const d = startOfWeek(anchor);
          d.setDate(d.getDate() + i);
          return d;
        });

  const shift = (amount: number) => {
    const next = new Date(anchor);
    next.setDate(next.getDate() + amount * (viewMode === 'day' ? 1 : 7));
    setAnchor(next);
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <h1 className="text-3xl font-semibold tracking-tight text-foreground">
        {t('schedule.title')}
      </h1>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          <Button
            variant={viewMode === 'day' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setViewMode('day')}
          >
            {t('schedule.day')}
          </Button>
          <Button
            variant={viewMode === 'week' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setViewMode('week')}
          >
            {t('schedule.week')}
          </Button>
        </div>
        <Button variant="ghost" size="sm" onClick={() => shift(-1)}>
          {t('schedule.prev')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setAnchor(new Date())}>
          {t('schedule.today')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => shift(1)}>
          {t('schedule.next')}
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {jobs === null ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : (
        <div className="flex flex-col gap-4">
          {days.map((d) => {
            const key = dateKey(d);
            const dayJobs = byDay.get(key) ?? [];
            return (
              <div key={key} className="rounded-3xl bg-card p-4">
                <p className="mb-2 text-sm font-medium">
                  {d.toLocaleDateString(dateLocale, {
                    weekday: 'long',
                    month: 'short',
                    day: 'numeric',
                  })}
                </p>
                {dayJobs.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t('schedule.noJobsScheduled')}</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {dayJobs.map((job) => (
                      <li key={job.id}>
                        <Link
                          href={`/jobs/${job.id}`}
                          className="flex items-center gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                        >
                          <span className="w-14 shrink-0 text-muted-foreground">
                            {new Date(job.scheduled_at!).toLocaleTimeString(dateLocale, {
                              hour: 'numeric',
                              minute: '2-digit',
                            })}
                          </span>
                          <JobStatusBadge status={job.status} />
                          <span className="truncate">{job.reported_issue}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}

          <div className="rounded-3xl bg-card p-4">
            <p className="mb-2 text-sm font-medium">{t('schedule.unscheduled')}</p>
            {unscheduled.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('schedule.nothingUnscheduled')}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {unscheduled.map((job) => (
                  <li key={job.id}>
                    <Link
                      href={`/jobs/${job.id}`}
                      className="flex items-center gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                    >
                      <JobStatusBadge status={job.status} />
                      <span className="truncate">{job.reported_issue}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
