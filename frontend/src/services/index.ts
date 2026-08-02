// Backend integration modules.
// Each domain lives in its own service module here (auth.ts, dashboard.ts,
// leads.ts). Pages and components must route data through these services via
// src/lib/api-client.ts, never raw fetch calls.
export { login, logout, fetchCurrentUser } from "./auth";
export { getDashboardSummary } from "./dashboard";
export { listLeads, getLead } from "./leads";
export { listAITools, runBrain, dispatchDraft, getAISettings, updateAISettings } from "./ai";
export type { LoginInput } from "./auth";
export type { LeadQuery } from "./leads";
export type { BrainRunInput } from "./ai";
