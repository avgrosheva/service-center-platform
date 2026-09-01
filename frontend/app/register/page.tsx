import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { REFRESH_TOKEN_COOKIE } from '@/lib/auth-cookies';
import { RegisterForm } from '@/components/auth/register-form';

/** Mirrors app/login/page.tsx's guard — see that file for the reasoning. */
export default async function RegisterPage() {
  const cookieStore = await cookies();
  if (cookieStore.has(REFRESH_TOKEN_COOKIE)) {
    redirect('/dashboard');
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 p-8 dark:bg-black">
      <RegisterForm />
    </div>
  );
}
