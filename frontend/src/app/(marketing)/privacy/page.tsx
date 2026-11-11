// Privacy Policy (Sheet 2A screen 05).
// Layout-only page: the legal text and claims are owner-supplied, so the
// reading column renders clearly-marked placeholders and a draft notice.
import type { Metadata } from "next";

import { LegalPage } from "@/components/marketing/legal-page";
import { LEGAL_DRAFT_NOTICE, PRIVACY_SECTIONS } from "@/lib/marketing";

export const metadata: Metadata = {
  title: "Privacy Policy · AgencyOS",
  description: "AgencyOS Privacy Policy (draft pending owner/legal review).",
};

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      sections={PRIVACY_SECTIONS}
      draftNotice={LEGAL_DRAFT_NOTICE}
    />
  );
}
