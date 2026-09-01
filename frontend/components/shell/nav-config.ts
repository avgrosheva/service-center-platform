/**
 * Role-based nav items (Milestone F3; Schedule added in F14). All hrefs
 * now resolve to real pages. Technician's nav stays deliberately minimal
 * ("their jobs, nothing else") — Schedule is a dispatch-planning tool for
 * owner/dispatcher, not added to the technician menu.
 */

import type { ComponentType } from 'react';
import { CalendarDays, LayoutDashboard, Settings, UserRound, Wrench } from 'lucide-react';

import type { UserRole } from '@/types/api';

export type NavItem = {
  label: string;
  href: string;
  icon: ComponentType<{ className?: string }>;
};

const OWNER_DISPATCHER_NAV: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { label: 'Jobs', href: '/jobs', icon: Wrench },
  { label: 'Customers', href: '/customers', icon: UserRound },
  { label: 'Schedule', href: '/schedule', icon: CalendarDays },
  { label: 'Settings', href: '/settings', icon: Settings },
];

// "Their jobs, nothing else" — one item, reusing the same /jobs route as
// owner/dispatcher: the backend already scopes a technician's job list to
// their own assigned jobs server-side (Milestone 9's list_jobs), so the
// frontend doesn't need a separate route or client-side filtering, just
// a differently-labeled link into the same page.
const TECHNICIAN_NAV: NavItem[] = [{ label: 'My Jobs', href: '/jobs', icon: Wrench }];

export function navItemsForRole(role: UserRole): NavItem[] {
  return role === 'technician' ? TECHNICIAN_NAV : OWNER_DISPATCHER_NAV;
}
