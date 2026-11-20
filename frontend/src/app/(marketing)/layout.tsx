// Public marketing shell (Sheet 2A): dark-first layout with the public
// header, centered content area and public footer. Used by the five
// Batch 1 marketing routes; the authenticated shells are unchanged.
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";

export default function MarketingLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-screen flex-col bg-obsidian text-off-white">
      <PublicHeader />
      <main className="flex-1">{children}</main>
      <PublicFooter />
    </div>
  );
}
