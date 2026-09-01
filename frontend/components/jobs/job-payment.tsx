'use client';

/**
 * Milestone F11 — payment section. Only ever rendered for owner/dispatcher
 * (see app/(authenticated)/jobs/[id]/page.tsx, which doesn't mount this
 * component at all for a technician viewer) — the backend blocks
 * technicians from both GET and PUT entirely, unlike additional work's
 * partial (flag-only) access.
 *
 * One PUT handles both "no payment yet" and "update the existing one" —
 * a genuine upsert per the backend's own PaymentUpsert semantics, so this
 * form never needs separate create/edit modes. A GET 404 means "no
 * payment set for this job yet", not an error — the job's own existence
 * is already guaranteed by the time this section renders.
 */

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ApiError, browserApiClient } from '@/lib/api-client';
import type { Payment, PaymentMethod, PaymentStatus, PaymentUpsertRequest } from '@/types/api';

const SELECT_CLASS =
  'h-8 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30';

export function JobPayment({ jobId }: { jobId: string }) {
  const [payment, setPayment] = useState<Payment | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState<PaymentMethod>('cash');
  const [status, setStatus] = useState<PaymentStatus>('unpaid');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<Payment>(`/jobs/${jobId}/payment`);
        if (!cancelled) {
          setPayment(data);
          setAmount(data.amount);
          setMethod(data.method);
          setStatus(data.status);
        }
      } catch (err) {
        if (cancelled) return;
        if (!(err instanceof ApiError && err.kind === 'not_found')) {
          setLoadError(err instanceof ApiError ? err.detail : 'Failed to load payment.');
        }
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const amountNum = Number(amount);
    if (!amount.trim() || !Number.isFinite(amountNum) || amountNum <= 0) {
      setFieldError('Amount must be greater than 0.');
      return;
    }

    setSaving(true);
    setFieldError(null);
    try {
      const payload: PaymentUpsertRequest = { amount, method, status };
      const updated = await browserApiClient<Payment>(`/jobs/${jobId}/payment`, {
        method: 'PUT',
        body: payload,
      });
      setPayment(updated);
      setAmount(updated.amount);
      setStatus(updated.status);
    } catch (err) {
      setFieldError(err instanceof ApiError ? err.detail : 'Failed to save payment.');
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>;
  }

  if (loadError) {
    return <p className="text-sm text-destructive">{loadError}</p>;
  }

  return (
    <form onSubmit={(e) => void handleSave(e)} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Label htmlFor="payment-amount">Amount</Label>
        <Input
          id="payment-amount"
          value={amount}
          aria-invalid={!!fieldError}
          onChange={(e) => setAmount(e.target.value)}
          className="w-32"
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="payment-method">Method</Label>
        <select
          id="payment-method"
          value={method}
          onChange={(e) => setMethod(e.target.value as PaymentMethod)}
          className={SELECT_CLASS}
        >
          <option value="cash">Cash</option>
          <option value="card">Card</option>
          <option value="bank_transfer">Bank transfer</option>
          <option value="other">Other</option>
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="payment-status">Status</Label>
        <select
          id="payment-status"
          value={status}
          onChange={(e) => setStatus(e.target.value as PaymentStatus)}
          className={SELECT_CLASS}
        >
          <option value="unpaid">Unpaid</option>
          <option value="paid">Paid</option>
        </select>
      </div>
      {payment?.paid_at && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Paid at: {new Date(payment.paid_at).toLocaleString()}
        </p>
      )}
      {fieldError && <p className="text-sm text-destructive">{fieldError}</p>}
      <div>
        <Button type="submit" disabled={saving}>
          {saving ? 'Saving…' : payment ? 'Update payment' : 'Save payment'}
        </Button>
      </div>
    </form>
  );
}
