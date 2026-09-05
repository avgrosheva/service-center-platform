'use client';

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useLocale } from '@/lib/i18n/context';
import type { TranslationKey } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { parseFieldErrors } from '@/lib/form-errors';
import type {
  MaterialItem,
  MaterialItemCreateRequest,
  MaterialItemUpdateRequest,
} from '@/types/api';

type DraftValues = { name: string; quantity: string; unit_cost: string };

const EMPTY_DRAFT: DraftValues = { name: '', quantity: '', unit_cost: '' };

function validateDraft(
  values: DraftValues,
  t: (key: TranslationKey) => string,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!values.name.trim()) errors.name = t('jobMaterials.nameRequired');
  const qty = Number(values.quantity);
  if (!values.quantity.trim() || !Number.isFinite(qty) || qty <= 0) {
    errors.quantity = t('jobMaterials.quantityMustBePositive');
  }
  if (values.unit_cost.trim()) {
    const cost = Number(values.unit_cost);
    if (!Number.isFinite(cost) || cost < 0) {
      errors.unit_cost = t('jobMaterials.unitCostMustBeNonNegative');
    }
  }
  return errors;
}

function total(item: MaterialItem): string {
  if (item.unit_cost === null) return '—';
  return (Number(item.quantity) * Number(item.unit_cost)).toFixed(2);
}

export function JobMaterials({ jobId, onActivity }: { jobId: string; onActivity?: () => void }) {
  const { t } = useLocale();
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
          setLoadError(err instanceof ApiError ? err.detail : t('jobMaterials.failedToLoad'));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors = validateDraft(newDraft, t);
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
        setActionError(err instanceof ApiError ? err.detail : t('jobMaterials.failedToAdd'));
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
    const errors = validateDraft(editDraft, t);
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
        setActionError(err instanceof ApiError ? err.detail : t('jobMaterials.failedToSave'));
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
      setActionError(err instanceof ApiError ? err.detail : t('jobMaterials.failedToRemove'));
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
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : materials.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('jobMaterials.noMaterialsYet')}</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[420px] text-left text-sm">
            <thead className="border-b border-border text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">{t('jobMaterials.tableName')}</th>
                <th className="px-3 py-2 font-medium">{t('jobMaterials.tableQty')}</th>
                <th className="px-3 py-2 font-medium">{t('jobMaterials.tableUnitCost')}</th>
                <th className="px-3 py-2 font-medium">{t('jobMaterials.tableTotal')}</th>
                <th className="px-3 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {materials.map((item) =>
                editingId === item.id ? (
                  <tr key={item.id} className="border-b border-border last:border-0">
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
                    <td className="px-3 py-2 text-muted-foreground">—</td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      <Button
                        size="sm"
                        onClick={() => void handleSaveEdit(item.id)}
                        disabled={saving}
                      >
                        {saving ? t('common.saving') : t('common.save')}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditingId(null)}
                        disabled={saving}
                      >
                        {t('common.cancel')}
                      </Button>
                    </td>
                  </tr>
                ) : (
                  <tr key={item.id} className="border-b border-border last:border-0">
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
                            {t('common.confirm')}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setConfirmRemoveId(null)}
                          >
                            {t('common.cancel')}
                          </Button>
                        </span>
                      ) : (
                        <span className="inline-flex gap-2">
                          <Button size="sm" variant="ghost" onClick={() => startEdit(item)}>
                            {t('common.edit')}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setConfirmRemoveId(item.id)}
                          >
                            {t('jobMaterials.remove')}
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
            placeholder={t('jobMaterials.namePlaceholder')}
            value={newDraft.name}
            aria-invalid={!!newErrors.name}
            onChange={(e) => setNewDraft((v) => ({ ...v, name: e.target.value }))}
            className="w-32"
          />
          {newErrors.name && <p className="text-xs text-destructive">{newErrors.name}</p>}
        </div>
        <div className="flex flex-col gap-1">
          <Input
            placeholder={t('jobMaterials.qtyPlaceholder')}
            value={newDraft.quantity}
            aria-invalid={!!newErrors.quantity}
            onChange={(e) => setNewDraft((v) => ({ ...v, quantity: e.target.value }))}
            className="w-20"
          />
          {newErrors.quantity && <p className="text-xs text-destructive">{newErrors.quantity}</p>}
        </div>
        <div className="flex flex-col gap-1">
          <Input
            placeholder={t('jobMaterials.unitCostPlaceholder')}
            value={newDraft.unit_cost}
            aria-invalid={!!newErrors.unit_cost}
            onChange={(e) => setNewDraft((v) => ({ ...v, unit_cost: e.target.value }))}
            className="w-24"
          />
          {newErrors.unit_cost && <p className="text-xs text-destructive">{newErrors.unit_cost}</p>}
        </div>
        <Button type="submit" disabled={adding}>
          {adding ? t('jobMaterials.adding') : t('jobMaterials.addMaterial')}
        </Button>
      </form>
    </div>
  );
}
