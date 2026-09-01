'use client';

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { parseFieldErrors } from '@/lib/form-errors';
import type {
  MaterialItem,
  MaterialItemCreateRequest,
  MaterialItemUpdateRequest,
} from '@/types/api';

type DraftValues = { name: string; quantity: string; unit_cost: string };

const EMPTY_DRAFT: DraftValues = { name: '', quantity: '', unit_cost: '' };

function validateDraft(values: DraftValues): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!values.name.trim()) errors.name = 'Name is required.';
  const qty = Number(values.quantity);
  if (!values.quantity.trim() || !Number.isFinite(qty) || qty <= 0) {
    errors.quantity = 'Quantity must be greater than 0.';
  }
  if (values.unit_cost.trim()) {
    const cost = Number(values.unit_cost);
    if (!Number.isFinite(cost) || cost < 0) errors.unit_cost = 'Unit cost must be 0 or more.';
  }
  return errors;
}

function total(item: MaterialItem): string {
  if (item.unit_cost === null) return '—';
  return (Number(item.quantity) * Number(item.unit_cost)).toFixed(2);
}

export function JobMaterials({ jobId, onActivity }: { jobId: string; onActivity?: () => void }) {
  const [materials, setMaterials] = useState<MaterialItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [newDraft, setNewDraft] = useState<DraftValues>(EMPTY_DRAFT);
  const [newErrors, setNewErrors] = useState<Record<string, string>>({});
  const [adding, setAdding] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<DraftValues>(EMPTY_DRAFT);
  const [editErrors, setEditErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<MaterialItem[]>(`/jobs/${jobId}/materials`);
        if (!cancelled) setMaterials(data);
      } catch (err) {
        if (!cancelled)
          setLoadError(err instanceof ApiError ? err.detail : 'Failed to load materials.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors = validateDraft(newDraft);
    if (Object.keys(errors).length > 0) {
      setNewErrors(errors);
      return;
    }
    setAdding(true);
    setNewErrors({});
    setActionError(null);
    try {
      const payload: MaterialItemCreateRequest = {
        name: newDraft.name,
        quantity: newDraft.quantity,
        unit_cost: newDraft.unit_cost.trim() || null,
      };
      const created = await browserApiClient<MaterialItem>(`/jobs/${jobId}/materials`, {
        method: 'POST',
        body: payload,
      });
      setMaterials((prev) => (prev ? [...prev, created] : [created]));
      setNewDraft(EMPTY_DRAFT);
      onActivity?.();
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') {
        setNewErrors(parseFieldErrors(err.detail));
      } else {
        setActionError(err instanceof ApiError ? err.detail : 'Failed to add material.');
      }
    } finally {
      setAdding(false);
    }
  };

  const startEdit = (item: MaterialItem) => {
    setEditingId(item.id);
    setEditDraft({ name: item.name, quantity: item.quantity, unit_cost: item.unit_cost ?? '' });
    setEditErrors({});
    setActionError(null);
  };

  const handleSaveEdit = async (id: string) => {
    const errors = validateDraft(editDraft);
    if (Object.keys(errors).length > 0) {
      setEditErrors(errors);
      return;
    }
    setSaving(true);
    setEditErrors({});
    setActionError(null);
    try {
      const payload: MaterialItemUpdateRequest = {
        name: editDraft.name,
        quantity: editDraft.quantity,
        unit_cost: editDraft.unit_cost.trim() || null,
      };
      const updated = await browserApiClient<MaterialItem>(`/jobs/${jobId}/materials/${id}`, {
        method: 'PATCH',
        body: payload,
      });
      setMaterials((prev) => prev?.map((m) => (m.id === id ? updated : m)) ?? prev);
      setEditingId(null);
      onActivity?.();
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') {
        setEditErrors(parseFieldErrors(err.detail));
      } else {
        setActionError(err instanceof ApiError ? err.detail : 'Failed to save material.');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async (id: string) => {
    setRemovingId(id);
    setActionError(null);
    try {
      await browserApiClient(`/jobs/${jobId}/materials/${id}`, { method: 'DELETE' });
      setMaterials((prev) => prev?.filter((m) => m.id !== id) ?? prev);
      onActivity?.();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : 'Failed to remove material.');
    } finally {
      setRemovingId(null);
      setConfirmRemoveId(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {loadError && <p className="text-sm text-destructive">{loadError}</p>}
      {actionError && <p className="text-sm text-destructive">{actionError}</p>}

      {materials === null ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
      ) : materials.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No materials logged yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full min-w-[420px] text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Qty</th>
                <th className="px-3 py-2 font-medium">Unit cost</th>
                <th className="px-3 py-2 font-medium">Total</th>
                <th className="px-3 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {materials.map((item) =>
                editingId === item.id ? (
                  <tr
                    key={item.id}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
                  >
                    <td className="px-3 py-2">
                      <Input
                        value={editDraft.name}
                        aria-invalid={!!editErrors.name}
                        onChange={(e) => setEditDraft((v) => ({ ...v, name: e.target.value }))}
                        className="w-32"
                      />
                      {editErrors.name && (
                        <p className="text-xs text-destructive">{editErrors.name}</p>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        value={editDraft.quantity}
                        aria-invalid={!!editErrors.quantity}
                        onChange={(e) => setEditDraft((v) => ({ ...v, quantity: e.target.value }))}
                        className="w-20"
                      />
                      {editErrors.quantity && (
                        <p className="text-xs text-destructive">{editErrors.quantity}</p>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        value={editDraft.unit_cost}
                        aria-invalid={!!editErrors.unit_cost}
                        onChange={(e) => setEditDraft((v) => ({ ...v, unit_cost: e.target.value }))}
                        className="w-24"
                      />
                      {editErrors.unit_cost && (
                        <p className="text-xs text-destructive">{editErrors.unit_cost}</p>
                      )}
                    </td>
                    <td className="px-3 py-2 text-zinc-500">—</td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      <Button
                        size="sm"
                        onClick={() => void handleSaveEdit(item.id)}
                        disabled={saving}
                      >
                        {saving ? 'Saving…' : 'Save'}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditingId(null)}
                        disabled={saving}
                      >
                        Cancel
                      </Button>
                    </td>
                  </tr>
                ) : (
                  <tr
                    key={item.id}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
                  >
                    <td className="px-3 py-2">{item.name}</td>
                    <td className="px-3 py-2">{item.quantity}</td>
                    <td className="px-3 py-2">{item.unit_cost ?? '—'}</td>
                    <td className="px-3 py-2">{total(item)}</td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {confirmRemoveId === item.id ? (
                        <span className="inline-flex gap-2">
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => void handleRemove(item.id)}
                            disabled={removingId === item.id}
                          >
                            Confirm
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setConfirmRemoveId(null)}
                          >
                            Cancel
                          </Button>
                        </span>
                      ) : (
                        <span className="inline-flex gap-2">
                          <Button size="sm" variant="ghost" onClick={() => startEdit(item)}>
                            Edit
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setConfirmRemoveId(item.id)}
                          >
                            Remove
                          </Button>
                        </span>
                      )}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      )}

      <form onSubmit={(e) => void handleAdd(e)} className="flex flex-wrap items-start gap-2">
        <div className="flex flex-col gap-1">
          <Input
            placeholder="Name"
            value={newDraft.name}
            aria-invalid={!!newErrors.name}
            onChange={(e) => setNewDraft((v) => ({ ...v, name: e.target.value }))}
            className="w-32"
          />
          {newErrors.name && <p className="text-xs text-destructive">{newErrors.name}</p>}
        </div>
        <div className="flex flex-col gap-1">
          <Input
            placeholder="Qty"
            value={newDraft.quantity}
            aria-invalid={!!newErrors.quantity}
            onChange={(e) => setNewDraft((v) => ({ ...v, quantity: e.target.value }))}
            className="w-20"
          />
          {newErrors.quantity && <p className="text-xs text-destructive">{newErrors.quantity}</p>}
        </div>
        <div className="flex flex-col gap-1">
          <Input
            placeholder="Unit cost"
            value={newDraft.unit_cost}
            aria-invalid={!!newErrors.unit_cost}
            onChange={(e) => setNewDraft((v) => ({ ...v, unit_cost: e.target.value }))}
            className="w-24"
          />
          {newErrors.unit_cost && <p className="text-xs text-destructive">{newErrors.unit_cost}</p>}
        </div>
        <Button type="submit" disabled={adding}>
          {adding ? 'Adding…' : 'Add material'}
        </Button>
      </form>
    </div>
  );
}
