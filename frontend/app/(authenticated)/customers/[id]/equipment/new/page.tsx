'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useState } from 'react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RequireRole } from '@/components/shell/require-role';
import { EquipmentForm, validateEquipmentForm } from '@/components/equipment/equipment-form';
import type { EquipmentFormValues } from '@/components/equipment/equipment-form';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { parseFieldErrors } from '@/lib/form-errors';
import type { Equipment, EquipmentCreateRequest } from '@/types/api';

const EMPTY_VALUES: EquipmentFormValues = {
  type: '',
  brand: '',
  model: '',
  serial_number: '',
  installation_address: '',
  install_date: '',
  warranty_until: '',
};

export default function NewEquipmentPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher']}>
      <NewEquipmentContent />
    </RequireRole>
  );
}

function NewEquipmentContent() {
  const { id: customerId } = useParams<{ id: string }>();
  const router = useRouter();
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (values: EquipmentFormValues) => {
    const clientErrors = validateEquipmentForm(values);
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      return;
    }

    setSubmitting(true);
    setFieldErrors({});
    setFormError(null);
    try {
      const payload: EquipmentCreateRequest = {
        type: values.type,
        brand: values.brand.trim() || null,
        model: values.model.trim() || null,
        serial_number: values.serial_number.trim() || null,
        installation_address: values.installation_address,
        install_date: values.install_date || null,
        warranty_until: values.warranty_until || null,
      };
      const created = await browserApiClient<Equipment>(`/customers/${customerId}/equipment`, {
        method: 'POST',
        body: payload,
      });
      router.push(`/equipment/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') {
        setFieldErrors(parseFieldErrors(err.detail));
      } else {
        setFormError(err instanceof ApiError ? err.detail : 'Failed to create equipment.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Link
        href={`/customers/${customerId}`}
        className="text-sm text-zinc-500 hover:underline dark:text-zinc-400"
      >
        ← Back to customer
      </Link>
      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>New equipment</CardTitle>
        </CardHeader>
        <CardContent>
          {formError && <p className="mb-3 text-sm text-destructive">{formError}</p>}
          <EquipmentForm
            initialValues={EMPTY_VALUES}
            fieldErrors={fieldErrors}
            submitting={submitting}
            submitLabel="Create equipment"
            onSubmit={(values) => void handleSubmit(values)}
            onCancel={() => router.push(`/customers/${customerId}`)}
          />
        </CardContent>
      </Card>
    </div>
  );
}
