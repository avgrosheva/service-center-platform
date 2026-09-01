'use client';

/**
 * Milestone F7 — filterable jobs list, viewable by all three roles (the
 * backend's `_can_view_or_act_on_jobs` gate). For a technician, the list
 * is transparently scoped server-side to their own assigned jobs
 * (job_service.list_jobs overrides any `assigned_technician_id` a
 * technician-role caller sends) — so the technician filter dropdown is
 * simply not rendered for them (it would filter a list that's already
 * always just "their own jobs"), and `GET /users` (owner/dispatcher only)
 * is never called for a technician viewer either.
 *
 * Filters auto-apply on change (no "Apply" button, unlike the dashboard's
 * date range) — each control here is a single deliberate action (a select
 * or a date input), not free text, so there's no debounce concern the way
 * customers/page.tsx's search box has.
 *
 * `scheduled_from`/`scheduled_to` are `datetime` query params on the
 * backend (job_service.list_jobs does a raw `>=`/`<=` comparison, unlike
 * dashboard_service's own date_from/date_to which it expands to full-day
 * boundaries server-side) — so a "From"/"To" date picked here is expanded
 * to a full-day boundary client-side before being sent, or the "To" date
 * itself would silently exclude same-day jobs scheduled after midnight.
 *
 * Milestone F13: a technician viewer gets a genuinely different render —
 * a single full-width status filter plus a card list (one large tappable
 * card per job) instead of the table, per the roadmap's explicit "larger
 * tap targets, less information density" for a technician's own view.
 * Same `jobs`/`loading`/`error` state and the same `load()` fetch either
 * way — only the JSX differs, so there's exactly one source of truth for
 * the data.
 */

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { RequireRole } from '@/components/shell/require-role';
import { JOB_STATUS_LABELS, JobStatusBadge } from '@/components/jobs/job-status-badge';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth';
import type { Job, JobStatus, User } from '@/types/api';

const ALL_STATUSES = Object.keys(JOB_STATUS_LABELS) as JobStatus[];

const SELECT_CLASS =
  'h-8 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30';

export default function JobsPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher', 'technician']}>
      <JobsContent />
    </RequireRole>
  );
}

function JobsContent() {
  const { user } = useAuth();
  const isTechnician = user?.role === 'technician';

  const [statusFilter, setStatusFilter] = useState<JobStatus | ''>('');
  const [technicianFilter, setTechnicianFilter] = useState('');
  const [scheduledFrom, setScheduledFrom] = useState('');
  const [scheduledTo, setScheduledTo] = useState('');

  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [technicians, setTechnicians] = useState<User[]>([]);

  useEffect(() => {
    if (isTechnician) return;
    let cancelled = false;
    void (async () => {
      try {
        const users = await browserApiClient<User[]>('/users');
        if (!cancelled) setTechnicians(users.filter((u) => u.role === 'technician'));
      } catch {
        // Non-fatal — the technician filter dropdown just stays empty; the list itself doesn't depend on this.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isTechnician]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await browserApiClient<Job[]>('/jobs', {
        params: {
          status: statusFilter || undefined,
          assigned_technician_id: isTechnician ? undefined : technicianFilter || undefined,
          scheduled_from: scheduledFrom ? `${scheduledFrom}T00:00:00` : undefined,
          scheduled_to: scheduledTo ? `${scheduledTo}T23:59:59` : undefined,
        },
      });
      setJobs(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load jobs.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, technicianFilter, scheduledFrom, scheduledTo, isTechnician]);

  // Fires on mount and again on every filter change — see module docstring
  // for why this stays outside a bare synchronous effect body.
  useEffect(() => {
    const handle = setTimeout(() => void load(), 0);
    return () => clearTimeout(handle);
  }, [load]);

  const technicianNameById = useMemo(() => {
    const map: Record<string, string> = {};
    for (const tech of technicians) map[tech.id] = tech.full_name;
    if (isTechnician && user) map[user.id] = user.full_name;
    return map;
  }, [technicians, isTechnician, user]);

  if (isTechnician) {
    return (
      <div className="flex flex-col gap-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as JobStatus | '')}
          className="h-11 w-full rounded-lg border border-input bg-transparent px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        >
          <option value="">All statuses</option>
          {ALL_STATUSES.map((s) => (
            <option key={s} value={s}>
              {JOB_STATUS_LABELS[s]}
            </option>
          ))}
        </select>

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {loading ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
        ) : !jobs || jobs.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No jobs match this filter.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {jobs.map((job) => (
              <Link
                key={job.id}
                href={`/jobs/${job.id}`}
                className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-4 active:bg-zinc-50 dark:border-zinc-800 dark:active:bg-zinc-900"
              >
                <div className="flex items-center justify-between gap-2">
                  <JobStatusBadge status={job.status} />
                  {job.scheduled_at && (
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">
                      {new Date(job.scheduled_at).toLocaleString(undefined, {
                        month: 'short',
                        day: 'numeric',
                        hour: 'numeric',
                        minute: '2-digit',
                      })}
                    </span>
                  )}
                </div>
                <p className="text-base font-medium">{job.reported_issue}</p>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">{job.address_snapshot}</p>
              </Link>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label
            className="text-xs font-medium text-zinc-500 dark:text-zinc-400"
            htmlFor="status-filter"
          >
            Status
          </label>
          <select
            id="status-filter"
            className={SELECT_CLASS}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as JobStatus | '')}
          >
            <option value="">All statuses</option>
            {ALL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {JOB_STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>

        {!isTechnician && (
          <div className="flex flex-col gap-1">
            <label
              className="text-xs font-medium text-zinc-500 dark:text-zinc-400"
              htmlFor="tech-filter"
            >
              Technician
            </label>
            <select
              id="tech-filter"
              className={SELECT_CLASS}
              value={technicianFilter}
              onChange={(e) => setTechnicianFilter(e.target.value)}
            >
              <option value="">All technicians</option>
              {technicians.map((tech) => (
                <option key={tech.id} value={tech.id}>
                  {tech.full_name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label
            className="text-xs font-medium text-zinc-500 dark:text-zinc-400"
            htmlFor="scheduled-from"
          >
            Scheduled from
          </label>
          <input
            id="scheduled-from"
            type="date"
            value={scheduledFrom}
            max={scheduledTo || undefined}
            onChange={(e) => setScheduledFrom(e.target.value)}
            className={SELECT_CLASS}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label
            className="text-xs font-medium text-zinc-500 dark:text-zinc-400"
            htmlFor="scheduled-to"
          >
            Scheduled to
          </label>
          <input
            id="scheduled-to"
            type="date"
            value={scheduledTo}
            min={scheduledFrom || undefined}
            onChange={(e) => setScheduledTo(e.target.value)}
            className={SELECT_CLASS}
          />
        </div>

        {!isTechnician && (
          <Button render={<Link href="/jobs/new" />} nativeButton={false} className="ml-auto">
            New job
          </Button>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
      ) : !jobs || jobs.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No jobs match these filters.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
              <tr>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Reported issue</th>
                <th className="px-4 py-2 font-medium">Address</th>
                <th className="px-4 py-2 font-medium">Scheduled</th>
                <th className="px-4 py-2 font-medium">Technician</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr
                  key={job.id}
                  className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
                >
                  <td className="px-4 py-2">
                    <Link href={`/jobs/${job.id}`}>
                      <JobStatusBadge status={job.status} />
                    </Link>
                  </td>
                  <td className="max-w-xs truncate px-4 py-2">
                    <Link href={`/jobs/${job.id}`} className="hover:underline">
                      {job.reported_issue}
                    </Link>
                  </td>
                  <td className="max-w-xs truncate px-4 py-2 text-zinc-600 dark:text-zinc-400">
                    {job.address_snapshot}
                  </td>
                  <td className="px-4 py-2 text-zinc-600 dark:text-zinc-400">
                    {job.scheduled_at ? new Date(job.scheduled_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-2 text-zinc-600 dark:text-zinc-400">
                    {job.assigned_technician_id
                      ? (technicianNameById[job.assigned_technician_id] ?? '—')
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
