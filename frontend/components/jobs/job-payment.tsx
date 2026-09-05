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
import { useLocale } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import type { Payment, PaymentMethod, PaymentStatus, PaymentUpsertRequest } from '@/types/api';

const SELECT_CLASS =
  'h-8 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30';

export function JobPayment({ jobId }: { jobId: string }) {
  const { t } = useLocale();
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
          setLoadError(err instanceof ApiError ? err.detail : t('jobPayment.failedToLoad'));
        }
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const amountNum = Number(amount);
    if (!amount.trim() || !Number.isFinite(amountNum) || amountNum <= 0) {
      setFieldError(t('jobPayment.amountMustBePositive'));
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
      setFieldError(err instanceof ApiError ? err.detail : t('jobPayment.failedToSave'));
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) {
    return <p className="text-sm text-muted-foreground">{t('common.loading')}</p>;
  }

  if (loadError) {
    return <p className="text-sm text-destructive">{loadError}</p>;
  }

  return (
    <form onSubmit={(e) => void handleSave(e)} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Label htmlFor="payment-amount">{t('jobPayment.amount')}</Label>
        <Input
          id="payment-amount"
          value={amount}
          aria-invalid={!!fieldError}
          onChange={(e) => setAmount(e.target.value)}
          className="w-32"
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="payment-method">{t('jobPayment.method')}</Label>
        <select
          id="payment-method"
          value={method}
          onChange={(e) => setMethod(e.target.value as PaymentMethod)}
          className={SELECT_CLASS}
        >
          <option value="cash">{t('jobPayment.cash')}</option>
          <option value="card">{t('jobPayment.card')}</option>
          <option value="bank_transfer">{t('jobPayment.bankTransfer')}</option>
          <option value="other">{t('jobPayment.other')}</option>
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="payment-status">{t('jobPayment.status')}</Label>
        <select
          id="payment-status"
          value={status}
          onChange={(e) => setStatus(e.target.value as PaymentStatus)}
          className={SELECT_CLASS}
        >
          <option value="unpaid">{t('jobPayment.unpaid')}</option>
          <option value="paid">{t('jobPayment.paid')}</option>
        </select>
      </div>
      {payment?.paid_at && (
        <p className="text-xs text-muted-foreground">
          {t('jobPayment.paidAt', { date: new Date(payment.paid_at).toLocaleString() })}
        </p>
      )}
      {fieldError && <p className="text-sm text-destructive">{fieldError}</p>}
      <div>
        <Button type="submit" disabled={saving}>
          {saving
            ? t('common.saving')
            : payment
              ? t('jobPayment.updatePayment')
              : t('jobPayment.savePayment')}
        </Button>
      </div>
    </form>
  );
}
