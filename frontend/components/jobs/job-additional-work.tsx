'use client';

/**
 * Milestone F11 — additional work: any role can flag it (a field
 * observation), only owner/dispatcher can approve/reject/bill (a dispatch
 * decision) — matches the backend's role split exactly (`_can_manage_job_items`
 * for flag/list vs `_can_approve_additional_work` for the status PATCH,
 * technician-gated at the router level, never reaching this component's
 * approve/reject/bill buttons at all when `isTechnician` is true).
 *
 * Flagging and approving are deliberately separate actions/buttons, never
 * a single "flag and approve" click — the backend has no combined
 * endpoint, and per the roadmap this is intentional: flagging is a field
 * observation, approving is a dispatch decision, and collapsing them
 * would let a technician's own flag silently self-approve.
 */

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useLocale } from '@/lib/i18n/context';
import type { TranslationKey } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { parseFieldErrors } from '@/lib/form-errors';
import { useAuth } from '@/lib/auth';
import type {
  AdditionalWorkItem,
  AdditionalWorkItemCreateRequest,
  AdditionalWorkItemStatusUpdateRequest,
  AdditionalWorkStatus,
} from '@/types/api';

const STATUS_STYLES: Record<AdditionalWorkStatus, string> = {
  pending: 'bg-status-pending/15 text-status-pending',
  approved: 'bg-blue-100 text-blue-700',
  rejected: 'bg-status-delayed/15 text-status-delayed',
  billed: 'bg-status-completed/15 text-status-completed',
};

const STATUS_KEYS: Record<AdditionalWorkStatus, TranslationKey> = {
  pending: 'additionalWorkStatus.pending',
  approved: 'additionalWorkStatus.approved',
  rejected: 'additionalWorkStatus.rejected',
  billed: 'additionalWorkStatus.billed',
};

// Mirrors app/services/job_items_service.py's
// `_ALLOWED_ADDITIONAL_WORK_TRANSITIONS` — kept in sync by hand, same
// convention as components/jobs/job-status-transitions.ts.
const NEXT_STATUSES: Record<AdditionalWorkStatus, AdditionalWorkStatus[]> = {
  pending: ['approved', 'rejected'],
  approved: ['billed'],
  rejected: [],
  billed: [],
};

export function JobAdditionalWork({
  jobId,
  onActivity,
}: {
  jobId: string;
  onActivity?: () => void;
}) {
  const { t } = useLocale();
  const { user } = useAuth();
  const isTechnician = user?.role === 'technician';

  const [items, setItems] = useState<AdditionalWorkItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [description, setDescription] = useState('');
  const [price, setPrice] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [flagging, setFlagging] = useState(false);

  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<AdditionalWorkItem[]>(`/jobs/${jobId}/additional-work`);
        if (!cancelled) setItems(data);
      } catch (err) {
        if (!cancelled)
          setLoadError(err instanceof ApiError ? err.detail : t('jobAdditionalWork.failedToLoad'));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const handleFlag = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (!description.trim()) errors.description = t('jobAdditionalWork.descriptionRequired');
    const priceNum = Number(price);
    if (!price.trim() || !Number.isFinite(priceNum) || priceNum <= 0) {
      errors.price = t('jobAdditionalWork.priceMustBePositive');
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFlagging(true);
    setFieldErrors({});
    setActionError(null);
    try {
      const payload: AdditionalWorkItemCreateRequest = { description, price };
      const created = await browserApiClient<AdditionalWorkItem>(`/jobs/${jobId}/additional-work`, {
        method: 'POST',
        body: payload,
      });
      setItems((prev) => (prev ? [...prev, created] : [created]));
      setDescription('');
      setPrice('');
      onActivity?.();
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') {
        setFieldErrors(parseFieldErrors(err.detail));
      } else {
        setActionError(err instanceof ApiError ? err.detail : t('jobAdditionalWork.failedToFlag'));
      }
    } finally {
      setFlagging(false);
    }
  };

  const handleUpdateStatus = async (itemId: string, status: AdditionalWorkStatus) => {
    setUpdatingId(itemId);
    setActionError(null);
    try {
      const updated = await browserApiClient<AdditionalWorkItem>(
        `/jobs/${jobId}/additional-work/${itemId}`,
        {
          method: 'PATCH',
          body: { status } as AdditionalWorkItemStatusUpdateRequest,
        },
      );
      setItems((prev) => prev?.map((item) => (item.id === itemId ? updated : item)) ?? prev);
      onActivity?.();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : t('jobAdditionalWork.failedToUpdate'));
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {loadError && <p className="text-sm text-destructive">{loadError}</p>}
      {actionError && <p className="text-sm text-destructive">{actionError}</p>}

      {items === null ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('jobAdditionalWork.noItemsYet')}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border px-3 py-2 text-sm"
            >
              <div className="flex flex-col gap-0.5">
                <span>{item.description}</span>
                <span className="text-xs text-muted-foreground">{item.price}</span>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[item.status]}`}
                >
                  {t(STATUS_KEYS[item.status])}
                </span>
                {!isTechnician &&
                  NEXT_STATUSES[item.status].map((next) => (
                    <Button
                      key={next}
                      size="sm"
                      variant="outline"
                      disabled={updatingId === item.id}
                      onClick={() => void handleUpdateStatus(item.id, next)}
                    >
                      {updatingId === item.id ? t('common.saving') : t(STATUS_KEYS[next])}
                    </Button>
                  ))}
              </div>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={(e) => void handleFlag(e)} className="flex flex-wrap items-start gap-2">
        <div className="flex flex-col gap-1">
          <Input
            placeholder={t('jobAdditionalWork.descriptionPlaceholder')}
            value={description}
            aria-invalid={!!fieldErrors.description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-48"
          />
          {fieldErrors.description && (
            <p className="text-xs text-destructive">{fieldErrors.description}</p>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <Input
            placeholder={t('jobAdditionalWork.pricePlaceholder')}
            value={price}
            aria-invalid={!!fieldErrors.price}
            onChange={(e) => setPrice(e.target.value)}
            className="w-24"
          />
          {fieldErrors.price && <p className="text-xs text-destructive">{fieldErrors.price}</p>}
        </div>
        <Button type="submit" disabled={flagging}>
          {flagging ? t('jobAdditionalWork.flagging') : t('jobAdditionalWork.flagAdditionalWork')}
        </Button>
      </form>
    </div>
  );
}
