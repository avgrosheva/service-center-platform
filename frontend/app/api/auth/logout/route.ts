/** Logout Route Handler (Milestone F2) — see lib/session.ts's clearSession for why there's no backend call. */

import { NextResponse } from 'next/server';

import { clearSession } from '@/lib/session';

export async function POST() {
  await clearSession();
  return NextResponse.json({ ok: true });
}
