// Shared TypeScript domain types.
// These mirror the backend schemas (app/schemas/) — keep them in sync.

/** An agency user account. */
export interface User {
  id: string;
  email: string;
  fullName: string;
  role: "admin" | "agent" | "client";
}

/** A single outreach campaign. */
export interface Campaign {
  id: string;
  name: string;
  status: "draft" | "active" | "paused" | "completed";
  createdAt: string;
}

/** A lead/prospect being reached out to. */
export interface Prospect {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  company?: string;
  linkedInUrl?: string;
}
