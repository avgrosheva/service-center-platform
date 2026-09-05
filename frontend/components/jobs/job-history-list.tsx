'use client';

/**
 * A customer's or a piece of equipment's job history — shared by
 * customers/[id]/page.tsx and equipment/[id]/page.tsx, which each pass
 * exactly one of `customerId`/`equipmentId` (whichever one they scope by)
 * straight through to GET /jobs' own filter of the same name. Only ever
 * rendered on those two owner/dispatcher-only pages, so there's no
 * technician-scoping concern here beyond what /jobs already enforces.
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { JobStatusBadge } from '@/components/jobs/job-status-badge';
import { useLocale } from '@/lib/i18n/context';
import type { TranslationKey } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import type { Job } from '@/types/api';

export function JobHistoryList({
  customerId,
  equipmentId,
  emptyMessageKey,
  errorMessageKey,
}: {
  customerId?: string;
  equipmentId?: string;
  emptyMessageKey: TranslationKey;
  errorMessageKey: TranslationKey;
}) {
  const { t } = useLocale();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<Job[]>('/jobs', {
          params: { customer_id: customerId, equipment_id: equipmentId },
        });
        if (!cancelled) setJobs(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.detail : t(errorMessageKey));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId, equipmentId]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (jobs === null) return <p className="text-sm text-muted-foreground">{t('common.loading')}</p>;
  if (jobs.length === 0)
    return <p className="text-sm text-muted-foreground">{t(emptyMessageKey)}</p>;

  return (
    <ul className="flex flex-col gap-1 text-sm">
      {jobs.map((job) => (
        <li key={job.id}>
          <Link
            href={`/jobs/${job.id}`}
            className="flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 hover:bg-muted"
          >
            <span className="flex min-w-0 items-center gap-2">
              <JobStatusBadge status={job.status} />
              <span className="truncate">{job.reported_issue}</span>
            </span>
            <span className="shrink-0 text-xs text-muted-foreground">
              {new Date(job.scheduled_at ?? job.created_at).toLocaleDateString()}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
