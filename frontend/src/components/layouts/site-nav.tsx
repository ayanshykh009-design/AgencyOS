// Site navigation for the dashboard shell.
// Links are filtered by the user's role using the client RBAC mirror.
"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/hooks/use-auth";
import { ROUTES } from "@/lib/constants";
import { can, type PermissionKey } from "@/lib/permissions";
import type { User } from "@/types";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  permission: PermissionKey;
}

const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "Workspace",
    items: [
      { href: ROUTES.dashboard, label: "Dashboard", permission: "lead_read" },
      { href: ROUTES.leads, label: "Leads", permission: "lead_read" },
      { href: ROUTES.pipeline, label: "Pipeline", permission: "lead_read" },
      { href: ROUTES.tasks, label: "Tasks", permission: "task_read" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: ROUTES.search, label: "Search", permission: "search" },
      { href: ROUTES.ai, label: "AI", permission: "lead_read" },
    ],
  },
  {
    label: "Automation",
    items: [
      { href: ROUTES.workflows, label: "Workflows", permission: "automation_read" },
      { href: ROUTES.triggers, label: "Triggers", permission: "automation_read" },
      { href: ROUTES.executions, label: "Executions", permission: "automation_read" },
      { href: ROUTES.credentials, label: "Credentials", permission: "credential_read" },
    ],
  },
  {
    label: "Manage",
    items: [
      { href: ROUTES.team, label: "Team", permission: "invite_manage" },
      { href: ROUTES.assignment, label: "Assignment", permission: "lead_assign" },
      { href: ROUTES.audit, label: "Audit log", permission: "audit_read" },
    ],
  },
];

function NavLinks({ user, onNavigate }: { user: User; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:gap-6">
      {NAV_GROUPS.map((group) => (
        <div key={group.label} className="lg:contents">
          <span className="hidden px-1 text-xs uppercase tracking-wide text-gray-400 lg:inline-block lg:normal-case">
            {group.label}
          </span>
          {group.items
            .filter((item) => can(user.role, item.permission))
            .map((item) => {
              const active =
                pathname === item.href ||
                (item.href !== ROUTES.dashboard && pathname.startsWith(item.href));
              return (
                <a
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  className={cn(
                    "text-sm hover:text-gray-900",
                    active ? "font-medium text-gray-900" : "text-gray-500"
                  )}
                >
                  {item.label}
                </a>
              );
            })}
        </div>
      ))}
    </div>
  );
}

export function SiteNav() {
  const session = useAuth();
  const [open, setOpen] = useState(false);
  if (!session) return null;
  const user = session.user;
  return (
    <>
      <nav className="hidden items-center gap-6 lg:flex">
        <NavLinks user={user} />
      </nav>
      <div className="relative lg:hidden">
        <button
          type="button"
          className="rounded-md border px-3 py-1.5 text-sm"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          Menu
        </button>
        {open ? (
          <div className="absolute right-0 top-full z-40 mt-2 w-56 rounded-lg border bg-white p-3 shadow-lg">
            <NavLinks user={user} onNavigate={() => setOpen(false)} />
          </div>
        ) : null}
      </div>
    </>
  );
}
