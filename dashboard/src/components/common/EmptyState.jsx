import React from 'react';
import { SearchX } from 'lucide-react';

export default function EmptyState({
  title = 'No data found',
  message = 'Nothing to show yet.',
  icon,
  action,
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center"
        style={{ background: 'var(--color-accent-dim)' }}
      >
        {icon ?? <SearchX className="w-7 h-7" style={{ color: 'var(--color-accent)' }} />}
      </div>
      <h4 className="font-semibold" style={{ color: 'var(--color-text-primary)' }}>{title}</h4>
      <p className="text-sm max-w-xs" style={{ color: 'var(--color-text-muted)' }}>{message}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
