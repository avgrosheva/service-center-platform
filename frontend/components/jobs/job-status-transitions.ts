import type { JobStatus } from '@/types/api';

/**
 * Mirrors app/services/job_service.py's `_ALLOWED_TRANSITIONS` exactly,
 * with two deliberate omissions:
 *
 * - `cancelled` is never listed as a forward option here, even though the
 *   backend allows it from every non-terminal status — this app surfaces
 *   that as the separate "Cancel job" action/button (DELETE
 *   /jobs/{id}, owner/dispatcher only), not a selectable entry in the
 *   generic status control everyone (including a technician on their own
 *   job) sees.
 * - `new -> assigned` is omitted — that transition only ever happens
 *   through the dedicated Assign control (POST /jobs/{id}/assign, which
 *   requires picking a technician), not a plain status change. This is
 *   why `new`'s own entry below is empty: its only backend-allowed
 *   forward move is handled by a different control entirely.
 *
 * There is no shared source of truth between the two codebases — keep
 * this in sync with `_ALLOWED_TRANSITIONS` by hand if that ever changes.
 */
export const JOB_STATUS_FORWARD_TRANSITIONS: Record<JobStatus, JobStatus[]> = {
  new: [],
  assigned: ['en_route'],
  en_route: ['in_progress'],
  in_progress: ['awaiting_parts', 'awaiting_approval'],
  awaiting_parts: ['in_progress'],
  awaiting_approval: ['completed'],
  completed: [],
  cancelled: [],
};

export function canCancelFromStatus(status: JobStatus): boolean {
  return status !== 'completed' && status !== 'cancelled';
}
