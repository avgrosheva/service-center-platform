/**
 * Shared httpOnly-cookie constants and options (Milestone F2).
 *
 * Server-only module (reads/writes cookies via `next/headers`, which is
 * only available in Server Components, Route Handlers, and Server
 * Functions) — imported only by the auth Route Handlers and the
 * `(authenticated)` layout guard, never by client code.
 *
 * `fsp_` prefix (matching the backend's own internal shorthand — its
 * Postgres user is literally named `fsp`) just to avoid any conceivable
 * collision with a future third-party script's generically-named cookie;
 * not a security measure on its own.
 */

export const ACCESS_TOKEN_COOKIE = 'fsp_access_token';
export const REFRESH_TOKEN_COOKIE = 'fsp_refresh_token';

// Matches the backend's own defaults (app/config.py:
// jwt_access_token_expire_minutes=45, jwt_refresh_token_expire_days=14).
// The cookie's maxAge is a courtesy only — actual validity is enforced by
// the JWT's own `exp` claim, checked server-side on every backend call —
// but setting it to roughly match avoids the browser holding onto a
// cookie for a token that's already long dead, and avoids the refresh
// cookie expiring "early" relative to what the backend would still
// accept. If those backend defaults ever change, update these to match.
const ACCESS_TOKEN_MAX_AGE_SECONDS = 45 * 60;
const REFRESH_TOKEN_MAX_AGE_SECONDS = 14 * 24 * 60 * 60;

/**
 * Shared options for both cookies, everything except `maxAge` (which
 * differs per token and is applied by the caller).
 *
 * - `httpOnly: true` — the frozen F2 decision; never readable from
 *   client-side JS, the whole point of this storage strategy.
 * - `secure` only in production — local dev runs over plain
 *   `http://localhost`, where a `Secure` cookie would silently never be
 *   sent at all, breaking every request.
 * - `sameSite: 'lax'` — sent on top-level cross-site navigations (e.g.
 *   following a link into the app) but withheld from cross-site
 *   POST/fetch requests, which covers the common CSRF vector for a
 *   cookie-authenticated app without a dedicated CSRF token. This is an
 *   internal operational tool for small businesses (per the Product
 *   Definition), not a public consumer app; revisit with an explicit
 *   CSRF token if that ever changes.
 * - `path: '/'` — needed everywhere the auth Route Handlers and the
 *   proxy route live, which is effectively the whole app.
 */
function baseCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
  };
}

export function accessTokenCookieOptions() {
  return { ...baseCookieOptions(), maxAge: ACCESS_TOKEN_MAX_AGE_SECONDS };
}

export function refreshTokenCookieOptions() {
  return { ...baseCookieOptions(), maxAge: REFRESH_TOKEN_MAX_AGE_SECONDS };
}
