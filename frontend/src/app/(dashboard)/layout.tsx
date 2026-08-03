// Dashboard shell: shared chrome (header + nav) around authenticated routes.
// Business logic must live in src/services/, not in layouts.

import { SignOutButton } from "@/components/auth/sign-out-button";
import { SiteNav } from "@/components/layouts/site-nav";
import { ROUTES } from "@/lib/constants";

export default function DashboardLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-14 items-center justify-between border-b px-4 lg:px-6">
        <div className="flex items-center gap-4">
          <a href={ROUTES.dashboard} className="font-semibold">
            AgencyOS
          </a>
          <SiteNav />
        </div>
        <SignOutButton />
      </header>
      <main className="flex-1 p-4 lg:p-8">{children}</main>
    </div>
  );
}
