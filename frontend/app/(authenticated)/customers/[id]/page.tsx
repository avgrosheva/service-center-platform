'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RequireRole } from '@/components/shell/require-role';
import { CustomerForm, validateCustomerForm } from '@/components/customers/customer-form';
import type { CustomerFormValues } from '@/components/customers/customer-form';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { parseFieldErrors } from '@/lib/form-errors';
import type { Customer, CustomerUpdateRequest, Equipment } from '@/types/api';

export default function CustomerDetailPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher']}>
      <CustomerDetailContent />
    </RequireRole>
  );
}

function CustomerDetailContent() {
  const { id } = useParams<{ id: string }>();

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [togglingActive, setTogglingActive] = useState(false);

  const [equipment, setEquipment] = useState<Equipment[] | null>(null);
  const [equipmentError, setEquipmentError] = useState<string | null>(null);

  // `loading`/`notFound`/`loadError` all start at their correct values, so
  // nothing is set synchronously before the first `await` here — see
  // dashboard/page.tsx's identical mount-effect shape for why.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<Customer>(`/customers/${id}`);
        if (!cancelled) setCustomer(data);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.kind === 'not_found') {
          setNotFound(true);
        } else {
          setLoadError(err instanceof ApiError ? err.detail : 'Failed to load customer.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Independent of the customer fetch above — if the customer itself
  // doesn't exist, this equipment fetch also 404s, but that's moot: the
  // early `notFound` return below means this card never renders either way.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<Equipment[]>(`/customers/${id}/equipment`);
        if (!cancelled) setEquipment(data);
      } catch (err) {
        if (!cancelled) {
          setEquipmentError(err instanceof ApiError ? err.detail : 'Failed to load equipment.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleSave = async (values: CustomerFormValues) => {
    const clientErrors = validateCustomerForm(values);
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      return;
    }

    setSubmitting(true);
    setFieldErrors({});
    setFormError(null);
    try {
      const payload: CustomerUpdateRequest = {
        full_name: values.full_name,
        phone: values.phone,
        notes: values.notes.trim() || null,
      };
      const updated = await browserApiClient<Customer>(`/customers/${id}`, {
        method: 'PATCH',
        body: payload,
      });
      setCustomer(updated);
      setEditing(false);
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') {
        setFieldErrors(parseFieldErrors(err.detail));
      } else {
        setFormError(err instanceof ApiError ? err.detail : 'Failed to save customer.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const toggleActive = async () => {
    if (!customer) return;
    setTogglingActive(true);
    try {
      const updated = customer.is_active
        ? await browserApiClient<Customer>(`/customers/${id}`, { method: 'DELETE' })
        : await browserApiClient<Customer>(`/customers/${id}`, {
            method: 'PATCH',
            body: { is_active: true } satisfies CustomerUpdateRequest,
          });
      setCustomer(updated);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.detail : 'Failed to update customer status.');
    } finally {
      setTogglingActive(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>;
  }

  if (notFound) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Customer not found.</p>
        <Link href="/customers" className="text-sm underline">
          Back to customers
        </Link>
      </div>
    );
  }

  if (loadError || !customer) {
    return <p className="text-sm text-destructive">{loadError ?? 'Failed to load customer.'}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <Link href="/customers" className="text-sm text-zinc-500 hover:underline dark:text-zinc-400">
        ← Back to customers
      </Link>

      <Card className="max-w-md">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{customer.full_name}</CardTitle>
          {!customer.is_active && (
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
              Archived
            </span>
          )}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {formError && <p className="text-sm text-destructive">{formError}</p>}

          {editing ? (
            <CustomerForm
              initialValues={{
                full_name: customer.full_name,
                phone: customer.phone,
                notes: customer.notes ?? '',
              }}
              fieldErrors={fieldErrors}
              submitting={submitting}
              submitLabel="Save"
              onSubmit={(values) => void handleSave(values)}
              onCancel={() => {
                setEditing(false);
                setFieldErrors({});
                setFormError(null);
              }}
            />
          ) : (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Phone</dt>
                <dd>{customer.phone}</dd>
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Notes</dt>
                <dd className="whitespace-pre-wrap">{customer.notes || '—'}</dd>
              </dl>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setEditing(true)}>
                  Edit
                </Button>
                <Button
                  variant={customer.is_active ? 'destructive' : 'outline'}
                  onClick={() => void toggleActive()}
                  disabled={togglingActive}
                >
                  {togglingActive ? 'Working…' : customer.is_active ? 'Archive' : 'Reactivate'}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card className="max-w-md">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Equipment</CardTitle>
          <Link
            href={`/customers/${id}/equipment/new`}
            className="text-sm text-zinc-500 hover:underline dark:text-zinc-400"
          >
            Add equipment
          </Link>
        </CardHeader>
        <CardContent>
          {equipmentError ? (
            <p className="text-sm text-destructive">{equipmentError}</p>
          ) : equipment === null ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
          ) : equipment.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">No equipment yet.</p>
          ) : (
            <ul className="flex flex-col gap-1 text-sm">
              {equipment.map((item) => (
                <li key={item.id}>
                  <Link href={`/equipment/${item.id}`} className="hover:underline">
                    {item.type}
                    {item.brand || item.model
                      ? ` — ${[item.brand, item.model].filter(Boolean).join(' ')}`
                      : ''}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>Job history</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Job history arrives in Milestone F7.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
