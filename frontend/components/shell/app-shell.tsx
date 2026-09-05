'use client';

import { useState } from 'react';
import type { ComponentType, ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { Menu } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet';
import { navItemsForRole } from '@/components/shell/nav-config';
import { SidebarNav } from '@/components/shell/sidebar-nav';
import { UserMenu } from '@/components/shell/user-menu';
import { LocaleToggle } from '@/components/shell/locale-toggle';
import { useAuth } from '@/lib/auth';
import { useLocale } from '@/lib/i18n/context';
import type { TranslationKey } from '@/lib/i18n/context';
import { cn } from '@/lib/utils';

/**
 * Milestone F3: the nav shell every authenticated page renders inside
 * (wired in via app/(authenticated)/layout.tsx, below the existing F2
 * guard). "Studio Console" (direction v3 — see
 * .impeccable/surfaces/…dashboard-page-tsx.md) started as a
 * dashboard-only experiment and was promoted app-wide once the user
 * confirmed the direction: a floating, icon-only pill rail on desktop,
 * no header bar, full-bleed content. Below `md` the rail becomes a
 * floating rounded hamburger button that opens the same labeled
 * `SidebarNav` list in a `Sheet` drawer — icon-only nav is a
 * desktop-only device; the drawer keeps full discoverability on mobile.
 *
 * `user?.role ?? 'technician'` picks the *narrowest* nav set as the
 * fallback for the brief window between this component mounting and
 * `useAuth()`'s own "am I logged in" fetch resolving — the
 * (authenticated) layout guard already guarantees a session exists by
 * the time this renders, but `user` itself is a client-side fetch, not
 * something available synchronously on mount. Defaulting to the
 * lowest-privilege nav for that brief window is deliberately safer than
 * defaulting to the full owner/dispatcher set.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { t } = useLocale();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const navItems = navItemsForRole(user?.role ?? 'technician');

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="fixed inset-y-4 left-4 z-20 hidden w-16 flex-col items-center rounded-full bg-sidebar py-5 text-sidebar-foreground md:flex">
        <span
          aria-hidden
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 border-sidebar-primary/70"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-sidebar-primary" />
        </span>
        <nav className="mt-6 flex flex-1 flex-col items-center gap-1.5">
          {navItems.map((item) => (
            <PillNavIcon key={item.href} item={item} />
          ))}
        </nav>
      </aside>

      <div className="fixed top-4 right-4 z-20 hidden items-center gap-2 md:flex">
        <LocaleToggle />
        <UserMenu />
      </div>

      <div className="fixed top-4 left-4 z-20 md:hidden">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t('nav.openNavigation')}
          className="rounded-full bg-sidebar text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          onClick={() => setMobileNavOpen(true)}
        >
          <Menu className="h-5 w-5" />
        </Button>
      </div>

      <main className="min-w-0 flex-1 p-4 md:p-6 md:pt-20 md:pl-24">
        <div className="mx-auto flex max-w-6xl items-center justify-end gap-2 pb-2 md:hidden">
          <LocaleToggle />
          <UserMenu />
        </div>
        {children}
      </main>

      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" className="w-64 bg-sidebar text-sidebar-foreground">
          <SheetTitle className="px-4 pt-4">
            <ShopPlate compact />
          </SheetTitle>
          <div className="px-4 pt-2">
            <SidebarNav items={navItems} onNavigate={() => setMobileNavOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

/**
 * The wordmark, shown only in the mobile nav drawer (the desktop pill
 * rail has no room for text — see PillNavIcon's docstring on why that
 * costs nothing for assistive tech).
 */
function ShopPlate({ compact = false }: { compact?: boolean }) {
  const { t } = useLocale();
  return (
    <div className={compact ? 'flex items-center gap-2' : 'mb-6 flex items-center gap-2.5 px-2'}>
      <span
        aria-hidden
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-sidebar-primary/70"
      >
        <span className="h-1.5 w-1.5 rounded-full bg-sidebar-primary" />
      </span>
      <span className="flex flex-col leading-none">
        {/* The product name is a working title (see PRODUCT.md) — kept
            untranslated like any brand name; only the sub-line below is
            UI chrome. */}
        <span className="text-sm font-semibold text-sidebar-foreground">Field Service</span>
        {!compact && (
          <span className="mt-1 text-xs text-sidebar-foreground/50">{t('nav.operations')}</span>
        )}
      </span>
    </div>
  );
}

/**
 * One icon-only stop on the floating pill rail. No visible label (the
 * rail has no room for one) — `title` and `aria-label` carry the same
 * text `SidebarNav`'s labeled variant shows in the mobile drawer, so the
 * icon-only choice costs nothing for keyboard/screen-reader users.
 */
function PillNavIcon({
  item,
}: {
  item: { labelKey: TranslationKey; href: string; icon: NavIcon };
}) {
  const pathname = usePathname();
  const { t } = useLocale();
  const Icon = item.icon;
  const active = pathname === item.href || pathname?.startsWith(`${item.href}/`);
  const label = t(item.labelKey);

  return (
    <a
      href={item.href}
      title={label}
      aria-label={label}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors',
        active
          ? 'bg-sidebar-primary text-sidebar-primary-foreground'
          : 'text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
      )}
    >
      <Icon className="h-4.5 w-4.5" />
    </a>
  );
}

type NavIcon = ComponentType<{ className?: string }>;
