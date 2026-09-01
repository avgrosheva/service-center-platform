import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { REFRESH_TOKEN_COOKIE } from '@/lib/auth-cookies';
import { LoginForm } from '@/components/auth/login-form';

/**
 * Server Component — checks (cheaply, no backend call) whether a session
 * cookie already exists before rendering the form at all, satisfying
 * this milestone's "visiting login while logged in redirects to
 * dashboard" checklist item. Presence-only, same reasoning as
 * app/(authenticated)/layout.tsx's guard — see that file's docstring.
 */
export default async function LoginPage() {
  const cookieStore = await cookies();
  if (cookieStore.has(REFRESH_TOKEN_COOKIE)) {
    redirect('/dashboard');
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 p-8 dark:bg-black">
      <LoginForm />
    </div>
  );
}
