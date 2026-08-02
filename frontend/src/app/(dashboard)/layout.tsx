// Dashboard shell: shared chrome (header + nav) around authenticated routes.
// Business logic must live in src/services/, not in layouts.

import { SignOutButton } from "@/components/auth/sign-out-button";
import { ROUTES } from "@/lib/constants";

export default function DashboardLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-14 items-center justify-between border-b px-6">
        <div className="flex items-center">
          <span className="font-semibold">AgencyOS</span>
          <nav className="ml-8 flex gap-6 text-sm text-gray-500">
            <a className="font-medium text-gray-900" href={ROUTES.dashboard}>
              Dashboard
            </a>
            <a className="hover:text-gray-900" href={ROUTES.ai}>
              AI
            </a>
          </nav>
        </div>
        <SignOutButton />
      </header>
      <main className="flex-1 p-8">{children}</main>
    </div>
  );
}
