import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { REFRESH_TOKEN_COOKIE } from '@/lib/auth-cookies';
import { LoginForm } from '@/components/auth/login-form';
import { LocaleToggle } from '@/components/shell/locale-toggle';

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
    <div className="relative flex min-h-screen items-center justify-center bg-background p-8">
      <div className="absolute top-4 right-4">
        <LocaleToggle />
      </div>
      <LoginForm />
    </div>
  );
}
