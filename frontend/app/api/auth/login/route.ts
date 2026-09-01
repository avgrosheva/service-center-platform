/**
 * Login Route Handler (Milestone F2) — mirrors register/route.ts's
 * shape exactly (see that file for the shared reasoning); kept as a
 * separate handler rather than merged with register, since they call
 * different backend endpoints with different request bodies and are
 * conceptually distinct actions, not two branches of one action.
 */

import { NextResponse } from 'next/server';

import { ApiError, apiClient } from '@/lib/api-client';
import { establishSession } from '@/lib/session';
import type { LoginRequest, TokenResponse } from '@/types/api';

export async function POST(request: Request) {
  const body = (await request.json()) as LoginRequest;

  let tokens: TokenResponse;
  try {
    tokens = await apiClient<TokenResponse>('/auth/login', { method: 'POST', body });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ detail: error.detail }, { status: error.status || 500 });
    }
    throw error;
  }

  const user = await establishSession(tokens);
  return NextResponse.json({ user });
}
