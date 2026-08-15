// App-wide constants (route paths, storage keys, feature flags).
export const ROUTES = {
  home: "/",
  login: "/login",
  dashboard: "/dashboard",
  leads: "/leads",
  leadDetail: (leadId: string) => `/leads/${leadId}`,
  pipeline: "/pipeline",
  tasks: "/tasks",
  search: "/search",
  audit: "/audit",
  team: "/team",
  assignment: "/assignment",
  ai: "/ai",
  aiSettings: "/ai/settings",
  workflows: "/workflows",
  workflowDetail: (workflowId: string) => `/workflows/${workflowId}`,
  triggers: "/triggers",
  executions: "/executions",
  credentials: "/credentials",
  deliveries: "/deliveries",
  inbox: "/inbox",
  growth: "/growth",
  founder: "/founder",
  founderProposals: "/founder/proposals",
} as const;

export const STORAGE_KEYS = {
  authSession: "agencyos.session",
} as const;

// Permission constants matching backend
export const Permission = {
  AUTOMATION_READ: "automation_read",
  AUTOMATION_MANAGE: "automation_manage",
  AUTOMATION_CONTROL: "automation_control",
  EXECUTION_READ: "execution_read",
  EXECUTION_WRITE: "execution_write",
  EXECUTION_MANAGE: "execution_manage",
} as const;

export type Permission = (typeof Permission)[keyof typeof Permission];
