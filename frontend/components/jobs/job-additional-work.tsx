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
  pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  approved: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  rejected: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  billed: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
};

const STATUS_LABELS: Record<AdditionalWorkStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  billed: 'Billed',
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
          setLoadError(err instanceof ApiError ? err.detail : 'Failed to load additional work.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const handleFlag = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (!description.trim()) errors.description = 'Description is required.';
    const priceNum = Number(price);
    if (!price.trim() || !Number.isFinite(priceNum) || priceNum <= 0) {
      errors.price = 'Price must be greater than 0.';
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
        setActionError(err instanceof ApiError ? err.detail : 'Failed to flag additional work.');
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
      setActionError(err instanceof ApiError ? err.detail : 'Failed to update additional work.');
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {loadError && <p className="text-sm text-destructive">{loadError}</p>}
      {actionError && <p className="text-sm text-destructive">{actionError}</p>}

      {items === null ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No additional work flagged yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800"
            >
              <div className="flex flex-col gap-0.5">
                <span>{item.description}</span>
                <span className="text-xs text-zinc-500 dark:text-zinc-400">{item.price}</span>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[item.status]}`}
                >
                  {STATUS_LABELS[item.status]}
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
                      {updatingId === item.id ? 'Saving…' : STATUS_LABELS[next]}
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
            placeholder="Description"
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
            placeholder="Price"
            value={price}
            aria-invalid={!!fieldErrors.price}
            onChange={(e) => setPrice(e.target.value)}
            className="w-24"
          />
          {fieldErrors.price && <p className="text-xs text-destructive">{fieldErrors.price}</p>}
        </div>
        <Button type="submit" disabled={flagging}>
          {flagging ? 'Flagging…' : 'Flag additional work'}
        </Button>
      </form>
    </div>
  );
}
