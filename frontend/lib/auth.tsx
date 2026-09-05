'use client';

/**
 * Client-side auth state (Milestone F2): `AuthProvider` + `useAuth()`.
 *
 * `login`/`register`/`logout` call the three dedicated Route Handlers
 * under `app/api/auth/*` directly via `fetch` (not `browserApiClient`,
 * which is hardcoded to the `/api/backend/*` data proxy — these three
 * actions issue or clear cookies, a fundamentally different job from
 * "fetch some backend data with an existing session," so they get their
 * own small local request helper, `postAuthAction`, rather than
 * stretching `browserApiClient`'s contract to cover both).
 *
 * The one-time "am I currently logged in?" check on mount goes through
 * `browserApiClient('/auth/me', { suppressUnauthorizedHandler: true })`
 * — the real backend data proxy, since by that point a session (if any)
 * is just an ordinary authenticated read. `suppressUnauthorizedHandler`
 * matters here specifically: an anonymous visitor's very first page load
 * legitimately 401s this call, and that must not trigger the global
 * redirect-to-login (see api-client.ts's docstring on that option) — it
 * just means `user` stays `null`.
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useRouter } from 'next/navigation';

import { ApiError, browserApiClient, setUnauthorizedHandler } from '@/lib/api-client';
import type { LoginRequest, RegisterRequest, User } from '@/types/api';

type AuthContextValue = {
  user: User | null;
  /** True only during the initial "am I logged in?" check on mount — not re-set true for login/register/logout calls themselves; forms track their own submitting state. */
  loading: boolean;
  login: (data: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  /** Pushes a fresh User (e.g. the response of a profile edit or avatar upload) into shared auth state, so every consumer — the top-right UserMenu included — reflects it immediately without a full reload. */
  updateUser: (user: User) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function postAuthAction<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    let detail = `Request failed with HTTP ${response.status}`;
    try {
      const data: unknown = await response.json();
      if (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string') {
        detail = data.detail;
      }
    } catch {
      // Non-JSON error body — keep the generic message above.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Registered once, for the lifetime of this provider — any
  // `browserApiClient` (or `apiClient`, though that never runs
  // client-side) call anywhere in the app that gets a real 401 funnels
  // through this single redirect, per api-client.ts's own docstring.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      router.push('/login');
    });
    return () => setUnauthorizedHandler(null);
  }, [router]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await browserApiClient<User>('/auth/me', { suppressUnauthorizedHandler: true });
        if (!cancelled) {
          setUser(me);
        }
      } catch {
        if (!cancelled) {
          setUser(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (data: LoginRequest) => {
    const result = await postAuthAction<{ user: User }>('/api/auth/login', data);
    setUser(result.user);
  }, []);

  const register = useCallback(async (data: RegisterRequest) => {
    const result = await postAuthAction<{ user: User }>('/api/auth/register', data);
    setUser(result.user);
  }, []);

  const logout = useCallback(async () => {
    await postAuthAction('/api/auth/logout');
    setUser(null);
    router.push('/login');
  }, [router]);

  const updateUser = useCallback((next: User) => setUser(next), []);

  const value: AuthContextValue = { user, loading, login, register, logout, updateUser };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
