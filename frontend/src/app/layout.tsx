import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

// Global document metadata. Override per-page with `export const metadata`.
export const metadata: Metadata = {
  title: "AgencyOS",
  description: "AI Outreach Agency Operating System",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
