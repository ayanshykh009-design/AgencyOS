// Backend integration modules.
// Each domain lives in its own service module here (auth.ts, dashboard.ts,
// leads.ts). Pages and components must route data through these services via
// src/lib/api-client.ts, never raw fetch calls.
export { login, logout, fetchCurrentUser } from "./auth";
export { getDashboardSummary } from "./dashboard";
export { listLeads, getLead, createLead, updateLead, deleteLead, checkDuplicates } from "./leads";
export { listAITools, runBrain, dispatchDraft, getAISettings, updateAISettings } from "./ai";
export {
  listStages,
  createStage,
  updateStage,
  deleteStage,
  reorderStages,
  listCloseReasons,
  createCloseReason,
  deleteCloseReason,
  getBoard,
  moveLead,
} from "./pipeline";
export {
  listTasks,
  listTasksDueForReminder,
  getTask,
  createTask,
  updateTask,
  completeTask,
  deleteTask,
} from "./tasks";
export { listNotesByLead, getNote, createNote, updateNote, deleteNote } from "./notes";
export { globalSearch } from "./search";
export { buildExportUrl, downloadExport } from "./exports";
export { listAuditLogs, getEntityAudit } from "./audit";
export { createInvite, listInvites, revokeInvite, lookupInvite, acceptInvite } from "./teams";
export { listUsers, getUser, updateUser } from "./users";
export {
  getAssignmentRule,
  upsertAssignmentRule,
  assignUnassignedLeads,
  assignLead,
} from "./assignment";
export type { LoginInput } from "./auth";
export type { LeadQuery, DuplicateQuery } from "./leads";
export type { BrainRunInput } from "./ai";
export type { TaskQuery } from "./tasks";
export type { AuditQuery } from "./audit";
export type { ExportFormat, ExportQuery } from "./exports";
