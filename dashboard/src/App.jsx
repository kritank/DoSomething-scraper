import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import ApiKeyGate from './components/common/ApiKeyGate';
import DashboardLayout from './layouts/DashboardLayout';
import Overview from './pages/Overview';
import QueryConsole from './pages/QueryConsole';
import Accounts from './pages/Accounts';

export default function App() {
  return (
    <BrowserRouter>
      <ApiKeyGate>
        <Routes>
          <Route path="/" element={<DashboardLayout />}>
            <Route index element={<Overview />} />
            <Route path="query" element={<QueryConsole />} />
            <Route path="accounts" element={<Accounts />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ApiKeyGate>
    </BrowserRouter>
  );
}
