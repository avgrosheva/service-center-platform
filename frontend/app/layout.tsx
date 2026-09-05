import type { Metadata } from 'next';
import { Golos_Text, JetBrains_Mono, Oswald } from 'next/font/google';
import './globals.css';
import { AuthProvider } from '@/lib/auth';
import { LocaleProvider } from '@/lib/i18n/context';

// Cyrillic-native body face (Russia/CIS is the product's target market per
// PRODUCT.md) rather than a Latin-only training-data default.
const golosText = Golos_Text({
  variable: '--font-golos-text',
  subsets: ['latin', 'cyrillic'],
});

// Tabular figures only: job counts, currency, dates — never a "technical"
// costume applied to prose.
const jetbrainsMono = JetBrains_Mono({
  variable: '--font-jetbrains-mono',
  subsets: ['latin', 'cyrillic'],
});

// Tracked caps for the stamped headers and status-band labels — the
// service-tag world's one display voice.
const oswald = Oswald({
  variable: '--font-oswald',
  subsets: ['latin', 'cyrillic'],
});

export const metadata: Metadata = {
  title: 'Field Service Platform',
  description: 'Operational workspace for field service repair companies.',
};

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    <html
      lang="en"
      className={`${golosText.variable} ${jetbrainsMono.variable} ${oswald.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* Wraps the whole app (not just the authenticated route group) —
            login/register also use useAuth() for their submit actions,
            and this keeps there being exactly one auth mechanism, not
            two. See lib/auth.tsx's own docstring for the full design. */}
        <LocaleProvider>
          <AuthProvider>{children}</AuthProvider>
        </LocaleProvider>
      </body>
    </html>
  );
}
