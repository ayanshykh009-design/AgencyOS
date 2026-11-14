// Terms of Service (Sheet 2A screen 04).
// Layout-only page: the legal text and claims are owner-supplied, so the
// reading column renders clearly-marked placeholders and a draft notice.
import type { Metadata } from "next";

import { LegalPage } from "@/components/marketing/legal-page";
import { LEGAL_DRAFT_NOTICE, TERMS_SECTIONS } from "@/lib/marketing";

export const metadata: Metadata = {
  title: "Terms of Service · AgencyOS",
  description: "AgencyOS Terms of Service (draft pending owner/legal review).",
};

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      sections={TERMS_SECTIONS}
      draftNotice={LEGAL_DRAFT_NOTICE}
    />
  );
}
