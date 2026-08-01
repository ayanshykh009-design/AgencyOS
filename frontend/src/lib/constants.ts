// App-wide constants (route paths, storage keys, feature flags).
export const ROUTES = {
  home: "/",
  login: "/login",
  dashboard: "/dashboard",
} as const;

export const STORAGE_KEYS = {
  authSession: "agencyos.session",
} as const;
