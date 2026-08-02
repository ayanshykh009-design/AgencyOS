import type { Metadata } from "next";
import "./globals.css";

// Global document metadata. Override per-page with `export const metadata`.
export const metadata: Metadata = {
  title: "AgencyOS",
  description: "AI Outreach Agency Operating System",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
