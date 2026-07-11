import React from 'react';

function KPICard({ label, value, icon, color, loading = false }) {
  return (
    <div className="card p-5 flex flex-col gap-3 animate-fade-in">
      <div className="flex items-start justify-between">
        <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
        {icon && (
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: color ? `${color}20` : 'var(--color-accent-dim)', color: color ?? 'var(--color-accent)' }}
          >
            {icon}
          </div>
        )}
      </div>
      {loading ? (
        <div className="h-7 w-20 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
      ) : (
        <p className="text-2xl font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>{value}</p>
      )}
    </div>
  );
}

export default React.memo(KPICard);
