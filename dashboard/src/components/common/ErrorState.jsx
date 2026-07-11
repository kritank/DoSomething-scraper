import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import Button from './Button';

export default function ErrorState({ title = 'Something went wrong', description, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
      <div
        className="w-12 h-12 rounded-2xl flex items-center justify-center"
        style={{ background: 'var(--color-danger-muted)' }}
      >
        <AlertTriangle className="w-6 h-6" style={{ color: 'var(--color-danger)' }} />
      </div>
      <div className="space-y-1">
        <p className="font-semibold text-sm" style={{ color: 'var(--color-text-primary)' }}>{title}</p>
        {description && (
          <p className="text-xs max-w-xs" style={{ color: 'var(--color-text-muted)' }}>{description}</p>
        )}
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          <RefreshCw className="w-3.5 h-3.5" />
          Try Again
        </Button>
      )}
    </div>
  );
}
