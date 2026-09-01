/**
 * Server-only session helpers (Milestone F2), shared by the register and
 * login Route Handlers. Not used by the generic backend proxy — that
 * route reads/writes the access-token cookie directly, since its
 * refresh-and-retry flow only ever needs to update one cookie at a time.
 */

import { cookies } from 'next/headers';

import { apiClient } from '@/lib/api-client';
import {
  ACCESS_TOKEN_COOKIE,
  REFRESH_TOKEN_COOKIE,
  accessTokenCookieOptions,
  refreshTokenCookieOptions,
} from '@/lib/auth-cookies';
import type { TokenResponse, User } from '@/types/api';

/**
 * Given a fresh TokenResponse from the backend (register or login), sets
 * both httpOnly cookies and fetches the corresponding user profile — so
 * the calling Route Handler can return `{user}` in the same round trip,
 * saving the browser a second `/auth/me` call immediately after every
 * successful register/login.
 */
export async function establishSession(tokens: TokenResponse): Promise<User> {
  const cookieStore = await cookies();
  cookieStore.set(ACCESS_TOKEN_COOKIE, tokens.access_token, accessTokenCookieOptions());
  cookieStore.set(REFRESH_TOKEN_COOKIE, tokens.refresh_token, refreshTokenCookieOptions());

  return apiClient<User>('/auth/me', { token: tokens.access_token });
}

/**
 * Clears both cookies. No backend call — JWTs are stateless and the
 * backend has no logout/revoke endpoint (confirmed from
 * app/routers/auth.py: only register/login/refresh/me exist), so
 * "logging out" purely means the browser forgets its session cookies.
 */
export async function clearSession(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(ACCESS_TOKEN_COOKIE);
  cookieStore.delete(REFRESH_TOKEN_COOKIE);
}
