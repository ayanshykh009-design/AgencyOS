// Shared TypeScript domain types.
// These mirror the backend schemas (app/schemas/) - keep them in sync.

export type UserRole = "owner" | "admin" | "manager" | "member" | "sales_agent" | "viewer";

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
  stage_id: string | null;
  close_reason_id: string | null;
  deal_value: number | null;
  won_at: string | null;
  lost_at: string | null;
}

/** Fields a client can set when creating a lead (backend LeadCreate). */
export interface LeadCreateInput {
  first_name?: string;
  last_name?: string;
  company?: string;
  position?: string;
  location?: string;
  linkedin_url?: string;
  email?: string;
  phone?: string;
  whatsapp?: string;
  website?: string;
  notes?: string;
  status?: LeadStatus;
  score?: number;
  lead_source_id?: string;
  owner_user_id?: string;
  stage_id?: string;
  deal_value?: number;
}

/** Partial lead update (backend LeadUpdate). */
export interface LeadUpdateInput {
  first_name?: string | null;
  last_name?: string | null;
  company?: string | null;
  position?: string | null;
  location?: string | null;
  linkedin_url?: string | null;
  email?: string | null;
  phone?: string | null;
  whatsapp?: string | null;
  website?: string | null;
  notes?: string | null;
  status?: LeadStatus;
  score?: number;
  lead_source_id?: string | null;
  owner_user_id?: string | null;
  stage_id?: string | null;
  close_reason_id?: string | null;
  deal_value?: number | null;
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

/** Audit entry with resolved actor metadata (backend ActivityLogRead extras). */
export interface AuditLogEntry extends ActivityLogEntry {
  actor_user_id: string | null;
  actor_name: string | null;
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

/** Task workload snapshot (backend DashboardTasks). */
export interface DashboardTasks {
  open: number;
  overdue: number;
  due_today: number;
  completed_30d: number;
}

/** Deal-flow snapshot (backend DashboardPipeline). */
export interface DashboardPipeline {
  won_deals: number;
  open_deals: number;
  won_revenue: number;
  unassigned_leads: number;
}

/** Top-level dashboard snapshot (backend DashboardSummary). */
export interface DashboardSummary {
  leads: DashboardLeadCounts;
  users: { total: number; active: number };
  conversations: { open: number };
  outreach: { outstanding: number };
  imports: { active: number };
  tasks: DashboardTasks;
  pipeline: DashboardPipeline;
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

/** Static description of an AI-callable tool (backend ToolManifestEntry). */
export interface ToolManifestEntry {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

/** A tool call the brain executed (backend ToolCallRead). */
export interface ToolCallRead {
  name: string;
  arguments: Record<string, unknown>;
}

/** Outcome of a single tool execution (backend ToolResultRead). */
export interface ToolResultRead {
  ok: boolean;
  error?: string | null;
  text: string;
}

/** Result of an AI brain run (backend BrainRunResponse). */
export interface BrainRunResponse {
  success: boolean;
  response?: string | null;
  error?: string | null;
  steps_taken: number;
  tool_calls: ToolCallRead[];
  tool_results: ToolResultRead[];
}

export type OutreachChannel = "email" | "linkedin";

/** Result of an n8n dispatch (backend DispatchResponse). */
export interface DispatchResponse {
  workflow: string;
  status: number;
  data: Record<string, unknown>;
}

/** Effective per-org AI configuration (backend OrganizationAISettingsRead). */
export interface OrganizationAISettings {
  provider: string;
  model: string;
  overridden: boolean;
}

// ---------------------------------------------------------------------------
// Phase 4: Pipeline management
// ---------------------------------------------------------------------------

export type StageLifecycle = "open" | "won" | "lost";

/** A pipeline Kanban column (backend PipelineStageRead). */
export interface PipelineStage {
  id: string;
  organization_id: string;
  name: string;
  lifecycle: StageLifecycle;
  position: number;
  is_default: boolean;
  lead_count: number;
  created_at: string;
  updated_at: string;
}

export interface PipelineStageCreateInput {
  name: string;
  lifecycle?: StageLifecycle;
  position?: number;
}

export interface PipelineStageUpdateInput {
  name?: string;
  position?: number;
}

/** A win/loss close reason (backend CloseReasonRead). */
export interface CloseReason {
  id: string;
  organization_id: string;
  lifecycle: StageLifecycle;
  name: string;
  is_default: boolean;
  created_at: string;
}

export interface CloseReasonCreateInput {
  name: string;
  lifecycle: StageLifecycle;
}

/** A Kanban board column with its lead cards (backend PipelineStageWithLeads). */
export interface PipelineBoardColumn {
  stage: PipelineStage;
  leads: Lead[];
}

export interface LeadStageMoveInput {
  stage_id: string;
  close_reason_id?: string;
}

// ---------------------------------------------------------------------------
// Phase 4: Tasks
// ---------------------------------------------------------------------------

export type TaskStatus = "todo" | "in_progress" | "completed" | "cancelled";
export type TaskPriority = "low" | "medium" | "high" | "urgent";
export type RecurrenceFrequency = "daily" | "weekly" | "monthly";

/** A task (backend TaskRead). */
export interface Task {
  id: string;
  organization_id: string;
  lead_id: string | null;
  assignee_user_id: string | null;
  created_by_user_id: string | null;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_at: string | null;
  reminder_at: string | null;
  completed_at: string | null;
  recurrence_frequency: RecurrenceFrequency | null;
  recurrence_interval: number | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreateInput {
  title: string;
  description?: string;
  lead_id?: string;
  assignee_user_id?: string;
  due_at?: string;
  reminder_at?: string;
  priority?: TaskPriority;
  recurrence_frequency?: RecurrenceFrequency;
  recurrence_interval?: number;
}

export interface TaskUpdateInput {
  title?: string;
  description?: string | null;
  lead_id?: string | null;
  assignee_user_id?: string | null;
  due_at?: string | null;
  reminder_at?: string | null;
  priority?: TaskPriority;
  status?: TaskStatus;
  recurrence_frequency?: RecurrenceFrequency | null;
  recurrence_interval?: number | null;
}

/** Response from the complete endpoint with recurrence metadata. */
export interface TaskCompleteResponse extends Task {
  metadata?: { recurred?: boolean };
}

// ---------------------------------------------------------------------------
// Phase 4: Notes
// ---------------------------------------------------------------------------

/** A lead note (backend NoteRead). */
export interface Note {
  id: string;
  organization_id: string;
  lead_id: string;
  author_user_id: string | null;
  body: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface NoteCreateInput {
  lead_id: string;
  body: string;
  pinned?: boolean;
}

export interface NoteUpdateInput {
  body?: string;
  pinned?: boolean;
}

// ---------------------------------------------------------------------------
// Phase 4: Advanced search
// ---------------------------------------------------------------------------

/** Unified search result counts (backend SearchCounts). */
export interface SearchCounts {
  leads: number;
  tasks: number;
  notes: number;
  total: number;
}

/** Unified search results (backend SearchResponse). */
export interface SearchResponse {
  query: string;
  leads: Lead[];
  tasks: Task[];
  notes: Note[];
  counts: SearchCounts;
}

// ---------------------------------------------------------------------------
// Phase 4: Audit logs
// ---------------------------------------------------------------------------

// AuditLogEntry is defined above (extends ActivityLogEntry).

// ---------------------------------------------------------------------------
// Phase 4: Team management / RBAC
// ---------------------------------------------------------------------------

export type InviteStatus = "pending" | "accepted" | "revoked" | "expired";

/** A team invitation (backend TeamInviteRead). */
export interface TeamInvite {
  id: string;
  organization_id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  status: InviteStatus;
  invited_by_user_id: string | null;
  expires_at: string;
  accepted_at: string | null;
  accepted_user_id: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Invite creation result including the one-time URL (backend response). */
export interface TeamInviteCreateResponse extends TeamInvite {
  invite_url: string;
}

export interface TeamInviteCreateInput {
  email: string;
  full_name?: string;
  role?: UserRole;
}

// ---------------------------------------------------------------------------
// Phase 4: Lead assignment
// ---------------------------------------------------------------------------

export type AssignmentStrategy = "manual" | "round_robin" | "rules";

/** The org's assignment rule (backend AssignmentRuleRead). */
export interface AssignmentRule {
  id: string;
  organization_id: string;
  name: string;
  strategy: AssignmentStrategy;
  enabled: boolean;
  target_user_ids: string[];
  conditions: Record<string, unknown>;
  last_assigned_index: number;
  created_at: string;
  updated_at: string;
}

export interface AssignmentRuleWriteInput {
  name: string;
  strategy: AssignmentStrategy;
  enabled: boolean;
  target_user_ids: string[];
}
