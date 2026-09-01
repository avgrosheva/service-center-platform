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
  const [searchInput, setSearchInput] = useState('');
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmArchiveId, setConfirmArchiveId] = useState<string | null>(null);
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const isFirstRun = useRef(true);

  const load = useCallback(async (search: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await browserApiClient<Customer[]>('/customers', {
        params: { search: search.trim() || undefined },
      });
      setCustomers(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load customers.');
    } finally {
      setLoading(false);
    }
  }, []);

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
      setError(err instanceof ApiError ? err.detail : 'Failed to archive customer.');
    } finally {
      setArchivingId(null);
      setConfirmArchiveId(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <input
          type="search"
          placeholder="Search by name or phone…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="h-8 w-64 max-w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        />
        <Button render={<Link href="/customers/new" />} nativeButton={false}>
          New customer
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
      ) : !customers || customers.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {searchInput.trim() ? 'No customers match your search.' : 'No customers yet.'}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Phone</th>
                <th className="px-4 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {customers.map((customer) => (
                <tr
                  key={customer.id}
                  className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
                >
                  <td className="px-4 py-2">
                    <Link href={`/customers/${customer.id}`} className="hover:underline">
                      {customer.full_name}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-zinc-600 dark:text-zinc-400">{customer.phone}</td>
                  <td className="px-4 py-2 text-right">
                    {confirmArchiveId === customer.id ? (
                      <span className="inline-flex items-center gap-2">
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={archivingId === customer.id}
                          onClick={() => void handleArchive(customer.id)}
                        >
                          Confirm
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setConfirmArchiveId(null)}>
                          Cancel
                        </Button>
                      </span>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setConfirmArchiveId(customer.id)}
                      >
                        Archive
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
