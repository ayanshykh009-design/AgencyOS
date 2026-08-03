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
} as const;

export const STORAGE_KEYS = {
  authSession: "agencyos.session",
} as const;
