"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useRole } from "@/lib/role-context";
import {
  ADMINISTRATOR,
  ALL_ROLES,
  EXECUTIVE,
  OPERATIONS_ANALYST,
  SUPPLY_PLANNER,
  type AtlasRole,
} from "@/lib/roles";
import { cn } from "@/lib/utils";

interface NavLink {
  href: string;
  label: string;
  roles: AtlasRole[];
}

// Kept in sync with backend/app/core/security.py's require_role(...) call
// on each router — a link only renders for roles that can actually open
// the page, so the nav never dangles a route the API will 403.
const LINKS: NavLink[] = [
  { href: "/dashboard", label: "Executive", roles: [EXECUTIVE, ADMINISTRATOR] },
  { href: "/sales", label: "Sales", roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR] },
  { href: "/inventory", label: "Inventory", roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR] },
  { href: "/procurement", label: "Procurement", roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR] },
  { href: "/supplier", label: "Supplier", roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR] },
  { href: "/operational", label: "Operational", roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR] },
  { href: "/data-quality", label: "Data Quality", roles: [OPERATIONS_ANALYST, ADMINISTRATOR] },
  { href: "/forecast", label: "Planning", roles: [SUPPLY_PLANNER, ADMINISTRATOR] },
  { href: "/supplier-risk", label: "Supplier Risk", roles: [SUPPLY_PLANNER, ADMINISTRATOR] },
  { href: "/service-level", label: "Service Level", roles: [SUPPLY_PLANNER, ADMINISTRATOR] },
  { href: "/inventory-policy", label: "Inventory Policy", roles: [SUPPLY_PLANNER, ADMINISTRATOR] },
];

export function Nav() {
  const pathname = usePathname();
  const { role, setRole } = useRole();
  const visibleLinks = LINKS.filter((link) => link.roles.includes(role));

  return (
    <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-6">
          <span className="text-lg font-semibold tracking-tight">ATLAS</span>
          <nav className="flex gap-1">
            {visibleLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
                  pathname === link.href && "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-white"
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
          Viewing as
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as AtlasRole)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
          >
            {ALL_ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </header>
  );
}
