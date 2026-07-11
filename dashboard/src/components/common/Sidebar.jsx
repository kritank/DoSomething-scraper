import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, TerminalSquare, Users, UserPlus, ChevronLeft, ChevronRight, Radio } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/influencers', label: 'Influencers', icon: UserPlus },
  { to: '/query', label: 'Query Console', icon: TerminalSquare },
  { to: '/accounts', label: 'Accounts', icon: Users },
];

export default function Sidebar() {
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);

  return (
    <aside
      className="relative flex flex-col h-full transition-all duration-300 ease-in-out shrink-0"
      style={{
        width: collapsed ? '64px' : '220px',
        background: 'var(--color-bg-secondary)',
        borderRight: '1px solid var(--color-border-subtle)',
      }}
    >
      <div
        className="flex items-center gap-2.5 px-4 py-5"
        style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
      >
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)' }}
        >
          <Radio className="w-4.5 h-4.5" />
        </div>
        {!collapsed && (
          <span
            className="font-bold text-base whitespace-nowrap animate-fade-in"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Scraper Ops
          </span>
        )}
      </div>

      <nav className="flex-1 px-2 py-4 space-y-1 overflow-hidden">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            title={collapsed ? label : undefined}
            className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all"
            style={({ isActive }) => ({
              background: isActive ? 'var(--color-accent-muted)' : 'transparent',
              color: isActive ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              border: isActive ? '1px solid rgba(99,102,241,0.25)' : '1px solid transparent',
            })}
          >
            <Icon className="w-4.5 h-4.5 shrink-0" />
            {!collapsed && <span className="whitespace-nowrap animate-fade-in">{label}</span>}
          </NavLink>
        ))}
      </nav>

      <button
        onClick={toggleSidebar}
        className="absolute -right-3 top-7 w-6 h-6 rounded-full flex items-center justify-center z-10 transition-all hover:scale-110"
        style={{
          background: 'var(--color-bg-card)',
          border: '1px solid var(--color-border-default)',
          color: 'var(--color-text-muted)',
          boxShadow: 'var(--shadow-card)',
        }}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
      </button>
    </aside>
  );
}
