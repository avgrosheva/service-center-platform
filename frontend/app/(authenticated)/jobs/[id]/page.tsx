'use client';

/**
 * Milestone F9 — the central job screen: info panel, status transitions,
 * assignment, cancel, and the activity timeline. Milestone F10 adds the
 * Photos and Materials sections below Actions; Milestone F11 adds
 * Additional Work and Payment; Milestone F12 adds Documents. Payment is
 * the one section never rendered for a technician viewer at all (not
 * even read-only) — the backend blocks it entirely, unlike every other
 * sub-resource's "flag/view yes, decide/manage no" split.
 *
 * Role split mirrors the backend's own two gates exactly:
 * - `_can_manage_jobs` (owner/dispatcher): editing info fields, assigning
 *   a technician, cancelling. None of these controls render for a
 *   technician viewer.
 * - `_can_view_or_act_on_jobs` (owner/dispatcher/technician): viewing,
 *   and the forward status-transition buttons — a technician can move
 *   their own assigned job forward through its states, just not
 *   reassign or cancel it.
 *
 * A technician who isn't assigned to this job gets a 403
 * (`ForbiddenJobAccessError`) from the backend, not a 404 — the job
 * genuinely exists in their organization, it's just not theirs to act on
 * or view. Handled as its own distinct empty-state, separate from a true
 * 404 (wrong org / nonexistent id).
 */

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RequireRole } from '@/components/shell/require-role';
import { JOB_STATUS_LABELS, JobStatusBadge } from '@/components/jobs/job-status-badge';
import {
  JOB_STATUS_FORWARD_TRANSITIONS,
  canCancelFromStatus,
} from '@/components/jobs/job-status-transitions';
import { JobTimeline } from '@/components/jobs/job-timeline';
import { JobPhotos } from '@/components/jobs/job-photos';
import { JobMaterials } from '@/components/jobs/job-materials';
import { JobAdditionalWork } from '@/components/jobs/job-additional-work';
import { JobPayment } from '@/components/jobs/job-payment';
import { JobDocuments } from '@/components/jobs/job-documents';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { parseFieldErrors } from '@/lib/form-errors';
import { useAuth } from '@/lib/auth';
import type {
  Job,
  JobAssignRequest,
  JobStatus,
  JobStatusChangeRequest,
  JobStatusHistoryEntry,
  JobUpdateRequest,
  User,
} from '@/types/api';

function toDatetimeLocalValue(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function JobDetailPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher', 'technician']}>
      <JobDetailContent />
    </RequireRole>
  );
}

function JobDetailContent() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const isTechnician = user?.role === 'technician';

  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [timeline, setTimeline] = useState<JobStatusHistoryEntry[] | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [editValues, setEditValues] = useState({
    reported_issue: '',
    address_snapshot: '',
    scheduled_at: '',
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  const [allUsers, setAllUsers] = useState<User[]>([]);
  const [selectedTechForAssign, setSelectedTechForAssign] = useState('');
  const [assigning, setAssigning] = useState(false);

  const [changingStatus, setChangingStatus] = useState<JobStatus | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const reloadTimeline = useCallback(async () => {
    try {
      const data = await browserApiClient<JobStatusHistoryEntry[]>(`/jobs/${id}/timeline`);
      setTimeline(data);
    } catch (err) {
      setTimelineError(err instanceof ApiError ? err.detail : 'Failed to load timeline.');
    }
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<Job>(`/jobs/${id}`);
        if (!cancelled) setJob(data);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.kind === 'not_found') {
          setNotFound(true);
        } else if (err instanceof ApiError && err.kind === 'forbidden') {
          setForbidden(true);
        } else {
          setLoadError(err instanceof ApiError ? err.detail : 'Failed to load job.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Wrapped in its own inline async IIFE (rather than `void
  // reloadTimeline()` directly) — an effect calling a named function
  // reference that itself calls setState trips
  // `react-hooks/set-state-in-effect`'s static analysis even when nothing
  // runs synchronously before that function's first `await`; an inline
  // IIFE written directly in the effect body doesn't.
  useEffect(() => {
    void (async () => {
      await reloadTimeline();
    })();
  }, [reloadTimeline]);

  useEffect(() => {
    if (isTechnician) return;
    let cancelled = false;
    void (async () => {
      try {
        const users = await browserApiClient<User[]>('/users');
        if (!cancelled) setAllUsers(users);
      } catch {
        // Non-fatal — assign control and actor-name resolution just degrade to showing raw ids/blanks.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isTechnician]);

  const technicians = useMemo(() => allUsers.filter((u) => u.role === 'technician'), [allUsers]);
  const userNameById = useMemo(() => {
    const map: Record<string, string> = {};
    for (const u of allUsers) map[u.id] = u.full_name;
    if (isTechnician && user) map[user.id] = user.full_name;
    return map;
  }, [allUsers, isTechnician, user]);

  const startEditing = () => {
    if (!job) return;
    setEditValues({
      reported_issue: job.reported_issue,
      address_snapshot: job.address_snapshot,
      scheduled_at: toDatetimeLocalValue(job.scheduled_at),
    });
    setFieldErrors({});
    setFormError(null);
    setEditing(true);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (!editValues.reported_issue.trim()) errors.reported_issue = 'Reported issue is required.';
    if (!editValues.address_snapshot.trim()) errors.address_snapshot = 'Address is required.';
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setSavingEdit(true);
    setFieldErrors({});
    setFormError(null);
    try {
      const payload: JobUpdateRequest = {
        reported_issue: editValues.reported_issue,
        address_snapshot: editValues.address_snapshot,
        // Omitted (not `null`) when cleared — the backend's own partial-
        // update convention treats `null` the same as "not provided" for
        // this field (see job_service.update_job), so there's currently
        // no way to un-schedule a job via this endpoint at all; sending
        // `null` here would silently do nothing, so don't imply it works.
        ...(editValues.scheduled_at
          ? { scheduled_at: new Date(editValues.scheduled_at).toISOString() }
          : {}),
      };
      const updated = await browserApiClient<Job>(`/jobs/${id}`, {
        method: 'PATCH',
        body: payload,
      });
      setJob(updated);
      setEditing(false);
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') {
        const parsed = parseFieldErrors(err.detail);
        if (Object.keys(parsed).length > 0) {
          setFieldErrors(parsed);
        } else {
          setFormError(err.detail);
        }
      } else {
        setFormError(err instanceof ApiError ? err.detail : 'Failed to save job.');
      }
    } finally {
      setSavingEdit(false);
    }
  };

  const handleAssign = async () => {
    if (!selectedTechForAssign) return;
    setAssigning(true);
    setActionError(null);
    try {
      const updated = await browserApiClient<Job>(`/jobs/${id}/assign`, {
        method: 'POST',
        body: { technician_id: selectedTechForAssign } satisfies JobAssignRequest,
      });
      setJob(updated);
      setSelectedTechForAssign('');
      void reloadTimeline();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : 'Failed to assign technician.');
    } finally {
      setAssigning(false);
    }
  };

  const handleChangeStatus = async (newStatus: JobStatus) => {
    setChangingStatus(newStatus);
    setActionError(null);
    try {
      const updated = await browserApiClient<Job>(`/jobs/${id}/status`, {
        method: 'POST',
        body: { status: newStatus } satisfies JobStatusChangeRequest,
      });
      setJob(updated);
      void reloadTimeline();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : 'Failed to change status.');
    } finally {
      setChangingStatus(null);
    }
  };

  const handleCancel = async () => {
    setCancelling(true);
    setActionError(null);
    try {
      const updated = await browserApiClient<Job>(`/jobs/${id}`, { method: 'DELETE' });
      setJob(updated);
      setConfirmCancel(false);
      void reloadTimeline();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : 'Failed to cancel job.');
    } finally {
      setCancelling(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>;
  }

  if (notFound) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Job not found.</p>
        <Link href="/jobs" className="text-sm underline">
          Back to jobs
        </Link>
      </div>
    );
  }

  if (forbidden) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          This job isn&apos;t assigned to you, so you don&apos;t have access to it.
        </p>
        <Link href="/jobs" className="text-sm underline">
          Back to jobs
        </Link>
      </div>
    );
  }

  if (loadError || !job) {
    return <p className="text-sm text-destructive">{loadError ?? 'Failed to load job.'}</p>;
  }

  const nextStatuses = JOB_STATUS_FORWARD_TRANSITIONS[job.status];

  return (
    <div className="flex flex-col gap-4">
      <Link href="/jobs" className="text-sm text-zinc-500 hover:underline dark:text-zinc-400">
        ← Back to jobs
      </Link>

      <Card className="max-w-lg">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Job</CardTitle>
          <JobStatusBadge status={job.status} />
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {formError && <p className="text-sm text-destructive">{formError}</p>}

          {editing ? (
            <form onSubmit={(e) => void handleSaveEdit(e)} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <Label htmlFor="reported_issue">Reported issue</Label>
                <textarea
                  id="reported_issue"
                  value={editValues.reported_issue}
                  onChange={(e) => setEditValues((v) => ({ ...v, reported_issue: e.target.value }))}
                  rows={3}
                  aria-invalid={!!fieldErrors.reported_issue}
                  className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
                />
                {fieldErrors.reported_issue && (
                  <p className="text-xs text-destructive">{fieldErrors.reported_issue}</p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="address_snapshot">Address</Label>
                <Input
                  id="address_snapshot"
                  value={editValues.address_snapshot}
                  aria-invalid={!!fieldErrors.address_snapshot}
                  onChange={(e) =>
                    setEditValues((v) => ({ ...v, address_snapshot: e.target.value }))
                  }
                />
                {fieldErrors.address_snapshot && (
                  <p className="text-xs text-destructive">{fieldErrors.address_snapshot}</p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="scheduled_at">Scheduled at</Label>
                <Input
                  id="scheduled_at"
                  type="datetime-local"
                  value={editValues.scheduled_at}
                  onChange={(e) => setEditValues((v) => ({ ...v, scheduled_at: e.target.value }))}
                />
              </div>
              <div className="flex gap-2">
                <Button type="submit" disabled={savingEdit}>
                  {savingEdit ? 'Saving…' : 'Save'}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setEditing(false)}
                  disabled={savingEdit}
                >
                  Cancel
                </Button>
              </div>
            </form>
          ) : (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Reported issue</dt>
                <dd className="whitespace-pre-wrap">{job.reported_issue}</dd>
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Address</dt>
                <dd>{job.address_snapshot}</dd>
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Scheduled</dt>
                <dd>{job.scheduled_at ? new Date(job.scheduled_at).toLocaleString() : '—'}</dd>
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Technician</dt>
                <dd>
                  {job.assigned_technician_id
                    ? (userNameById[job.assigned_technician_id] ?? job.assigned_technician_id)
                    : 'Unassigned'}
                </dd>
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Warranty claim</dt>
                <dd>{job.is_warranty_claim ? 'Yes' : 'No'}</dd>
                {job.completed_at && (
                  <>
                    <dt className="font-medium text-zinc-500 dark:text-zinc-400">Completed</dt>
                    <dd>{new Date(job.completed_at).toLocaleString()}</dd>
                  </>
                )}
              </dl>
              {!isTechnician && (
                <div>
                  <Button variant="outline" onClick={startEditing}>
                    Edit
                  </Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {actionError && <p className="text-sm text-destructive">{actionError}</p>}

          {!isTechnician && job.status === 'new' && (
            <div className="flex flex-col gap-1">
              <Label htmlFor="assign-technician">Assign technician</Label>
              <div className="flex gap-2">
                <select
                  id="assign-technician"
                  value={selectedTechForAssign}
                  onChange={(e) => setSelectedTechForAssign(e.target.value)}
                  className="h-8 flex-1 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
                >
                  <option value="">Select a technician…</option>
                  {technicians.map((tech) => (
                    <option key={tech.id} value={tech.id}>
                      {tech.full_name}
                    </option>
                  ))}
                </select>
                <Button
                  onClick={() => void handleAssign()}
                  disabled={!selectedTechForAssign || assigning}
                >
                  {assigning ? 'Assigning…' : 'Assign'}
                </Button>
              </div>
            </div>
          )}

          {nextStatuses.length > 0 && (
            <div className="flex flex-col gap-1">
              <Label>Move to</Label>
              {/* Milestone F13: stacked, full-width, larger-height buttons
                  for a technician — this is the control they tap
                  repeatedly out in the field, one-handed; owner/dispatcher
                  keep the compact wrapped row since they're not the
                  target of the mobile-usability requirement here. */}
              <div className={isTechnician ? 'flex flex-col gap-2' : 'flex flex-wrap gap-2'}>
                {nextStatuses.map((status) => (
                  <Button
                    key={status}
                    variant="outline"
                    onClick={() => void handleChangeStatus(status)}
                    disabled={changingStatus !== null}
                    className={isTechnician ? 'h-12 w-full text-base' : undefined}
                  >
                    {changingStatus === status ? 'Saving…' : JOB_STATUS_LABELS[status]}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {!isTechnician && canCancelFromStatus(job.status) && (
            <div className="flex flex-col gap-1">
              <Label>Cancel</Label>
              {confirmCancel ? (
                <div className="flex gap-2">
                  <Button
                    variant="destructive"
                    onClick={() => void handleCancel()}
                    disabled={cancelling}
                  >
                    {cancelling ? 'Cancelling…' : 'Confirm cancel'}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => setConfirmCancel(false)}
                    disabled={cancelling}
                  >
                    Never mind
                  </Button>
                </div>
              ) : (
                <div>
                  <Button variant="destructive" onClick={() => setConfirmCancel(true)}>
                    Cancel job
                  </Button>
                </div>
              )}
            </div>
          )}

          {nextStatuses.length === 0 &&
            !canCancelFromStatus(job.status) &&
            job.status !== 'new' && (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                This job is in a final state — no further actions available.
              </p>
            )}
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Photos</CardTitle>
        </CardHeader>
        <CardContent>
          <JobPhotos jobId={id} onActivity={() => void reloadTimeline()} large={isTechnician} />
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Materials</CardTitle>
        </CardHeader>
        <CardContent>
          <JobMaterials jobId={id} onActivity={() => void reloadTimeline()} />
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Additional work</CardTitle>
        </CardHeader>
        <CardContent>
          <JobAdditionalWork jobId={id} onActivity={() => void reloadTimeline()} />
        </CardContent>
      </Card>

      {!isTechnician && (
        <Card className="max-w-lg">
          <CardHeader>
            <CardTitle>Payment</CardTitle>
          </CardHeader>
          <CardContent>
            <JobPayment jobId={id} />
          </CardContent>
        </Card>
      )}

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Documents</CardTitle>
        </CardHeader>
        <CardContent>
          <JobDocuments jobId={id} onActivity={() => void reloadTimeline()} />
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Activity timeline</CardTitle>
        </CardHeader>
        <CardContent>
          {timelineError ? (
            <p className="text-sm text-destructive">{timelineError}</p>
          ) : timeline === null ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
          ) : (
            <JobTimeline entries={timeline} actorNameById={userNameById} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
