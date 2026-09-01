/**
 * Typed HTTP layer for talking to the backend (Milestone F1, extended in
 * F2). Nothing else in the app should call `fetch` against the backend
 * directly — every later milestone's endpoints flow through one of the
 * two functions this module exports. (The one deliberate exception is
 * app/page.tsx's Milestone F0 health check, predating this file — it
 * hits the unversioned `/health` path outside `/api/v1`.)
 *
 * Two entry points, for two contexts that cannot share one code path:
 *
 * - **`apiClient`** — server-side only (Server Components, Route
 *   Handlers, Server Functions). Talks to the real backend at an
 *   absolute URL and takes an explicit `token`, because that's the only
 *   context that can ever legally possess one: Milestone F2's httpOnly
 *   cookies are readable via `next/headers`' `cookies()` there, and
 *   nowhere else.
 * - **`browserApiClient`** — client-side only (Client Components/hooks).
 *   The browser can never read an httpOnly cookie or hold a bearer
 *   token directly — by design, that's the entire point of storing it
 *   httpOnly. So this calls a same-origin Next.js proxy Route Handler
 *   (`app/api/backend/[...path]/route.ts`) instead of the real backend:
 *   the browser's session cookie rides along automatically (same-origin
 *   fetch sends cookies by default, no explicit option needed), and the
 *   proxy — running server-side — reads that cookie, attaches the real
 *   bearer token, forwards to the backend, and relays the response back
 *   verbatim (including a transparent refresh-and-retry on a 401; see
 *   that route's own docstring for the exact mechanics). From this
 *   module's perspective the two functions differ only in how they build
 *   the request URL and whether a `token` option exists at all — there's
 *   nothing for a client component to pass, which is enforced at the
 *   type level (`ClientApiOptions` omits `token` entirely, not just by
 *   convention).
 *
 * Error shape: the backend's Milestone 19 centralized exception handlers
 * guarantee every non-2xx response is `{"detail": "<string>"}` — a
 * single string, never a list — for HTTPExceptions, validation errors,
 * and unhandled exceptions alike. Confirmed empirically against the
 * running backend (register → login → a deliberate 422 and a deliberate
 * 404), not assumed from memory of a "typical" FastAPI error shape
 * (which, before Milestone 19, WOULD have been a list of objects for
 * validation errors — that's no longer true here). The proxy route
 * relays the backend's error bodies through unchanged, so this same
 * shape holds for `browserApiClient` too.
 */

export type ApiErrorKind =
  | 'unauthorized' // 401
  | 'forbidden' // 403
  | 'not_found' // 404
  | 'validation' // 422
  | 'rate_limited' // 429
  | 'server_error' // 5xx
  | 'network_error' // fetch itself failed (backend unreachable, offline, ...)
  | 'unknown';

function classify(status: number): ApiErrorKind {
  switch (status) {
    case 401:
      return 'unauthorized';
    case 403:
      return 'forbidden';
    case 404:
      return 'not_found';
    case 422:
      return 'validation';
    case 429:
      return 'rate_limited';
    default:
      return status >= 500 ? 'server_error' : 'unknown';
  }
}

export class ApiError extends Error {
  /** HTTP status code, or 0 for a network-level failure (no response at all). */
  readonly status: number;
  readonly kind: ApiErrorKind;
  /** The backend's raw `detail` string, or a locally-constructed message for network errors. */
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.kind = status === 0 ? 'network_error' : classify(status);
  }
}

/**
 * Registered once by Milestone F2's `AuthProvider` to centralize "a 401
 * happened somewhere, redirect to login" — every call site funnels
 * through this single hook instead of each page/hook reimplementing the
 * redirect. Takes a plain callback (not wired to `next/navigation`
 * directly) because `AuthProvider` is the one place that both knows the
 * right client-side navigation call and can register this from a
 * `useEffect`.
 */
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

const API_PREFIX = '/api/v1';
const PROXY_PREFIX = '/api/backend';

type SharedOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  /** JSON-serialized as the request body. Omit entirely for a body-less request (GET/DELETE). */
  body?: unknown;
  /** Query-string parameters; `undefined` values are omitted, not sent as "undefined". */
  params?: Record<string, string | number | boolean | undefined>;
  /** Forwarded to `fetch`. Defaults to `'no-store'` — this is a live operational app, not a page that benefits from stale cached API responses. */
  cache?: RequestCache;
  signal?: AbortSignal;
  /**
   * Skip the global `onUnauthorized` callback for this call's 401s,
   * without changing anything else — the error is still thrown normally
   * for the caller to catch. For the one call site (`useAuth()`'s "am I
   * currently logged in?" probe on mount) where a 401 is an expected,
   * routine outcome (an anonymous visitor), not a signal that a live
   * session just died — the global handler firing there would redirect
   * a never-logged-in visitor away from a public page they're already on
   * for no reason.
   */
  suppressUnauthorizedHandler?: boolean;
};

export type ApiClientOptions = SharedOptions & {
  /** Bearer token to attach, if the caller has one. Server-side only — see the module docstring. */
  token?: string | null;
};

/** `browserApiClient`'s options — deliberately has no `token` field: a Client Component can never legally have one to pass. */
export type ClientApiOptions = SharedOptions;

async function extractErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      return body.detail;
    }
  } catch {
    // Response body wasn't JSON (or was empty) — fall through to the generic message below.
  }
  return `Request failed with HTTP ${response.status}`;
}

function applyParams(url: URL, params: SharedOptions['params']): void {
  if (!params) return;
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      url.searchParams.set(key, String(value));
    }
  }
}

/**
 * Shared core: makes one request to a fully-built URL and returns the
 * parsed JSON body, typed as `T` (the caller asserts the shape — there's
 * no runtime validation here, matching the "hand-written types, no
 * codegen" approach documented in types/api.ts).
 *
 * Throws `ApiError` for both non-2xx responses and network-level
 * failures, so callers only ever need to catch one error type regardless
 * of failure mode.
 */
async function performRequest<T>(
  url: string,
  options: SharedOptions & { token?: string | null },
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  if (options.token) {
    headers['Authorization'] = `Bearer ${options.token}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? 'GET',
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      cache: options.cache ?? 'no-store',
      signal: options.signal,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new ApiError(0, `Could not reach the backend: ${message}`);
  }

  if (!response.ok) {
    const detail = await extractErrorDetail(response);
    const apiError = new ApiError(response.status, detail);
    if (apiError.kind === 'unauthorized' && !options.suppressUnauthorizedHandler) {
      onUnauthorized?.();
    }
    throw apiError;
  }

  // DELETE /jobs/{id}/materials/{item_id} (and any other 204 response)
  // has no body — parsing it as JSON would throw.
  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

/** Server-side only — see the module docstring. */
export async function apiClient<T>(path: string, options: ApiClientOptions = {}): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    throw new ApiError(0, 'NEXT_PUBLIC_API_BASE_URL is not set');
  }
  const url = new URL(`${API_PREFIX}${path}`, baseUrl);
  applyParams(url, options.params);
  return performRequest<T>(url.toString(), options);
}

/** Client-side only, via the same-origin auth proxy — see the module docstring. */
export async function browserApiClient<T>(
  path: string,
  options: ClientApiOptions = {},
): Promise<T> {
  // Relative to the current page's origin — this function only ever runs
  // in the browser, where `window` is always available.
  const url = new URL(`${PROXY_PREFIX}${path}`, window.location.origin);
  applyParams(url, options.params);
  return performRequest<T>(url.toString(), options);
}
