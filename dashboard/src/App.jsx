import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import ApiKeyGate from './components/common/ApiKeyGate';
import DashboardLayout from './layouts/DashboardLayout';
import Overview from './pages/Overview';
import { PageLoader } from './components/common/LoadingSpinner';
import CommandPalette from './components/common/CommandPalette';

// Every page other than Overview (the default landing route) is
// lazy-loaded so the initial bundle isn't paying for every page's
// charts/deps up front -- each ships as its own chunk fetched only when
// the user actually opens it, same pattern as the public-site App.jsx.
const QueryConsole = lazy(() => import('./pages/QueryConsole'));
const Accounts = lazy(() => import('./pages/Accounts'));
const Influencers = lazy(() => import('./pages/Influencers'));
const CreatorProfile = lazy(() => import('./pages/CreatorProfile'));
const CombinedCreatorProfile = lazy(() => import('./pages/CombinedCreatorProfile'));
const CategoryProfile = lazy(() => import('./pages/CategoryProfile'));
const Content = lazy(() => import('./pages/Content'));
const Insights = lazy(() => import('./pages/Insights'));
const Export = lazy(() => import('./pages/Export'));

function LazyRoute({ children }) {
  return <Suspense fallback={<PageLoader label="Loading…" />}>{children}</Suspense>;
}

export default function App() {
  return (
    <BrowserRouter>
      <ApiKeyGate>
        <Routes>
          <Route path="/" element={<DashboardLayout />}>
            <Route index element={<Overview />} />
            <Route path="influencers" element={<LazyRoute><Influencers /></LazyRoute>} />
            <Route path="influencers/:influencerId" element={<LazyRoute><CreatorProfile /></LazyRoute>} />
            <Route path="creators/:creatorId" element={<LazyRoute><CombinedCreatorProfile /></LazyRoute>} />
            <Route path="categories/:categoryId" element={<LazyRoute><CategoryProfile /></LazyRoute>} />
            <Route path="content" element={<LazyRoute><Content /></LazyRoute>} />
            <Route path="insights" element={<LazyRoute><Insights /></LazyRoute>} />
            <Route path="query" element={<LazyRoute><QueryConsole /></LazyRoute>} />
            <Route path="accounts" element={<LazyRoute><Accounts /></LazyRoute>} />
            <Route path="export" element={<LazyRoute><Export /></LazyRoute>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <CommandPalette />
      </ApiKeyGate>
    </BrowserRouter>
  );
}
