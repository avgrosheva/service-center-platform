'use client';

import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { useRouter } from 'next/navigation';

import { useAuth } from '@/lib/auth';
import type { UserRole } from '@/types/api';

function landingPathForRole(role: UserRole): string {
  return role === 'technician' ? '/jobs' : '/dashboard';
}

/**
 * Client-side route gate mirroring a backend page's `require_role`
 * dependency (dashboard.py's owner/dispatcher-only gate is the first
 * consumer; F5/F7/F8/F15 reuse this for their own role restrictions).
 * This only prevents a disallowed role from briefly seeing — or being
 * confused by — a page whose data fetches would fail anyway; the
 * backend's own 403 remains the real enforcement regardless of this
 * component.
 *
 * Renders nothing (not even a flash of the real content) until `user` is
 * known, then either the children or nothing while the redirect away
 * happens — never a loading spinner for this specific transition, since
 * it should be near-instant off `useAuth()`'s already-resolved state for
 * every navigation except the very first page load of a session.
 */
export function RequireRole({ allow, children }: { allow: UserRole[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user && !allow.includes(user.role)) {
      router.replace(landingPathForRole(user.role));
    }
  }, [loading, user, allow, router]);

  if (loading || !user || !allow.includes(user.role)) {
    return null;
  }

  return <>{children}</>;
}
