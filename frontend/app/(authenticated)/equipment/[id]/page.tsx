'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RequireRole } from '@/components/shell/require-role';
import { EquipmentForm, validateEquipmentForm } from '@/components/equipment/equipment-form';
import type { EquipmentFormValues } from '@/components/equipment/equipment-form';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { parseFieldErrors } from '@/lib/form-errors';
import type { Equipment, EquipmentUpdateRequest } from '@/types/api';

export default function EquipmentDetailPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher']}>
      <EquipmentDetailContent />
    </RequireRole>
  );
}

function EquipmentDetailContent() {
  const { id } = useParams<{ id: string }>();

  const [equipment, setEquipment] = useState<Equipment | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // See app/(authenticated)/customers/[id]/page.tsx's identical mount-effect
  // shape — no synchronous setState before the first `await` here either.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<Equipment>(`/equipment/${id}`);
        if (!cancelled) setEquipment(data);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.kind === 'not_found') {
          setNotFound(true);
        } else {
          setLoadError(err instanceof ApiError ? err.detail : 'Failed to load equipment.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleSave = async (values: EquipmentFormValues) => {
    const clientErrors = validateEquipmentForm(values);
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      return;
    }

    setSubmitting(true);
    setFieldErrors({});
    setFormError(null);
    try {
      const payload: EquipmentUpdateRequest = {
        type: values.type,
        brand: values.brand.trim() || null,
        model: values.model.trim() || null,
        serial_number: values.serial_number.trim() || null,
        installation_address: values.installation_address,
        install_date: values.install_date || null,
        warranty_until: values.warranty_until || null,
      };
      const updated = await browserApiClient<Equipment>(`/equipment/${id}`, {
        method: 'PATCH',
        body: payload,
      });
      setEquipment(updated);
      setEditing(false);
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') {
        setFieldErrors(parseFieldErrors(err.detail));
      } else {
        setFormError(err instanceof ApiError ? err.detail : 'Failed to save equipment.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>;
  }

  if (notFound) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Equipment not found.</p>
        <Link href="/customers" className="text-sm underline">
          Back to customers
        </Link>
      </div>
    );
  }

  if (loadError || !equipment) {
    return <p className="text-sm text-destructive">{loadError ?? 'Failed to load equipment.'}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <Link
        href={`/customers/${equipment.customer_id}`}
        className="text-sm text-zinc-500 hover:underline dark:text-zinc-400"
      >
        ← Back to customer
      </Link>

      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>
            {equipment.type}
            {equipment.brand || equipment.model
              ? ` — ${[equipment.brand, equipment.model].filter(Boolean).join(' ')}`
              : ''}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {formError && <p className="text-sm text-destructive">{formError}</p>}

          {editing ? (
            <EquipmentForm
              initialValues={{
                type: equipment.type,
                brand: equipment.brand ?? '',
                model: equipment.model ?? '',
                serial_number: equipment.serial_number ?? '',
                installation_address: equipment.installation_address,
                install_date: equipment.install_date ?? '',
                warranty_until: equipment.warranty_until ?? '',
              }}
              fieldErrors={fieldErrors}
              submitting={submitting}
              submitLabel="Save"
              showAddressChangeNote
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
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Serial number</dt>
                <dd>{equipment.serial_number || '—'}</dd>
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Address</dt>
                <dd>{equipment.installation_address}</dd>
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Installed</dt>
                <dd>{equipment.install_date || '—'}</dd>
                <dt className="font-medium text-zinc-500 dark:text-zinc-400">Warranty until</dt>
                <dd>{equipment.warranty_until || '—'}</dd>
              </dl>
              <div>
                <Button variant="outline" onClick={() => setEditing(true)}>
                  Edit
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>Repair history</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Repair history arrives in Milestone F7.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
