/**
 * Role-based nav items (Milestone F3; Schedule added in F14). All hrefs
 * now resolve to real pages. Technician's nav stays deliberately minimal
 * ("their jobs, nothing else") — Schedule is a dispatch-planning tool for
 * owner/dispatcher, not added to the technician menu.
 *
 * `labelKey` (not a literal label) so both nav renderers (the labeled
 * `SidebarNav` list and the icon-only `PillNavIcon` rail) translate it
 * via `useLocale()`'s `t()` at render time — this file itself isn't a
 * component and can't call the hook.
 */

import type { ComponentType } from 'react';
import { CalendarDays, LayoutDashboard, Settings, UserRound, Wrench } from 'lucide-react';

import type { TranslationKey } from '@/lib/i18n/context';
import type { UserRole } from '@/types/api';

export type NavItem = {
  labelKey: TranslationKey;
  href: string;
  icon: ComponentType<{ className?: string }>;
};

const OWNER_DISPATCHER_NAV: NavItem[] = [
  { labelKey: 'nav.dashboard', href: '/dashboard', icon: LayoutDashboard },
  { labelKey: 'nav.jobs', href: '/jobs', icon: Wrench },
  { labelKey: 'nav.customers', href: '/customers', icon: UserRound },
  { labelKey: 'nav.schedule', href: '/schedule', icon: CalendarDays },
  { labelKey: 'nav.settings', href: '/settings', icon: Settings },
];

// "Their jobs, nothing else" — one item, reusing the same /jobs route as
// owner/dispatcher: the backend already scopes a technician's job list to
// their own assigned jobs server-side (Milestone 9's list_jobs), so the
// frontend doesn't need a separate route or client-side filtering, just
// a differently-labeled link into the same page.
const TECHNICIAN_NAV: NavItem[] = [{ labelKey: 'nav.myJobs', href: '/jobs', icon: Wrench }];

export function navItemsForRole(role: UserRole): NavItem[] {
  return role === 'technician' ? TECHNICIAN_NAV : OWNER_DISPATCHER_NAV;
}
