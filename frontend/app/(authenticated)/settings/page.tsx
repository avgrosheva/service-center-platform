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

export default function SettingsPage() {
  return (
    <RequireRole allow={['owner', 'dispatcher']}>
      <SettingsContent />
    </RequireRole>
  );
}

function SettingsContent() {
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
          setLoadError(err instanceof ApiError ? err.detail : 'Failed to load settings.');
      }
    })();
    return () => {
      cancelled = true;
    };
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
  const [rowError, setRowError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (!newEmail.trim()) errors.email = 'Email is required.';
    if (!newName.trim()) errors.full_name = 'Name is required.';
    if (!newPassword.trim()) errors.password = 'Password is required.';
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
      setCreateErrors({
        _general: err instanceof ApiError ? err.detail : 'Failed to create user.',
      });
    } finally {
      setCreating(false);
    }
  };

  const startEdit = (u: User) => {
    setEditingId(u.id);
    setEditRole(u.role);
    setEditActive(u.is_active);
    setRowError(null);
  };

  const handleSaveEdit = async (id: string, original: User) => {
    setSavingId(id);
    setRowError(null);
    try {
      const payload: UserUpdateRequest = {};
      if (editRole !== original.role) payload.role = editRole;
      if (editActive !== original.is_active) payload.is_active = editActive;
      const updated = await browserApiClient<User>(`/users/${id}`, {
        method: 'PATCH',
        body: payload,
      });
      setUsers((prev) => prev?.map((u) => (u.id === id ? updated : u)) ?? prev);
      setEditingId(null);
    } catch (err) {
      setRowError(err instanceof ApiError ? err.detail : 'Failed to update user.');
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
      setRowError(err instanceof ApiError ? err.detail : 'Failed to deactivate user.');
    } finally {
      setSavingId(null);
    }
  };

  if (loadError) return <p className="text-sm text-destructive">{loadError}</p>;

  return (
    <div className="flex flex-col gap-4">
      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Organization</CardTitle>
        </CardHeader>
        <CardContent>
          {org === null ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
          ) : (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="font-medium text-zinc-500 dark:text-zinc-400">Name</dt>
              <dd>{org.name}</dd>
              <dt className="font-medium text-zinc-500 dark:text-zinc-400">Since</dt>
              <dd>{new Date(org.created_at).toLocaleDateString()}</dd>
            </dl>
          )}
        </CardContent>
      </Card>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Users</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {rowError && <p className="text-sm text-destructive">{rowError}</p>}

          {users === null ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Email</th>
                    <th className="px-3 py-2 font-medium">Role</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    {isOwner && <th className="px-3 py-2 font-medium" />}
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const isSelf = u.id === currentUser?.id;
                    const isSoleActiveOwner =
                      u.role === 'owner' && u.is_active && activeOwnerCount <= 1;
                    return editingId === u.id ? (
                      <tr
                        key={u.id}
                        className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
                      >
                        <td className="px-3 py-2">{u.full_name}</td>
                        <td className="px-3 py-2 text-zinc-500 dark:text-zinc-400">{u.email}</td>
                        <td className="px-3 py-2">
                          {isSelf ? (
                            u.role
                          ) : (
                            <select
                              value={editRole}
                              onChange={(e) => setEditRole(e.target.value as UserRole)}
                              className={SELECT_CLASS}
                            >
                              <option value="owner">Owner</option>
                              <option value="dispatcher">Dispatcher</option>
                              <option value="technician">Technician</option>
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
                            Active
                          </label>
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          <Button
                            size="sm"
                            onClick={() => void handleSaveEdit(u.id, u)}
                            disabled={savingId === u.id}
                          >
                            {savingId === u.id ? 'Saving…' : 'Save'}
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                            Cancel
                          </Button>
                        </td>
                      </tr>
                    ) : (
                      <tr
                        key={u.id}
                        className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
                      >
                        <td className="px-3 py-2">
                          {u.full_name}
                          {isSelf && <span className="ml-1 text-xs text-zinc-500">(you)</span>}
                        </td>
                        <td className="px-3 py-2 text-zinc-500 dark:text-zinc-400">{u.email}</td>
                        <td className="px-3 py-2 capitalize">{u.role}</td>
                        <td className="px-3 py-2">{u.is_active ? 'Active' : 'Deactivated'}</td>
                        {isOwner && (
                          <td className="px-3 py-2 text-right whitespace-nowrap">
                            <Button size="sm" variant="ghost" onClick={() => startEdit(u)}>
                              Edit
                            </Button>
                            {u.is_active && !isSoleActiveOwner && (
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => void handleDeactivate(u.id)}
                                disabled={savingId === u.id}
                              >
                                Deactivate
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
                <Label htmlFor="new-name">Name</Label>
                <Input
                  id="new-name"
                  value={newName}
                  aria-invalid={!!createErrors.full_name}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-36"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="new-email">Email</Label>
                <Input
                  id="new-email"
                  value={newEmail}
                  aria-invalid={!!createErrors.email}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="w-44"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="new-role">Role</Label>
                <select
                  id="new-role"
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value as UserRole)}
                  className={SELECT_CLASS}
                >
                  <option value="owner">Owner</option>
                  <option value="dispatcher">Dispatcher</option>
                  <option value="technician">Technician</option>
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="new-password">Password</Label>
                <Input
                  id="new-password"
                  type="password"
                  value={newPassword}
                  aria-invalid={!!createErrors.password}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-36"
                />
              </div>
              <Button type="submit" disabled={creating} className="self-end">
                {creating ? 'Creating…' : 'Add user'}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
