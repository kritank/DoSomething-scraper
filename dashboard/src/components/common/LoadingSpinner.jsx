import React from 'react';

const sizes = { sm: 'w-4 h-4', md: 'w-7 h-7', lg: 'w-10 h-10' };

export default function LoadingSpinner({ size = 'md', label = 'Loading…', className = '' }) {
  return (
    <span
      role="status"
      aria-label={label}
      className={`inline-block border-2 rounded-full animate-spin ${sizes[size]} ${className}`}
      style={{ borderColor: 'var(--color-border-default)', borderTopColor: 'var(--color-accent)' }}
    />
  );
}

export function PageLoader({ label = 'Loading…' }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 min-h-[60vh]">
      <LoadingSpinner size="lg" label={label} />
      <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{label}</p>
    </div>
  );
}
