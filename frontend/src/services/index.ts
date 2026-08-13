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
export {
  listWorkflows,
  listActiveWorkflows,
  getWorkflow,
  createWorkflow,
  updateWorkflow,
  activateWorkflow,
  pauseWorkflow,
  archiveWorkflow,
  deleteWorkflow,
} from "./workflows";
export {
  listWorkflowTriggers,
  getWorkflowTrigger,
  createWorkflowTrigger,
  updateWorkflowTrigger,
  enableWorkflowTrigger,
  disableWorkflowTrigger,
  deleteWorkflowTrigger,
} from "./workflow-triggers";
export {
  listWorkflowExecutions,
  getWorkflowExecution,
  queueWorkflowExecution,
  startWorkflowExecution,
  retryWorkflowExecution,
  cancelWorkflowExecution,
} from "./workflow-executions";
export { listWorkflowEvents, publishWorkflowEvent } from "./workflow-events";
export {
  listCredentials,
  getCredential,
  createCredential,
  updateCredential,
  deleteCredential,
} from "./credentials";
export {
  listDeliveries,
  getDelivery,
  createDelivery,
  listDeliveryEvents,
  retryDelivery,
  cancelDelivery,
} from "./deliveries";
export {
  listNotifications,
  getNotification,
  getUnreadCount,
  getNotificationTypeCounts,
  markNotificationRead,
  setNotificationRead,
} from "./notifications";
export {
  listAnalyses,
  getAnalysis,
  runAnalysis,
  runAllAnalyses,
  listRecommendations,
  recommendationCounts,
  updateRecommendation,
  listScenarios,
  getScenario,
  createScenario,
  deleteScenario,
  getHealthWeights,
  upsertHealthWeights,
  runForecast,
} from "./growth";
export type { LoginInput } from "./auth";
export type { LeadQuery, DuplicateQuery } from "./leads";
export type { BrainRunInput } from "./ai";
export type { TaskQuery } from "./tasks";
export type { AuditQuery } from "./audit";
export type { ExportFormat, ExportQuery } from "./exports";
export type { WorkflowQuery } from "./workflows";
export type { WorkflowTriggerQuery } from "./workflow-triggers";
export type { WorkflowExecutionQuery } from "./workflow-executions";
export type { WorkflowEventQuery } from "./workflow-events";
export type { CredentialQuery } from "./credentials";
export type { DeliveryQuery } from "./deliveries";
export type { NotificationQuery, UnreadCount, NotificationTypeCounts } from "./notifications";
export type { GrowthAnalysisQuery, GrowthRecommendationQuery, GrowthScenarioQuery } from "./growth";
