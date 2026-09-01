import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { AuthProvider } from '@/lib/auth';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'Field Service Platform',
  description: 'Operational workspace for field service repair companies.',
};

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        {/* Wraps the whole app (not just the authenticated route group) —
            login/register also use useAuth() for their submit actions,
            and this keeps there being exactly one auth mechanism, not
            two. See lib/auth.tsx's own docstring for the full design. */}
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
