import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const MAX_QUERY_HISTORY = 20;

export const ALL_PLATFORMS = ['instagram', 'youtube'];

export const useAppStore = create(
  persist(
    (set) => ({
      apiKey: null,
      setApiKey: (apiKey) => set({ apiKey }),
      clearApiKey: () => set({ apiKey: null }),

      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

      queryHistory: [],
      pushQueryHistory: (sql) =>
        set((s) => ({
          queryHistory: [sql, ...s.queryHistory.filter((q) => q !== sql)].slice(
            0,
            MAX_QUERY_HISTORY,
          ),
        })),

      // Global scope for which platforms' data the app shows -- the master
      // bound every page's own (local, further-narrowing) platform filter
      // is drawn from. Set from the Header; persists across reloads like
      // sidebarCollapsed. Defaults to both -- nothing is hidden until a
      // user deliberately narrows it.
      enabledPlatforms: ALL_PLATFORMS,
      setEnabledPlatforms: (enabledPlatforms) => set({
        // Never allow the global scope to collapse to zero platforms --
        // that would make every page silently show nothing app-wide with
        // no visible cause. A page's own local filter can still narrow to
        // "nothing selected" (that's a valid, visible empty state there).
        enabledPlatforms: enabledPlatforms.length > 0 ? enabledPlatforms : ALL_PLATFORMS,
      }),
    }),
    {
      name: 'viralytics-scraper-dashboard',
      partialize: (s) => ({
        apiKey: s.apiKey,
        sidebarCollapsed: s.sidebarCollapsed,
        queryHistory: s.queryHistory,
        enabledPlatforms: s.enabledPlatforms,
      }),
    },
  ),
);
