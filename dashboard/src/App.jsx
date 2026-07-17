import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import ApiKeyGate from './components/common/ApiKeyGate';
import DashboardLayout from './layouts/DashboardLayout';
import Overview from './pages/Overview';
import QueryConsole from './pages/QueryConsole';
import Accounts from './pages/Accounts';
import Influencers from './pages/Influencers';
import CreatorProfile from './pages/CreatorProfile';
import CombinedCreatorProfile from './pages/CombinedCreatorProfile';
import Content from './pages/Content';
import Insights from './pages/Insights';
import Export from './pages/Export';
import CommandPalette from './components/common/CommandPalette';

export default function App() {
  return (
    <BrowserRouter>
      <ApiKeyGate>
        <Routes>
          <Route path="/" element={<DashboardLayout />}>
            <Route index element={<Overview />} />
            <Route path="influencers" element={<Influencers />} />
            <Route path="influencers/:influencerId" element={<CreatorProfile />} />
            <Route path="creators/:creatorId" element={<CombinedCreatorProfile />} />
            <Route path="content" element={<Content />} />
            <Route path="insights" element={<Insights />} />
            <Route path="query" element={<QueryConsole />} />
            <Route path="accounts" element={<Accounts />} />
            <Route path="export" element={<Export />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <CommandPalette />
      </ApiKeyGate>
    </BrowserRouter>
  );
}
