// Dashboard shell: shared chrome (header + nav) around authenticated routes.
// Business logic must live in src/services/, not in layouts.

export default function DashboardLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-14 items-center border-b px-6">
        <span className="font-semibold">AgencyOS</span>
        <nav className="ml-8 flex gap-6 text-sm text-muted-foreground">
          <a href="/dashboard">Dashboard</a>
          <a href="/dashboard/campaigns">Campaigns</a>
          <a href="/dashboard/prospects">Prospects</a>
        </nav>
      </header>
      <main className="flex-1 p-8">{children}</main>
    </div>
  );
}
