'use client';

import { useState } from 'react';
import type { ReactNode } from 'react';
import { Menu } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet';
import { navItemsForRole } from '@/components/shell/nav-config';
import { SidebarNav } from '@/components/shell/sidebar-nav';
import { UserMenu } from '@/components/shell/user-menu';
import { useAuth } from '@/lib/auth';

/**
 * Milestone F3: the nav shell every authenticated page renders inside
 * (wired in via app/(authenticated)/layout.tsx, below the existing F2
 * guard). Desktop gets a persistent left sidebar; below the `md`
 * breakpoint the sidebar collapses into a `Sheet` drawer opened from a
 * topbar hamburger button — both presentations render the exact same
 * `SidebarNav` with the exact same `items` list, so they can never drift.
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
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const navItems = navItemsForRole(user?.role ?? 'technician');

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 border-r border-zinc-200 p-4 dark:border-zinc-800 md:block">
        <div className="mb-6 px-2 text-lg font-semibold">Field Service</div>
        <SidebarNav items={navItems} />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-zinc-200 px-4 dark:border-zinc-800">
          <div className="flex items-center gap-2 md:hidden">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Open navigation"
              onClick={() => setMobileNavOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </Button>
            <span className="text-base font-semibold">Field Service</span>
          </div>
          <div className="ml-auto">
            <UserMenu />
          </div>
        </header>

        <main className="min-w-0 flex-1 p-4">{children}</main>
      </div>

      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" className="w-64">
          <SheetTitle className="px-4 pt-4">Field Service</SheetTitle>
          <div className="px-4">
            <SidebarNav items={navItems} onNavigate={() => setMobileNavOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
