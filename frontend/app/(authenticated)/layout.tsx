import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { AppShell } from '@/components/shell/app-shell';
import { REFRESH_TOKEN_COOKIE } from '@/lib/auth-cookies';

/**
 * Route-protection guard (Milestone F2) for every page under this route
 * group — `(authenticated)` doesn't appear in the URL, only in the file
 * tree, per Next.js's route-group convention. Milestone F3 added the
 * `AppShell` wrapper (sidebar/topbar) below, kept in this same file
 * rather than a separate mechanism, since both exist to wrap every page
 * in this route group.
 *
 * Deliberately a *presence* check only (does a refresh-token cookie
 * exist at all), not a full validation (no backend call here) — for two
 * reasons:
 *
 * 1. Cost: this guard runs on every single navigation into the
 *    authenticated section. A network round-trip to the backend on every
 *    page load, just to confirm what's about to be confirmed anyway by
 *    the page's own first real data fetch, is pure overhead.
 * 2. Refresh-token presence is genuinely the right question for "is
 *    there a session at all" — it's the long-lived cookie (14 days vs.
 *    the access token's 45 minutes), so a merely-expired-but-refreshable
 *    access token doesn't wrongly bounce someone to the login page.
 *    Actual expiry/refresh of the *access* token is handled transparently
 *    by app/api/backend/[...path]/route.ts on the first real data fetch
 *    the page makes — that's the layer that already has to talk to the
 *    backend regardless, so the refresh logic belongs there once, not
 *    duplicated here as a second implementation that could drift from it.
 *
 * A refresh token that exists but is itself expired/revoked isn't caught
 * here either — that surfaces the moment the page's own data fetch 401s
 * and the proxy's refresh attempt also fails, at which point
 * `AuthProvider`'s `onUnauthorized` handler (registered in lib/auth.tsx)
 * redirects to login from the client side. Two different failure modes,
 * two different (and each individually simple) layers — not one
 * mechanism trying to cover both.
 */
export default async function AuthenticatedLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  if (!cookieStore.has(REFRESH_TOKEN_COOKIE)) {
    redirect('/login');
  }

  return <AppShell>{children}</AppShell>;
}
