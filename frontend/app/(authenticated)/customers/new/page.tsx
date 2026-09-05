'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RequireRole } from '@/components/shell/require-role';
import { CustomerForm, validateCustomerForm } from '@/components/customers/customer-form';
import type { CustomerFormValues } from '@/components/customers/customer-form';
import { useLocale } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { parseFieldErrors } from '@/lib/form-errors';
import type { Customer, CustomerCreateRequest } from '@/types/api';

export default function NewCustomerPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher']}>
      <NewCustomerContent />
    </RequireRole>
  );
}

function NewCustomerContent() {
  const { t } = useLocale();
  const router = useRouter();
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (values: CustomerFormValues) => {
    const clientErrors = validateCustomerForm(values, t);
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      return;
    }

    setSubmitting(true);
    setFieldErrors({});
    setFormError(null);
    try {
      const payload: CustomerCreateRequest = {
        full_name: values.full_name,
        phone: values.phone,
        notes: values.notes.trim() || null,
      };
      const created = await browserApiClient<Customer>('/customers', {
        method: 'POST',
        body: payload,
      });
      router.push(`/customers/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') {
        setFieldErrors(parseFieldErrors(err.detail));
      } else {
        setFormError(err instanceof ApiError ? err.detail : t('customerDetail.failedToSave'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>{t('customers.newCustomer')}</CardTitle>
      </CardHeader>
      <CardContent>
        {formError && <p className="mb-3 text-sm text-destructive">{formError}</p>}
        <CustomerForm
          initialValues={{ full_name: '', phone: '', notes: '' }}
          fieldErrors={fieldErrors}
          submitting={submitting}
          submitLabel={t('customerForm.createCustomer')}
          onSubmit={(values) => void handleSubmit(values)}
          onCancel={() => router.push('/customers')}
        />
      </CardContent>
    </Card>
  );
}
