"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Boxes,
  Gauge,
  LayoutDashboard,
  LineChart,
  Route,
  Sparkles,
  Users,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { CommandPalette } from "@/components/command-palette";
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

interface NavSection {
  label: string;
  icon: LucideIcon;
  links: NavLink[];
}

// Kept in sync with backend/app/core/security.py's require_role(...) on
// each router -- a link only renders for roles that can actually open
// the page, so the nav never dangles a route the API will 403. Grouped
// into the eight control-center sections named in the v2 spec; every
// route from the flat v1 nav is still reachable, just organized by
// workflow instead of listed flat.
const SECTIONS: NavSection[] = [
  {
    label: "Overview",
    icon: LayoutDashboard,
    links: [
      { href: "/dashboard", label: "Executive", roles: [EXECUTIVE, ADMINISTRATOR] },
      {
        href: "/supply-chain",
        label: "Supply Chain Map",
        roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR],
      },
      { href: "/data-quality", label: "Data Quality", roles: [OPERATIONS_ANALYST, ADMINISTRATOR] },
    ],
  },
  {
    label: "Operations",
    icon: Workflow,
    links: [
      { href: "/sales", label: "Sales", roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR] },
      {
        href: "/procurement",
        label: "Procurement",
        roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR],
      },
      {
        href: "/operational",
        label: "Fleet & Warehouse",
        roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR],
      },
    ],
  },
  {
    label: "Forecasting",
    icon: LineChart,
    links: [{ href: "/forecast", label: "Demand Forecast", roles: [SUPPLY_PLANNER, ADMINISTRATOR] }],
  },
  {
    label: "Inventory",
    icon: Boxes,
    links: [
      { href: "/inventory", label: "Inventory", roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR] },
      {
        href: "/inventory-policy",
        label: "Inventory Policy",
        roles: [SUPPLY_PLANNER, ADMINISTRATOR],
      },
    ],
  },
  {
    label: "Suppliers",
    icon: Users,
    links: [
      { href: "/supplier", label: "Supplier", roles: [OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR] },
      { href: "/supplier-risk", label: "Supplier Risk", roles: [SUPPLY_PLANNER, ADMINISTRATOR] },
    ],
  },
  {
    label: "Scenarios",
    icon: Gauge,
    links: [{ href: "/scenarios", label: "Scenario Simulation", roles: [SUPPLY_PLANNER, ADMINISTRATOR] }],
  },
  {
    label: "Optimization",
    icon: Route,
    links: [
      { href: "/service-level", label: "Service Level", roles: [SUPPLY_PLANNER, ADMINISTRATOR] },
      {
        href: "/route-cost-optimization",
        label: "Route & Cost",
        roles: [SUPPLY_PLANNER, ADMINISTRATOR],
      },
    ],
  },
  {
    label: "Copilot",
    icon: Sparkles,
    links: [
      {
        href: "/copilot",
        label: "Analytics Copilot",
        roles: [EXECUTIVE, SUPPLY_PLANNER, ADMINISTRATOR],
      },
    ],
  },
];

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { role, setRole } = useRole();
  const [paletteOpen, setPaletteOpen] = useState(false);

  const visibleSections = useMemo(
    () =>
      SECTIONS.map((section) => ({
        ...section,
        links: section.links.filter((link) => link.roles.includes(role)),
      })).filter((section) => section.links.length > 0),
    [role],
  );

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const allLinks = useMemo(() => visibleSections.flatMap((s) => s.links), [visibleSections]);

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-hairline bg-surface">
        <Link
          href="/dashboard"
          className="flex items-center gap-2 border-b border-hairline px-5 py-5"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-xs font-bold text-white">
            A
          </div>
          <span className="text-sm font-semibold tracking-tight text-ink-primary">ATLAS</span>
        </Link>

        <button
          onClick={() => setPaletteOpen(true)}
          className="mx-4 mt-4 flex items-center justify-between rounded-md border border-hairline bg-surface-inset px-3 py-2 text-left text-xs text-ink-muted transition-colors hover:border-hairline-strong hover:text-ink-secondary"
        >
          <span>Jump to…</span>
          <kbd className="rounded border border-hairline bg-surface px-1.5 py-0.5 font-mono text-2xs">
            ⌘K
          </kbd>
        </button>

        <nav className="mt-2 flex-1 overflow-y-auto px-3 py-3">
          {visibleSections.map((section) => (
            <div key={section.label} className="mb-4">
              <div className="mb-1 flex items-center gap-2 px-2 py-1 text-2xs font-medium uppercase tracking-wide text-ink-muted">
                <section.icon className="h-3.5 w-3.5" strokeWidth={2} />
                {section.label}
              </div>
              <div className="flex flex-col gap-0.5">
                {section.links.map((link) => {
                  const active = pathname === link.href;
                  return (
                    <Link
                      key={link.href}
                      href={link.href}
                      className={cn(
                        "rounded-md px-2.5 py-1.5 text-sm font-medium text-ink-secondary transition-colors hover:bg-surface-2 hover:text-ink-primary",
                        active && "bg-accent-subtle text-accent hover:bg-accent-subtle",
                      )}
                    >
                      {link.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-hairline p-4">
          <label className="flex flex-col gap-1.5 text-2xs text-ink-muted">
            Viewing as
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as AtlasRole)}
              className="rounded-md border border-hairline bg-surface-inset px-2 py-1.5 text-sm text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {ALL_ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </aside>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        links={allLinks}
        onNavigate={(href) => router.push(href)}
      />
    </>
  );
}
