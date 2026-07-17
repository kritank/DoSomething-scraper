import React, { useState } from 'react';
import { Info, AlertTriangle, Sparkles, X } from 'lucide-react';
import { cn } from '../../utils/cn';

const VARIANTS = {
  info: { bg: 'var(--color-accent-dim)', fg: 'var(--color-accent)', Icon: Info },
  warning: { bg: 'var(--color-warning-muted)', fg: 'var(--color-warning)', Icon: AlertTriangle },
  estimate: { bg: 'var(--color-accent-muted)', fg: 'var(--color-accent)', Icon: Sparkles },
};

// Inline callout bar for page/section-level disclaimers (e.g. "these
// figures are estimates"). Not a toast -- stays in the page flow so it's
// visible without a transient popup timing out.
export default function Banner({ variant = 'info', children, dismissible = false, className }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const { bg, fg, Icon } = VARIANTS[variant] ?? VARIANTS.info;

  return (
    <div
      className={cn('flex items-start gap-2.5 rounded-xl px-4 py-3 text-sm animate-fade-in', className)}
      style={{ background: bg, color: fg }}
    >
      <Icon className="w-4 h-4 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">{children}</div>
      {dismissible && (
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Dismiss"
          className="shrink-0 opacity-70 hover:opacity-100 transition-opacity"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
