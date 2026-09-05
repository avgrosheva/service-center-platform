'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { LogOut, UserRound } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { browserApiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth';
import { useLocale } from '@/lib/i18n/context';
import type { Organization } from '@/types/api';

function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]![0]}${parts[parts.length - 1]![0]}`.toUpperCase();
}

/**
 * Fetches the org name itself (rather than requiring a parent to pass it
 * in) via `GET /organizations/me` (added post-Milestone-19 specifically
 * for this component — see app/routers/organizations.py). A failed fetch
 * is swallowed, not surfaced: the menu is still fully usable (name, role,
 * logout) without an org name, and a transient hiccup here shouldn't
 * block the rest of the shell.
 */
export function UserMenu({ compact = false }: { compact?: boolean }) {
  const { user, logout } = useAuth();
  const { t } = useLocale();
  const router = useRouter();
  const [orgName, setOrgName] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const org = await browserApiClient<Organization>('/organizations/me');
        if (!cancelled) setOrgName(org.name);
      } catch {
        // Non-fatal — see docstring above.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!user) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            className={compact ? 'h-auto rounded-full p-0' : 'h-auto gap-2 px-2 py-1.5'}
          />
        }
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary font-mono text-xs font-medium tabular-nums text-primary-foreground">
          {user.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- presigned S3/MinIO URL, not a static/local asset next/image can optimize
            <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
          ) : (
            initials(user.full_name)
          )}
        </span>
        <span className={compact ? 'hidden' : 'hidden flex-col items-start text-left sm:flex'}>
          <span className="text-sm font-medium leading-tight">{user.full_name}</span>
          <span className="text-xs leading-tight text-muted-foreground">{orgName ?? ' '}</span>
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuGroup>
          <DropdownMenuLabel>{orgName ?? user.email}</DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push('/profile')}>
          <UserRound className="h-4 w-4" />
          {t('nav.profile')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => void logout()} variant="destructive">
          <LogOut className="h-4 w-4" />
          {t('nav.logOut')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
