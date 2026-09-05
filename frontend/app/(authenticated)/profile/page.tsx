'use client';

/**
 * Self-service profile page — a signed-in user editing their own name,
 * email, phone, password, and avatar. Distinct from Settings' user roster
 * (owner-only, manages *other* users' role/active status): every field
 * here goes through `/auth/me`, which only ever touches the caller's own
 * row, so all three roles reach this page and there's nothing here for
 * `RequireRole` to actually gate on — it's included purely for the same
 * "every authenticated page wraps its content this way" consistency the
 * rest of the app follows.
 */

import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RequireRole } from '@/components/shell/require-role';
import { useLocale } from '@/lib/i18n/context';
import type { TranslationKey } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import { parseFieldErrors } from '@/lib/form-errors';
import { useAuth } from '@/lib/auth';
import type {
  AvatarConfirmRequest,
  AvatarUploadUrlRequest,
  AvatarUploadUrlResponse,
  MeUpdateRequest,
  Organization,
  PasswordChangeRequest,
  PhotoContentType,
  User,
  UserRole,
} from '@/types/api';

const ACCEPTED_CONTENT_TYPES: PhotoContentType[] = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/heic',
];

const ROLE_KEYS: Record<UserRole, TranslationKey> = {
  owner: 'profile.roleOwner',
  dispatcher: 'profile.roleDispatcher',
  technician: 'profile.roleTechnician',
};

function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]![0]}${parts[parts.length - 1]![0]}`.toUpperCase();
}

function clearFieldError(
  setErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>,
  name: string,
) {
  setErrors((prev) => {
    if (!(name in prev)) return prev;
    const next = { ...prev };
    delete next[name];
    return next;
  });
}

export default function ProfilePage() {
  return (
    <RequireRole allow={['owner', 'dispatcher', 'technician']}>
      <ProfileContent />
    </RequireRole>
  );
}

function ProfileContent() {
  const { t, locale } = useLocale();
  const dateLocale = locale === 'ru' ? 'ru-RU' : 'en-US';
  const { user, updateUser } = useAuth();
  const [orgName, setOrgName] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const org = await browserApiClient<Organization>('/organizations/me');
        if (!cancelled) setOrgName(org.name);
      } catch {
        // Non-fatal — matches UserMenu's own handling of this same call.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // --- Personal info (name / email / phone) ---
  const [editingInfo, setEditingInfo] = useState(false);
  const [infoValues, setInfoValues] = useState({ full_name: '', email: '', phone: '' });
  const [infoErrors, setInfoErrors] = useState<Record<string, string>>({});
  const [infoFormError, setInfoFormError] = useState<string | null>(null);
  const [savingInfo, setSavingInfo] = useState(false);

  const startEditingInfo = () => {
    if (!user) return;
    setInfoValues({ full_name: user.full_name, email: user.email, phone: user.phone ?? '' });
    setInfoErrors({});
    setInfoFormError(null);
    setEditingInfo(true);
  };

  const handleSaveInfo = async (e: FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (!infoValues.full_name.trim()) errors.full_name = t('profile.fullNameRequired');
    if (!infoValues.email.trim()) errors.email = t('profile.emailRequired');
    if (Object.keys(errors).length > 0) {
      setInfoErrors(errors);
      return;
    }

    setSavingInfo(true);
    setInfoErrors({});
    setInfoFormError(null);
    try {
      const payload: MeUpdateRequest = {
        full_name: infoValues.full_name,
        email: infoValues.email,
        phone: infoValues.phone.trim(),
      };
      const updated = await browserApiClient<User>('/auth/me', { method: 'PATCH', body: payload });
      updateUser(updated);
      setEditingInfo(false);
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'conflict') {
        setInfoFormError(t('profile.emailAlreadyExists'));
      } else if (err instanceof ApiError && err.kind === 'validation') {
        const parsed = parseFieldErrors(err.detail);
        if (Object.keys(parsed).length > 0) setInfoErrors(parsed);
        else setInfoFormError(err.detail);
      } else {
        setInfoFormError(err instanceof ApiError ? err.detail : t('profile.failedToSave'));
      }
    } finally {
      setSavingInfo(false);
    }
  };

  // --- Password change ---
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordErrors, setPasswordErrors] = useState<Record<string, string>>({});
  const [passwordFormError, setPasswordFormError] = useState<string | null>(null);
  const [passwordChanged, setPasswordChanged] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (!currentPassword) errors.current_password = t('profile.currentPasswordRequired');
    if (!newPassword) errors.new_password = t('profile.newPasswordRequired');
    else if (newPassword.length < 8)
      errors.new_password = t('profile.newPasswordTooShort', { count: 8 });
    if (newPassword && confirmPassword !== newPassword) {
      errors.confirm_password = t('profile.passwordsDoNotMatch');
    }
    if (Object.keys(errors).length > 0) {
      setPasswordErrors(errors);
      return;
    }

    setChangingPassword(true);
    setPasswordErrors({});
    setPasswordFormError(null);
    setPasswordChanged(false);
    try {
      const payload: PasswordChangeRequest = {
        current_password: currentPassword,
        new_password: newPassword,
      };
      await browserApiClient<void>('/auth/me/password', { method: 'POST', body: payload });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setPasswordChanged(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setPasswordFormError(t('profile.incorrectCurrentPassword'));
      } else if (err instanceof ApiError && err.kind === 'validation') {
        const parsed = parseFieldErrors(err.detail);
        if (Object.keys(parsed).length > 0) setPasswordErrors(parsed);
        else setPasswordFormError(err.detail);
      } else {
        setPasswordFormError(
          err instanceof ApiError ? err.detail : t('profile.failedToChangePassword'),
        );
      }
    } finally {
      setChangingPassword(false);
    }
  };

  // --- Avatar upload/remove — same 3-step presigned-URL flow as job
  // photos (job-photos.tsx), just against /auth/me/avatar/* instead of a
  // job's sub-resource. ---
  const [avatarError, setAvatarError] = useState<string | null>(null);
  const [avatarBusy, setAvatarBusy] = useState<'uploading' | 'removing' | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleAvatarChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarError(null);
    if (!ACCEPTED_CONTENT_TYPES.includes(file.type as PhotoContentType)) {
      setAvatarError(t('profile.unsupportedFileType', { type: file.type || 'unknown' }));
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setAvatarBusy('uploading');
    try {
      const { upload_url, s3_key } = await browserApiClient<AvatarUploadUrlResponse>(
        '/auth/me/avatar/upload-url',
        { method: 'POST', body: { content_type: file.type } as AvatarUploadUrlRequest },
      );
      const putRes = await fetch(upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': file.type },
        body: file,
      });
      if (!putRes.ok) {
        throw new Error(`Upload to storage failed (HTTP ${putRes.status}).`);
      }
      const updated = await browserApiClient<User>('/auth/me/avatar', {
        method: 'POST',
        body: { s3_key } as AvatarConfirmRequest,
      });
      updateUser(updated);
    } catch (err) {
      setAvatarError(
        err instanceof ApiError
          ? err.detail
          : err instanceof Error
            ? err.message
            : t('profile.failedToUploadPhoto'),
      );
    } finally {
      setAvatarBusy(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleRemoveAvatar = async () => {
    setAvatarBusy('removing');
    setAvatarError(null);
    try {
      const updated = await browserApiClient<User>('/auth/me/avatar', { method: 'DELETE' });
      updateUser(updated);
    } catch (err) {
      setAvatarError(err instanceof ApiError ? err.detail : t('profile.failedToUploadPhoto'));
    } finally {
      setAvatarBusy(null);
    }
  };

  if (!user) return <p className="text-sm text-muted-foreground">{t('common.loading')}</p>;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <h1 className="text-3xl font-semibold tracking-tight text-foreground">
        {t('profile.title')}
      </h1>

      <Card>
        <CardContent className="flex items-center gap-4 pt-6">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={avatarBusy !== null}
            className="group relative flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary font-mono text-xl font-medium tabular-nums text-primary-foreground"
          >
            {user.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- presigned S3/MinIO URL, not a static/local asset next/image can optimize
              <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
            ) : (
              initials(user.full_name)
            )}
            <span className="absolute inset-0 flex items-center justify-center bg-black/50 text-center text-[11px] font-medium text-white opacity-0 transition-opacity group-hover:opacity-100">
              {avatarBusy === 'uploading' ? t('profile.uploadingPhoto') : t('profile.changePhoto')}
            </span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_CONTENT_TYPES.join(',')}
            onChange={(e) => void handleAvatarChange(e)}
            className="hidden"
          />
          <div className="flex flex-col gap-1">
            <span className="text-lg font-semibold">{user.full_name}</span>
            <span className="text-sm text-muted-foreground">
              {t(ROLE_KEYS[user.role])}
              {orgName ? ` · ${orgName}` : ''}
            </span>
            {user.avatar_url && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-auto self-start px-0 text-destructive hover:text-destructive"
                onClick={() => void handleRemoveAvatar()}
                disabled={avatarBusy !== null}
              >
                {avatarBusy === 'removing' ? t('profile.removingPhoto') : t('profile.removePhoto')}
              </Button>
            )}
            {avatarError && <p className="text-xs text-destructive">{avatarError}</p>}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('profile.personalInfo')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {infoFormError && <p className="text-sm text-destructive">{infoFormError}</p>}

          {editingInfo ? (
            <form onSubmit={(e) => void handleSaveInfo(e)} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <Label htmlFor="profile-full-name">{t('profile.fullName')}</Label>
                <Input
                  id="profile-full-name"
                  value={infoValues.full_name}
                  aria-invalid={!!infoErrors.full_name}
                  onChange={(e) => {
                    setInfoValues((v) => ({ ...v, full_name: e.target.value }));
                    clearFieldError(setInfoErrors, 'full_name');
                  }}
                />
                {infoErrors.full_name && (
                  <p className="text-xs text-destructive">{infoErrors.full_name}</p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="profile-email">{t('profile.email')}</Label>
                <Input
                  id="profile-email"
                  type="email"
                  value={infoValues.email}
                  aria-invalid={!!infoErrors.email}
                  onChange={(e) => {
                    setInfoValues((v) => ({ ...v, email: e.target.value }));
                    clearFieldError(setInfoErrors, 'email');
                  }}
                />
                {infoErrors.email && <p className="text-xs text-destructive">{infoErrors.email}</p>}
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="profile-phone">{t('profile.phone')}</Label>
                <Input
                  id="profile-phone"
                  value={infoValues.phone}
                  aria-invalid={!!infoErrors.phone}
                  onChange={(e) => {
                    setInfoValues((v) => ({ ...v, phone: e.target.value }));
                    clearFieldError(setInfoErrors, 'phone');
                  }}
                />
                {infoErrors.phone && <p className="text-xs text-destructive">{infoErrors.phone}</p>}
              </div>
              <div className="flex gap-2">
                <Button type="submit" disabled={savingInfo}>
                  {savingInfo ? t('common.saving') : t('common.save')}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setEditingInfo(false)}
                  disabled={savingInfo}
                >
                  {t('common.cancel')}
                </Button>
              </div>
            </form>
          ) : (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                <dt className="font-medium text-muted-foreground">{t('profile.fullName')}</dt>
                <dd>{user.full_name}</dd>
                <dt className="font-medium text-muted-foreground">{t('profile.email')}</dt>
                <dd>{user.email}</dd>
                <dt className="font-medium text-muted-foreground">{t('profile.phone')}</dt>
                <dd>{user.phone || t('profile.noPhone')}</dd>
              </dl>
              <div>
                <Button variant="outline" onClick={startEditingInfo}>
                  {t('common.edit')}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('profile.password')}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => void handleChangePassword(e)} className="flex flex-col gap-4">
            {passwordFormError && <p className="text-sm text-destructive">{passwordFormError}</p>}
            {passwordChanged && (
              <p className="text-sm text-status-completed">{t('profile.passwordChanged')}</p>
            )}
            <div className="flex flex-col gap-1">
              <Label htmlFor="profile-current-password">{t('profile.currentPassword')}</Label>
              <Input
                id="profile-current-password"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                aria-invalid={!!passwordErrors.current_password}
                onChange={(e) => {
                  setCurrentPassword(e.target.value);
                  clearFieldError(setPasswordErrors, 'current_password');
                }}
              />
              {passwordErrors.current_password && (
                <p className="text-xs text-destructive">{passwordErrors.current_password}</p>
              )}
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="profile-new-password">{t('profile.newPassword')}</Label>
              <Input
                id="profile-new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                aria-invalid={!!passwordErrors.new_password}
                onChange={(e) => {
                  setNewPassword(e.target.value);
                  clearFieldError(setPasswordErrors, 'new_password');
                }}
              />
              {passwordErrors.new_password && (
                <p className="text-xs text-destructive">{passwordErrors.new_password}</p>
              )}
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="profile-confirm-password">{t('profile.confirmNewPassword')}</Label>
              <Input
                id="profile-confirm-password"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                aria-invalid={!!passwordErrors.confirm_password}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  clearFieldError(setPasswordErrors, 'confirm_password');
                }}
              />
              {passwordErrors.confirm_password && (
                <p className="text-xs text-destructive">{passwordErrors.confirm_password}</p>
              )}
            </div>
            <div>
              <Button type="submit" disabled={changingPassword}>
                {changingPassword ? t('profile.changingPassword') : t('profile.changePassword')}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('profile.account')}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="font-medium text-muted-foreground">{t('profile.role')}</dt>
            <dd>{t(ROLE_KEYS[user.role])}</dd>
            <dt className="font-medium text-muted-foreground">{t('profile.organization')}</dt>
            <dd>{orgName ?? '—'}</dd>
            <dt className="font-medium text-muted-foreground">{t('profile.memberSince')}</dt>
            <dd>{new Date(user.created_at).toLocaleDateString(dateLocale)}</dd>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}
