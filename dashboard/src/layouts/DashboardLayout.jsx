import React from 'react';
import { Outlet } from 'react-router-dom';
import { Toaster } from 'sonner';
import Sidebar from '../components/common/Sidebar';
import Header from '../components/common/Header';

export default function DashboardLayout() {
  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--color-bg-primary)' }}>
      <Sidebar />
      {/* min-w-0 on both the column and main: flex children default to
          min-width:auto, so without this a wide table/card inside refuses
          to shrink and blows out the whole page into a horizontal scroll
          instead of scrolling within its own container. */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header />
        <main className="flex-1 min-w-0 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
      <Toaster theme="dark" position="bottom-right" richColors />
    </div>
  );
}
