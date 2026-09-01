/**
 * Generic authenticated backend proxy (Milestone F2).
 *
 * The one and only bridge between client-side code and the real backend
 * for everything except register/login/logout (which have their own
 * dedicated Route Handlers, since they issue/clear cookies rather than
 * use an existing one). Every `browserApiClient` call from F4 onward
 * flows through here — this is what makes the httpOnly-cookie decision
 * actually work for the whole app, not just the auth screens: a Client
 * Component can never read the cookie itself, so it can never attach a
 * bearer token itself either. It calls this same-origin route instead
 * (cookies ride along automatically on a same-origin fetch), and this
 * route — running server-side, where the cookie IS readable — attaches
 * the real token and forwards the request.
 *
 * Refresh-on-401, precisely: (per the roadmap's own business-logic note
 * — "attempt refresh once, retry the original request, otherwise
 * redirect to login" — and NOT on a timer)
 *   1. Forward the incoming request to the backend with whatever access
 *      token is currently cookied (possibly none, possibly expired).
 *   2. If that comes back anything other than 401, relay it verbatim —
 *      done.
 *   3. On 401: if there's no refresh token cookie either, the session
 *      never existed or is fully over — clear both cookies and relay the
 *      original 401.
 *   4. Otherwise, call the backend's own `/auth/refresh` exactly once.
 *      On success: persist the new access token as a cookie, retry the
 *      ORIGINAL request exactly once with it, and relay whatever THAT
 *      returns (success or otherwise — no second refresh attempt, ever,
 *      even if it 401s again).
 *   5. If the refresh call itself fails (refresh token expired, revoked,
 *      or otherwise invalid): the session is genuinely over. Clear both
 *      cookies and relay a 401 — `browserApiClient`'s `onUnauthorized`
 *      handler (registered by `AuthProvider`) picks this up and redirects
 *      to login.
 *
 * The incoming request body is read into a string exactly once, up
 * front, and that same string is reused for both the first attempt and
 * the possible retry — a Request's body stream can only be consumed
 * once, so building the retry from a second `request.text()` call would
 * silently fail (an empty body) the moment a refresh was actually
 * needed. This was caught by mentally tracing the retry path while
 * writing this file, not by a test catching it after the fact — the
 * scenario (a real 401 needing a real refresh) only shows up in a
 * long-lived session, exactly the case this milestone's own risk
 * assessment flagged as easy to get subtly wrong under time pressure.
 */

import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { cookies } from 'next/headers';

import { ApiError, apiClient } from '@/lib/api-client';
import {
  ACCESS_TOKEN_COOKIE,
  REFRESH_TOKEN_COOKIE,
  accessTokenCookieOptions,
} from '@/lib/auth-cookies';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL;
const BODYLESS_METHODS = new Set(['GET', 'DELETE', 'HEAD']);

async function forwardToBackend(
  method: string,
  search: string,
  path: string[],
  bodyText: string | undefined,
  accessToken: string | undefined,
): Promise<Response> {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'NEXT_PUBLIC_API_BASE_URL is not set' }, { status: 500 });
  }

  const backendUrl = new URL(`/api/v1/${path.join('/')}`, BACKEND_URL);
  backendUrl.search = search;

  const headers: Record<string, string> = {};
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }
  if (bodyText !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  return fetch(backendUrl.toString(), {
    method,
    headers,
    body: bodyText,
    cache: 'no-store',
  });
}

/** Relays a backend Response to the client verbatim — same status, same body, no reshaping. */
async function relay(response: Response): Promise<NextResponse> {
  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const text = await response.text();
  return new NextResponse(text, {
    status: response.status,
    headers: { 'Content-Type': response.headers.get('Content-Type') ?? 'application/json' },
  });
}

async function handler(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  const cookieStore = await cookies();
  const accessToken = cookieStore.get(ACCESS_TOKEN_COOKIE)?.value;

  // Read the body exactly once — see the module docstring for why.
  const bodyText = BODYLESS_METHODS.has(request.method) ? undefined : await request.text();
  const search = request.nextUrl.search;

  const firstAttempt = await forwardToBackend(request.method, search, path, bodyText, accessToken);

  if (firstAttempt.status !== 401) {
    return relay(firstAttempt);
  }

  const refreshToken = cookieStore.get(REFRESH_TOKEN_COOKIE)?.value;
  if (!refreshToken) {
    cookieStore.delete(ACCESS_TOKEN_COOKIE);
    cookieStore.delete(REFRESH_TOKEN_COOKIE);
    return relay(firstAttempt);
  }

  try {
    const refreshed = await apiClient<{ access_token: string; token_type: string }>(
      '/auth/refresh',
      {
        method: 'POST',
        body: { refresh_token: refreshToken },
      },
    );

    cookieStore.set(ACCESS_TOKEN_COOKIE, refreshed.access_token, accessTokenCookieOptions());

    const retried = await forwardToBackend(
      request.method,
      search,
      path,
      bodyText,
      refreshed.access_token,
    );
    return relay(retried);
  } catch (error) {
    cookieStore.delete(ACCESS_TOKEN_COOKIE);
    cookieStore.delete(REFRESH_TOKEN_COOKIE);
    if (error instanceof ApiError) {
      return NextResponse.json({ detail: error.detail }, { status: error.status || 401 });
    }
    return relay(firstAttempt);
  }
}

export { handler as GET, handler as POST, handler as PATCH, handler as PUT, handler as DELETE };
