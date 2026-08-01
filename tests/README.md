# Tests (cross-service)

Cross-service and end-to-end test suites that span more than one layer or
service. Backend unit/integration/API tests live in `backend/tests/` instead;
component tests live with the frontend.

| Path    | Purpose                                              |
| ------- | ---------------------------------------------------- |
| `e2e/`  | End-to-end flows (frontend → backend → database).    |

Suggested tools (add as adopted):

- **Playwright** for browser E2E (`tests/e2e/`).
- **Contract tests** for the frontend↔backend API surface.

Keep E2E tests stable and few — they are slow and flaky by nature.
