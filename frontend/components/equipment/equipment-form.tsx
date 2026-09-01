'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export type EquipmentFormValues = {
  type: string;
  brand: string;
  model: string;
  serial_number: string;
  installation_address: string;
  install_date: string;
  warranty_until: string;
};

export function validateEquipmentForm(values: EquipmentFormValues): Record<string, string> {
  const errors: Record<string, string> = {};
  if (values.type.trim().length === 0) {
    errors.type = 'Type is required.';
  }
  if (values.installation_address.trim().length === 0) {
    errors.installation_address = 'Installation address is required.';
  }
  return errors;
}

export function EquipmentForm({
  initialValues,
  fieldErrors,
  submitting,
  submitLabel,
  showAddressChangeNote,
  onSubmit,
  onCancel,
}: {
  initialValues: EquipmentFormValues;
  fieldErrors: Record<string, string>;
  submitting: boolean;
  submitLabel: string;
  /** True only when editing existing equipment — a new record has no jobs yet, so the caveat doesn't apply. */
  showAddressChangeNote?: boolean;
  onSubmit: (values: EquipmentFormValues) => void;
  onCancel?: () => void;
}) {
  const [values, setValues] = useState(initialValues);

  const field = (key: keyof EquipmentFormValues, label: string, type: string = 'text') => (
    <div className="flex flex-col gap-1">
      <Label htmlFor={key}>{label}</Label>
      <Input
        id={key}
        type={type}
        value={values[key]}
        aria-invalid={!!fieldErrors[key]}
        onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
      />
      {fieldErrors[key] && <p className="text-xs text-destructive">{fieldErrors[key]}</p>}
    </div>
  );

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(values);
      }}
      className="flex flex-col gap-4"
    >
      {field('type', 'Type')}
      {field('brand', 'Brand')}
      {field('model', 'Model')}
      {field('serial_number', 'Serial number')}
      {field('installation_address', 'Installation address')}
      {showAddressChangeNote && (
        <p className="-mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          Changing this won&apos;t update the address already recorded on this equipment&apos;s past
          jobs.
        </p>
      )}
      {field('install_date', 'Install date', 'date')}
      {field('warranty_until', 'Warranty until', 'date')}

      <div className="flex gap-2">
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Saving…' : submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
