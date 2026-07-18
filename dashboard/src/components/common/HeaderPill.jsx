import React from 'react';

// Small rounded badge for the profile-header metadata row (video count,
// account age, country, "Updated ..."), matching vidiq's row of pills
// under a channel's name/handle.
export default function HeaderPill({ icon: Icon, children }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
      style={{ background: 'var(--color-bg-card-hover)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border-subtle)' }}
    >
      {Icon && <Icon className="w-3 h-3" style={{ color: 'var(--color-text-muted)' }} />}
      {children}
    </span>
  );
}
