// Initial-render smoke tests for the Lead Conversations panel.
// Follows the repo's component-test convention (auth-ssr.test.tsx): the panel
// is rendered to static markup, so only the honest initial states are
// asserted — loading state, no fabricated conversations or success copy, and
// no content at all before a session exists. Interactive behavior (loading
// results, replying, thread switching) is covered by the conversations
// service tests; full DOM interaction testing is not available in this repo's
// test environment (node-only, no jsdom/testing-library dependency).
import { afterEach, describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { LeadConversationsPanel } from "@/components/leads/lead-conversations-panel";
import { clearSession, setSession } from "@/lib/session";
import type { User } from "@/types";

const OWNER: User = {
  id: "11111111-1111-1111-1111-111111111111",
  organization_id: "22222222-2222-2222-2222-222222222222",
  email: "owner@example.com",
  full_name: "Owner",
  role: "owner",
  is_active: true,
  last_login_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

describe("lead conversations panel — initial render", () => {
  afterEach(() => {
    clearSession();
  });

  it("renders the honest loading state and never fabricates conversations", () => {
    setSession({ accessToken: "access-123", expiresIn: 3600, user: OWNER });

    const html = renderToStaticMarkup(<LeadConversationsPanel leadId="lead-1" />);

    expect(html).toContain("Conversations");
    expect(html).toContain("Loading conversations");
    // No fake thread data or success copy may render before the API answers.
    expect(html).not.toContain("Intro call");
    expect(html).not.toContain("Last message");
  });

  it("renders nothing without an authenticated session", () => {
    clearSession();

    const html = renderToStaticMarkup(<LeadConversationsPanel leadId="lead-1" />);

    expect(html).toBe("");
  });
});
