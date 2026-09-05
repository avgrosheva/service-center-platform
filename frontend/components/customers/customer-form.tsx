'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useLocale } from '@/lib/i18n/context';
import type { TranslationKey } from '@/lib/i18n/context';

export type CustomerFormValues = {
  full_name: string;
  phone: string;
  notes: string;
};

// Mirrors app/schemas/customer.py's `_PHONE_MIN_DIGITS` — client-side
// validation exists only for immediate feedback; the backend remains the
// real enforcement (and its own message is what actually surfaces if this
// ever drifts out of sync with it).
const PHONE_MIN_DIGITS = 7;

export function validateCustomerForm(
  values: CustomerFormValues,
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (values.full_name.trim().length === 0) {
    errors.full_name = t('customerForm.fullNameRequired');
  }
  const digitCount = values.phone.replace(/\D/g, '').length;
  if (digitCount < PHONE_MIN_DIGITS) {
    errors.phone = t('customerForm.phoneMinDigits', { count: PHONE_MIN_DIGITS });
  }
  return errors;
}

export function CustomerForm({
  initialValues,
  fieldErrors,
  submitting,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initialValues: CustomerFormValues;
  fieldErrors: Record<string, string>;
  submitting: boolean;
  submitLabel: string;
  onSubmit: (values: CustomerFormValues) => void;
  onCancel?: () => void;
}) {
  const { t } = useLocale();
  const [values, setValues] = useState(initialValues);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(values);
      }}
      className="flex flex-col gap-4"
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor="full_name">{t('customerForm.fullName')}</Label>
        <Input
          id="full_name"
          value={values.full_name}
          aria-invalid={!!fieldErrors.full_name}
          onChange={(e) => setValues((v) => ({ ...v, full_name: e.target.value }))}
        />
        {fieldErrors.full_name && (
          <p className="text-xs text-destructive">{fieldErrors.full_name}</p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <Label htmlFor="phone">{t('customerForm.phone')}</Label>
        <Input
          id="phone"
          value={values.phone}
          aria-invalid={!!fieldErrors.phone}
          onChange={(e) => setValues((v) => ({ ...v, phone: e.target.value }))}
        />
        {fieldErrors.phone && <p className="text-xs text-destructive">{fieldErrors.phone}</p>}
      </div>

      <div className="flex flex-col gap-1">
        <Label htmlFor="notes">{t('customerForm.notes')}</Label>
        <textarea
          id="notes"
          value={values.notes}
          onChange={(e) => setValues((v) => ({ ...v, notes: e.target.value }))}
          rows={3}
          className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        />
        {fieldErrors.notes && <p className="text-xs text-destructive">{fieldErrors.notes}</p>}
      </div>

      <div className="flex gap-2">
        <Button type="submit" disabled={submitting}>
          {submitting ? t('common.saving') : submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>
            {t('common.cancel')}
          </Button>
        )}
      </div>
    </form>
  );
}
