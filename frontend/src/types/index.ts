// Shared TypeScript domain types.
// These mirror the backend schemas (app/schemas/) - keep them in sync.

export type UserRole = "owner" | "admin" | "member" | "viewer";

export type LeadStatus =
  "new" | "researching" | "contacted" | "meeting_booked" | "proposal_sent" | "won" | "lost";

/** An agency user account (backend UserRead schema). */
export interface User {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Token pair returned after login/refresh (backend AuthResponse). */
export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

/** A lead/prospect being reached out to (backend LeadRead). */
export interface Lead {
  id: string;
  organization_id: string;
  lead_source_id: string | null;
  owner_user_id: string | null;
  email_normalized: string | null;
  phone_normalized: string | null;
  website_domain: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  first_name: string | null;
  last_name: string | null;
  company: string | null;
  position: string | null;
  location: string | null;
  linkedin_url: string | null;
  email: string | null;
  phone: string | null;
  whatsapp: string | null;
  website: string | null;
  notes: string | null;
  status: LeadStatus;
  score: number;
}

/** A single business audit-trail entry (backend ActivityLogRead). */
export interface ActivityLogEntry {
  id: string;
  organization_id: string;
  user_id: string | null;
  lead_id: string | null;
  event_type: string;
  entity_type: string | null;
  entity_id: string | null;
  description: string | null;
  metadata: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
}

/** Lead counts by lifecycle status plus the total (backend DashboardLeadCounts). */
export interface DashboardLeadCounts {
  new: number;
  researching: number;
  contacted: number;
  meeting_booked: number;
  proposal_sent: number;
  won: number;
  lost: number;
  total: number;
}

/** Top-level dashboard snapshot (backend DashboardSummary). */
export interface DashboardSummary {
  leads: DashboardLeadCounts;
  users: { total: number; active: number };
  conversations: { open: number };
  outreach: { outstanding: number };
  imports: { active: number };
  activity: { recent: ActivityLogEntry[] };
  usage: { spend_last_30_days_usd: number };
}

/** Paginated list envelope used by every list endpoint (backend Page). */
export interface Page<T> {
  items: T[];
  total: number;
}

/** Standardized error envelope (backend ErrorResponse). */
export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}
