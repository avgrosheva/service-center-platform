'use client';

/**
 * Milestone F15 — organization info (read-only: no PATCH /organizations
 * exists, per the roadmap's own "check before building an edit form that
 * has nowhere to submit to") plus user management. Dispatcher sees the
 * user list read-only; only owner gets create/edit/deactivate controls,
 * matching `require_role` on each backend endpoint exactly (list/get:
 * owner+dispatcher; create/update/deactivate: owner only). Technician
 * never reaches this page at all (RequireRole below).
 */

import { useEffect, useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RequireRole } from '@/components/shell/require-role';
import { useLocale } from '@/lib/i18n/context';
import type { TranslationKey } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth';
import type {
  Organization,
  User,
  UserCreateRequest,
  UserRole,
  UserUpdateRequest,
} from '@/types/api';

const SELECT_CLASS =
  'h-8 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30';

const ROLE_KEYS: Record<UserRole, TranslationKey> = {
  owner: 'settings.roleOwner',
  dispatcher: 'settings.roleDispatcher',
  technician: 'settings.roleTechnician',
};

export default function SettingsPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher']}>
      <SettingsContent />
    </RequireRole>
  );
}

function SettingsContent() {
  const { t, locale } = useLocale();
  const dateLocale = locale === 'ru' ? 'ru-RU' : 'en-US';
  const { user: currentUser } = useAuth();
  const isOwner = currentUser?.role === 'owner';

  const [org, setOrg] = useState<Organization | null>(null);
  const [users, setUsers] = useState<User[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [orgData, usersData] = await Promise.all([
          browserApiClient<Organization>('/organizations/me'),
          browserApiClient<User[]>('/users'),
        ]);
        if (!cancelled) {
          setOrg(orgData);
          setUsers(usersData);
        }
      } catch (err) {
        if (!cancelled)
          setLoadError(err instanceof ApiError ? err.detail : t('settings.failedToLoad'));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activeOwnerCount = useMemo(
    () => (users ?? []).filter((u) => u.role === 'owner' && u.is_active).length,
    [users],
  );

  const [newEmail, setNewEmail] = useState('');
  const [newName, setNewName] = useState('');
  const [newRole, setNewRole] = useState<UserRole>('technician');
  const [newPassword, setNewPassword] = useState('');
  const [createErrors, setCreateErrors] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editRole, setEditRole] = useState<UserRole>('technician');
  const [editActive, setEditActive] = useState(true);
  const [editPassword, setEditPassword] = useState('');
  const [rowError, setRowError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (!newEmail.trim()) errors.email = t('settings.emailRequired');
    if (!newName.trim()) errors.full_name = t('settings.fullNameRequired');
    if (!newPassword.trim()) errors.password = t('settings.passwordRequired');
    if (Object.keys(errors).length > 0) {
      setCreateErrors(errors);
      return;
    }
    setCreating(true);
    setCreateErrors({});
    try {
      const payload: UserCreateRequest = {
        email: newEmail,
        full_name: newName,
        role: newRole,
        password: newPassword,
      };
      const created = await browserApiClient<User>('/users', { method: 'POST', body: payload });
      setUsers((prev) => (prev ? [...prev, created] : [created]));
      setNewEmail('');
      setNewName('');
      setNewPassword('');
      setNewRole('technician');
    } catch (err) {
      let message = t('settings.failedToCreateUser');
      if (err instanceof ApiError) {
        message = err.kind === 'conflict' ? t('settings.emailAlreadyExists') : err.detail;
      }
      setCreateErrors({ _general: message });
    } finally {
      setCreating(false);
    }
  };

  const startEdit = (u: User) => {
    setEditingId(u.id);
    setEditRole(u.role);
    setEditActive(u.is_active);
    setEditPassword('');
    setRowError(null);
  };

  const handleSaveEdit = async (id: string, original: User) => {
    if (editPassword && editPassword.length < 8) {
      setRowError(t('settings.newPasswordTooShort', { count: 8 }));
      return;
    }

    setSavingId(id);
    setRowError(null);
    try {
      const payload: UserUpdateRequest = {};
      if (editRole !== original.role) payload.role = editRole;
      if (editActive !== original.is_active) payload.is_active = editActive;
      if (editPassword) payload.password = editPassword;
      const updated = await browserApiClient<User>(`/users/${id}`, {
        method: 'PATCH',
        body: payload,
      });
      setUsers((prev) => prev?.map((u) => (u.id === id ? updated : u)) ?? prev);
      setEditingId(null);
    } catch (err) {
      setRowError(err instanceof ApiError ? err.detail : t('settings.failedToUpdateUser'));
    } finally {
      setSavingId(null);
    }
  };

  const handleDeactivate = async (id: string) => {
    setSavingId(id);
    setRowError(null);
    try {
      const updated = await browserApiClient<User>(`/users/${id}`, { method: 'DELETE' });
      setUsers((prev) => prev?.map((u) => (u.id === id ? updated : u)) ?? prev);
    } catch (err) {
      setRowError(err instanceof ApiError ? err.detail : t('settings.failedToDeactivateUser'));
    } finally {
      setSavingId(null);
    }
  };

  if (loadError) return <p className="text-sm text-destructive">{loadError}</p>;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <h1 className="text-3xl font-semibold tracking-tight text-foreground">
        {t('settings.title')}
      </h1>
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.organization')}</CardTitle>
        </CardHeader>
        <CardContent>
          {org === null ? (
            <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="font-medium text-muted-foreground">{t('settings.name')}</dt>
              <dd>{org.name}</dd>
              <dt className="font-medium text-muted-foreground">{t('settings.since')}</dt>
              <dd>{new Date(org.created_at).toLocaleDateString(dateLocale)}</dd>
            </dl>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('settings.users')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {rowError && <p className="text-sm text-destructive">{rowError}</p>}

          {users === null ? (
            <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : (
            <div className="overflow-x-auto rounded-2xl bg-background">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="border-b border-border text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">{t('settings.tableName')}</th>
                    <th className="px-3 py-2 font-medium">{t('settings.tableEmail')}</th>
                    <th className="px-3 py-2 font-medium">{t('settings.tableRole')}</th>
                    <th className="px-3 py-2 font-medium">{t('settings.tableStatus')}</th>
                    {isOwner && <th className="px-3 py-2 font-medium" />}
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const isSelf = u.id === currentUser?.id;
                    const isSoleActiveOwner =
                      u.role === 'owner' && u.is_active && activeOwnerCount <= 1;
                    return editingId === u.id ? (
                      <tr key={u.id} className="border-b border-border last:border-0">
                        <td className="px-3 py-2">{u.full_name}</td>
                        <td className="px-3 py-2 text-muted-foreground">{u.email}</td>
                        <td className="px-3 py-2">
                          {isSelf ? (
                            t(ROLE_KEYS[u.role])
                          ) : (
                            <select
                              value={editRole}
                              onChange={(e) => setEditRole(e.target.value as UserRole)}
                              className={SELECT_CLASS}
                            >
                              <option value="owner">{t('settings.roleOwner')}</option>
                              <option value="dispatcher">{t('settings.roleDispatcher')}</option>
                              <option value="technician">{t('settings.roleTechnician')}</option>
                            </select>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <label className="flex items-center gap-1.5">
                            <input
                              type="checkbox"
                              checked={editActive}
                              disabled={isSoleActiveOwner && editActive}
                              onChange={(e) => setEditActive(e.target.checked)}
                            />
                            {t('settings.active')}
                          </label>
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          <div className="flex items-center justify-end gap-2">
                            {!isSelf && (
                              <Input
                                type="password"
                                autoComplete="new-password"
                                placeholder={t('settings.newPasswordOptional')}
                                value={editPassword}
                                onChange={(e) => setEditPassword(e.target.value)}
                                className="h-8 w-56"
                              />
                            )}
                            <Button
                              size="sm"
                              onClick={() => void handleSaveEdit(u.id, u)}
                              disabled={savingId === u.id}
                            >
                              {savingId === u.id ? t('common.saving') : t('common.save')}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                              {t('common.cancel')}
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      <tr key={u.id} className="border-b border-border last:border-0">
                        <td className="px-3 py-2">
                          {u.full_name}
                          {isSelf && (
                            <span className="ml-1 text-xs text-muted-foreground">
                              {t('settings.you')}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">{u.email}</td>
                        <td className="px-3 py-2">{t(ROLE_KEYS[u.role])}</td>
                        <td className="px-3 py-2">
                          {u.is_active ? t('settings.active') : t('settings.deactivated')}
                        </td>
                        {isOwner && (
                          <td className="px-3 py-2 text-right whitespace-nowrap">
                            <Button size="sm" variant="ghost" onClick={() => startEdit(u)}>
                              {t('common.edit')}
                            </Button>
                            {u.is_active && !isSoleActiveOwner && (
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => void handleDeactivate(u.id)}
                                disabled={savingId === u.id}
                              >
                                {t('settings.deactivate')}
                              </Button>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {isOwner && (
            <form
              onSubmit={(e) => void handleCreate(e)}
              className="flex flex-wrap items-start gap-2"
            >
              {createErrors._general && (
                <p className="w-full text-sm text-destructive">{createErrors._general}</p>
              )}
              <div className="flex flex-col gap-1">
                <Label htmlFor="new-name">{t('settings.name')}</Label>
                <Input
                  id="new-name"
                  autoComplete="off"
                  value={newName}
                  aria-invalid={!!createErrors.full_name}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-36"
                />
                {createErrors.full_name && (
                  <p className="text-xs text-destructive">{createErrors.full_name}</p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="new-email">{t('settings.email')}</Label>
                <Input
                  id="new-email"
                  autoComplete="off"
                  value={newEmail}
                  aria-invalid={!!createErrors.email}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="w-44"
                />
                {createErrors.email && (
                  <p className="text-xs text-destructive">{createErrors.email}</p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="new-role">{t('settings.role')}</Label>
                <select
                  id="new-role"
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value as UserRole)}
                  className={SELECT_CLASS}
                >
                  <option value="owner">{t('settings.roleOwner')}</option>
                  <option value="dispatcher">{t('settings.roleDispatcher')}</option>
                  <option value="technician">{t('settings.roleTechnician')}</option>
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="new-password">{t('settings.password')}</Label>
                <Input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  aria-invalid={!!createErrors.password}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-36"
                />
                {createErrors.password && (
                  <p className="text-xs text-destructive">{createErrors.password}</p>
                )}
              </div>
              <Button type="submit" disabled={creating} className="self-end">
                {creating ? t('settings.creating') : t('settings.addUser')}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
