'use client';

/**
 * Milestone F8 — job creation form. No inline customer-create (roadmap
 * calls it "a nice-to-have, not required for MVP") — search/select an
 * existing customer only; F5 owns customer creation.
 *
 * No `scheduled_at` control here — the roadmap's own F8 component list
 * doesn't include one (only customer picker, equipment picker, and the
 * warranty override), so scheduling is left to whichever later milestone
 * actually owns it (F9's job detail, or F14's calendar) rather than
 * guessed at here.
 *
 * Address handling mirrors the backend's own `JobCreate` model validator
 * exactly: equipment selected -> address_snapshot is always derived
 * server-side from that equipment's current installation_address (this
 * form doesn't send `address` at all in that case, so there's no chance
 * of the two disagreeing); no equipment selected -> a manual address is
 * required, validated client-side for immediate feedback with the same
 * rule the backend enforces.
 *
 * On success, this navigates to `/jobs/{id}` per the roadmap's literal
 * spec ("Successful creation navigates to the new job's detail page
 * (F9)") — that page doesn't exist until Milestone F9, so this currently
 * 404s, the same accepted interim state as every other forward reference
 * in this app (nav-config.ts's Jobs/Settings links, F7's own list-row
 * links here). Revisit nothing here once F9 lands; the link is already
 * correct.
 */

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RequireRole } from '@/components/shell/require-role';
import { useLocale } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { parseFieldErrors } from '@/lib/form-errors';
import type { Customer, Equipment, Job, JobCreateRequest } from '@/types/api';

const SELECT_CLASS =
  'h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30';

type WarrantyOverride = 'auto' | 'yes' | 'no';

export default function NewJobPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher']}>
      <NewJobContent />
    </RequireRole>
  );
}

function NewJobContent() {
  const { t } = useLocale();
  const router = useRouter();

  const [customerSearch, setCustomerSearch] = useState('');
  const [customerResults, setCustomerResults] = useState<Customer[]>([]);
  const [searchingCustomers, setSearchingCustomers] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);

  const [equipmentList, setEquipmentList] = useState<Equipment[] | null>(null);
  const [selectedEquipmentId, setSelectedEquipmentId] = useState('');
  const [manualAddress, setManualAddress] = useState('');

  const [reportedIssue, setReportedIssue] = useState('');
  const [warrantyOverride, setWarrantyOverride] = useState<WarrantyOverride>('auto');

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!customerSearch.trim() || selectedCustomer) return;
    const handle = setTimeout(() => {
      void (async () => {
        setSearchingCustomers(true);
        try {
          const data = await browserApiClient<Customer[]>('/customers', {
            params: { search: customerSearch },
          });
          setCustomerResults(data);
        } catch {
          setCustomerResults([]);
        } finally {
          setSearchingCustomers(false);
        }
      })();
    }, 350);
    return () => clearTimeout(handle);
  }, [customerSearch, selectedCustomer]);

  useEffect(() => {
    if (!selectedCustomer) return;
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<Equipment[]>(
          `/customers/${selectedCustomer.id}/equipment`,
        );
        if (!cancelled) setEquipmentList(data);
      } catch {
        if (!cancelled) setEquipmentList([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedCustomer]);

  const selectedEquipment = equipmentList?.find((e) => e.id === selectedEquipmentId) ?? null;

  const clearFieldError = (name: string) => {
    setFieldErrors((prev) => {
      if (!(name in prev)) return prev;
      const next = { ...prev };
      delete next[name];
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const errors: Record<string, string> = {};
    if (!selectedCustomer) errors.customer = t('jobNew.selectCustomer');
    if (!reportedIssue.trim()) errors.reported_issue = t('jobNew.reportedIssueRequired');
    if (!selectedEquipmentId && !manualAddress.trim()) {
      errors.address = t('jobNew.addressRequiredNoEquipment');
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setSubmitting(true);
    setFieldErrors({});
    setFormError(null);
    try {
      const payload: JobCreateRequest = {
        customer_id: selectedCustomer!.id,
        equipment_id: selectedEquipmentId || undefined,
        reported_issue: reportedIssue,
        address: selectedEquipmentId ? undefined : manualAddress,
        is_warranty_claim: warrantyOverride === 'auto' ? null : warrantyOverride === 'yes',
      };
      const created = await browserApiClient<Job>('/jobs', { method: 'POST', body: payload });
      router.push(`/jobs/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') {
        const parsed = parseFieldErrors(err.detail);
        if (Object.keys(parsed).length > 0) {
          setFieldErrors(parsed);
        } else {
          // A model-level validator error (e.g. the backend's own "address
          // is required when no equipment_id is provided") has no field
          // name to attach to — parseFieldErrors legitimately returns
          // nothing to key inline errors off of, so it belongs in the
          // general banner instead of being silently dropped.
          setFormError(err.detail);
        }
      } else {
        setFormError(err instanceof ApiError ? err.detail : t('jobNew.failedToCreate'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>{t('jobNew.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        {formError && <p className="mb-3 text-sm text-destructive">{formError}</p>}
        <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <Label>{t('jobNew.customer')}</Label>
            {selectedCustomer ? (
              <div className="flex items-center justify-between rounded-lg border border-input px-2.5 py-1.5 text-sm">
                <span>
                  {selectedCustomer.full_name} — {selectedCustomer.phone}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setSelectedCustomer(null);
                    setEquipmentList(null);
                    setSelectedEquipmentId('');
                  }}
                >
                  {t('jobNew.change')}
                </Button>
              </div>
            ) : (
              <div className="relative">
                <Input
                  placeholder={t('jobNew.searchPlaceholder')}
                  value={customerSearch}
                  aria-invalid={!!fieldErrors.customer}
                  onChange={(e) => {
                    setCustomerSearch(e.target.value);
                    if (!e.target.value.trim()) setCustomerResults([]);
                    clearFieldError('customer');
                  }}
                />
                {customerSearch.trim() && (
                  <div className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-border">
                    {searchingCustomers ? (
                      <p className="px-2.5 py-1.5 text-sm text-muted-foreground">
                        {t('common.searching')}
                      </p>
                    ) : customerResults.length === 0 ? (
                      <p className="px-2.5 py-1.5 text-sm text-muted-foreground">
                        {t('common.noMatches')}
                      </p>
                    ) : (
                      customerResults.map((customer) => (
                        <button
                          key={customer.id}
                          type="button"
                          onClick={() => {
                            setSelectedCustomer(customer);
                            setCustomerSearch('');
                            setCustomerResults([]);
                            clearFieldError('customer');
                          }}
                          className="block w-full px-2.5 py-1.5 text-left text-sm hover:bg-muted"
                        >
                          {customer.full_name} — {customer.phone}
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            )}
            {fieldErrors.customer && (
              <p className="text-xs text-destructive">{fieldErrors.customer}</p>
            )}
          </div>

          {selectedCustomer && (
            <div className="flex flex-col gap-1">
              <Label htmlFor="equipment">{t('jobNew.equipment')}</Label>
              {equipmentList === null ? (
                <p className="text-sm text-muted-foreground">{t('jobNew.loadingEquipment')}</p>
              ) : (
                <select
                  id="equipment"
                  className={SELECT_CLASS}
                  value={selectedEquipmentId}
                  onChange={(e) => setSelectedEquipmentId(e.target.value)}
                >
                  <option value="">{t('jobNew.noEquipmentManual')}</option>
                  {equipmentList.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.type}
                      {item.brand || item.model
                        ? ` — ${[item.brand, item.model].filter(Boolean).join(' ')}`
                        : ''}
                    </option>
                  ))}
                </select>
              )}
              {selectedEquipment && (
                <p className="text-xs text-muted-foreground">
                  {t('jobNew.addressWillBeSetTo', {
                    address: selectedEquipment.installation_address,
                  })}
                </p>
              )}
            </div>
          )}

          {selectedCustomer && !selectedEquipmentId && (
            <div className="flex flex-col gap-1">
              <Label htmlFor="address">{t('jobNew.address')}</Label>
              <Input
                id="address"
                value={manualAddress}
                aria-invalid={!!fieldErrors.address}
                onChange={(e) => {
                  setManualAddress(e.target.value);
                  clearFieldError('address');
                }}
              />
              {fieldErrors.address && (
                <p className="text-xs text-destructive">{fieldErrors.address}</p>
              )}
            </div>
          )}

          <div className="flex flex-col gap-1">
            <Label htmlFor="reported_issue">{t('jobNew.reportedIssue')}</Label>
            <textarea
              id="reported_issue"
              value={reportedIssue}
              onChange={(e) => {
                setReportedIssue(e.target.value);
                clearFieldError('reported_issue');
              }}
              rows={3}
              aria-invalid={!!fieldErrors.reported_issue}
              className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
            {fieldErrors.reported_issue && (
              <p className="text-xs text-destructive">{fieldErrors.reported_issue}</p>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <Label htmlFor="warranty">{t('jobNew.warrantyClaim')}</Label>
            <select
              id="warranty"
              className={SELECT_CLASS}
              value={warrantyOverride}
              onChange={(e) => setWarrantyOverride(e.target.value as WarrantyOverride)}
            >
              <option value="auto">{t('jobNew.autoDetect')}</option>
              <option value="yes">{t('jobNew.markAsWarranty')}</option>
              <option value="no">{t('jobNew.notWarranty')}</option>
            </select>
          </div>

          <div className="flex gap-2">
            <Button type="submit" disabled={submitting}>
              {submitting ? t('jobNew.creating') : t('jobNew.createJob')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push('/jobs')}
              disabled={submitting}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
