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
        {/* Padding lives on this inner div, not on the scrolling `main`
            itself -- a `position: sticky` descendant (e.g. CreatorProfile's
            in-page section nav) sticks relative to main's scrollport, and
            if main itself carried the padding, that padding would leave a
            gap above the stuck element instead of scrolling away with the
            rest of the content. */}
        <main className="flex-1 min-w-0 overflow-y-auto">
          <div className="p-6">
            <Outlet />
          </div>
        </main>
      </div>
      <Toaster theme="dark" position="bottom-right" richColors />
    </div>
  );
}
