'use client';

import { useLocale } from '@/lib/i18n/context';
import type { JobStatus } from '@/types/api';

// One distinct color per status, all 8 covered per the F7 testing
// checklist. Roughly: neutral/cool tones early in the job's life, warm
// tones while it's blocked, the studio accent for the in-progress/final
// success state, muted red for the non-success terminal state. No
// dark-mode pair — the product has no dark-mode toggle, so a `dark:`
// class here would be dead code.
const JOB_STATUS_STYLES: Record<JobStatus, string> = {
  new: 'bg-muted text-muted-foreground',
  assigned: 'bg-blue-100 text-blue-700',
  en_route: 'bg-indigo-100 text-indigo-700',
  in_progress: 'bg-primary/15 text-primary',
  awaiting_parts: 'bg-orange-100 text-orange-800',
  awaiting_approval: 'bg-purple-100 text-purple-700',
  completed: 'bg-status-completed/15 text-status-completed',
  cancelled: 'bg-status-delayed/15 text-status-delayed',
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const { t } = useLocale();
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${JOB_STATUS_STYLES[status]}`}
    >
      {t(`jobStatus.${status}`)}
    </span>
  );
}
