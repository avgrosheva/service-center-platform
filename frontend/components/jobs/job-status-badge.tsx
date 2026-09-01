import type { JobStatus } from '@/types/api';

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  new: 'New',
  assigned: 'Assigned',
  en_route: 'En Route',
  in_progress: 'In Progress',
  awaiting_parts: 'Awaiting Parts',
  awaiting_approval: 'Awaiting Approval',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

// One distinct color per status (light/dark pair), all 8 covered per the
// F7 testing checklist. Roughly: cool/neutral tones early in the job's
// life, warm tones while it's blocked, green for the success terminal
// state, muted red for the non-success terminal state.
const JOB_STATUS_STYLES: Record<JobStatus, string> = {
  new: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
  assigned: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  en_route: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300',
  in_progress: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  awaiting_parts: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300',
  awaiting_approval: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  completed: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  cancelled: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${JOB_STATUS_STYLES[status]}`}
    >
      {JOB_STATUS_LABELS[status]}
    </span>
  );
}
