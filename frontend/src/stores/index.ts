// Global client state (Zustand stores).
// Holds cross-page state: auth session, current campaign, UI preferences.
// Do NOT put server data here when a component query suffices.

// Example store shape:
// import { create } from "zustand";
// export const useAuthStore = create<AuthState>((set) => ({
//   user: null,
//   setUser: (user) => set({ user }),
// }));
export {};
