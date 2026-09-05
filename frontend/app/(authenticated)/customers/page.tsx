'use client';

/**
 * Milestone F5 — customer list + search. Search is debounced (350ms)
 * against the backend's own `ILIKE` search on `/customers?search=...`
 * (customer_service.list_customers) rather than filtered client-side —
 * matches the roadmap's explicit "search-as-you-type... debounced, not
 * fired on every keystroke" requirement. The very first load (mount, no
 * search text yet) skips the debounce delay via a 0ms timeout instead of
 * calling the fetch synchronously in the effect — see dashboard/page.tsx
 * for why a direct synchronous call here would trip
 * `react-hooks/set-state-in-effect`.
 */

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { RequireRole } from '@/components/shell/require-role';
import { useLocale } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import type { Customer } from '@/types/api';

const SEARCH_DEBOUNCE_MS = 350;

export default function CustomersPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher']}>
      <CustomersContent />
    </RequireRole>
  );
}

function CustomersContent() {
  const { t } = useLocale();
  const [searchInput, setSearchInput] = useState('');
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmArchiveId, setConfirmArchiveId] = useState<string | null>(null);
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const isFirstRun = useRef(true);

  const load = useCallback(
    async (search: string) => {
      setLoading(true);
      setError(null);
      try {
        const data = await browserApiClient<Customer[]>('/customers', {
          params: { search: search.trim() || undefined },
        });
        setCustomers(data);
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : t('customers.failedToLoad'));
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  useEffect(() => {
    const delay = isFirstRun.current ? 0 : SEARCH_DEBOUNCE_MS;
    isFirstRun.current = false;
    const handle = setTimeout(() => void load(searchInput), delay);
    return () => clearTimeout(handle);
  }, [searchInput, load]);

  const handleArchive = async (id: string) => {
    setArchivingId(id);
    try {
      await browserApiClient(`/customers/${id}`, { method: 'DELETE' });
      setCustomers((prev) => (prev ? prev.filter((c) => c.id !== id) : prev));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t('customers.failedToArchive'));
    } finally {
      setArchivingId(null);
      setConfirmArchiveId(null);
    }
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <h1 className="text-3xl font-semibold tracking-tight text-foreground">
        {t('customers.title')}
      </h1>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <input
          type="search"
          placeholder={t('customers.searchPlaceholder')}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="h-8 w-64 max-w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        />
        <Button render={<Link href="/customers/new" />} nativeButton={false}>
          {t('customers.newCustomer')}
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : !customers || customers.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {searchInput.trim()
            ? t('customers.noCustomersMatchSearch')
            : t('customers.noCustomersYet')}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-3xl bg-card">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead className="border-b border-border text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">{t('customers.tableName')}</th>
                <th className="px-4 py-2 font-medium">{t('customers.tablePhone')}</th>
                <th className="px-4 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {customers.map((customer) => (
                <tr key={customer.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-2">
                    <Link href={`/customers/${customer.id}`} className="hover:underline">
                      {customer.full_name}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">{customer.phone}</td>
                  <td className="px-4 py-2 text-right">
                    {confirmArchiveId === customer.id ? (
                      <span className="inline-flex items-center gap-2">
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={archivingId === customer.id}
                          onClick={() => void handleArchive(customer.id)}
                        >
                          {t('common.confirm')}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setConfirmArchiveId(null)}>
                          {t('common.cancel')}
                        </Button>
                      </span>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setConfirmArchiveId(customer.id)}
                      >
                        {t('common.archive')}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
