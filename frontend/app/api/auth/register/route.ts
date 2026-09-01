/**
 * Register Route Handler (Milestone F2) — the one place `POST
 * /auth/register` is called with no token, since none exists yet. Calls
 * the real backend directly via `apiClient`, then issues the httpOnly
 * session cookies and returns the created user in one round trip.
 */

import { NextResponse } from 'next/server';

import { ApiError, apiClient } from '@/lib/api-client';
import { establishSession } from '@/lib/session';
import type { RegisterRequest, TokenResponse } from '@/types/api';

export async function POST(request: Request) {
  const body = (await request.json()) as RegisterRequest;

  let tokens: TokenResponse;
  try {
    tokens = await apiClient<TokenResponse>('/auth/register', { method: 'POST', body });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ detail: error.detail }, { status: error.status || 500 });
    }
    throw error;
  }

  const user = await establishSession(tokens);
  return NextResponse.json({ user }, { status: 201 });
}
