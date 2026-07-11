import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const MAX_QUERY_HISTORY = 20;

export const useAppStore = create(
  persist(
    (set, get) => ({
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
    }),
    {
      name: 'viralytics-scraper-dashboard',
      partialize: (s) => ({
        apiKey: s.apiKey,
        sidebarCollapsed: s.sidebarCollapsed,
        queryHistory: s.queryHistory,
      }),
    },
  ),
);
