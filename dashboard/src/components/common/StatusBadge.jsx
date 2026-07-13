import React from 'react';
import { cn } from '../../utils/cn';

// Covers both ScrapeJob.status and InstagramAccount.status -- the two enums
// don't overlap, so one badge component/palette works for both.
const STYLES = {
  completed:          { bg: 'var(--color-success-muted)', fg: 'var(--color-success)' },
  active:             { bg: 'var(--color-success-muted)', fg: 'var(--color-success)' },
  running:            { bg: 'var(--color-accent-muted)',  fg: 'var(--color-accent)' },
  in_use:             { bg: 'var(--color-accent-muted)',  fg: 'var(--color-accent)' },
  queued:             { bg: 'var(--color-warning-muted)', fg: 'var(--color-warning)' },
  retry_pending:      { bg: 'var(--color-warning-muted)', fg: 'var(--color-warning)' },
  failed:             { bg: 'var(--color-danger-muted)',  fg: 'var(--color-danger)' },
  cancelled:          { bg: 'rgba(255,255,255,0.06)',     fg: 'var(--color-text-muted)' },
  checkpoint_required:{ bg: 'var(--color-danger-muted)',  fg: 'var(--color-danger)' },
  disabled:           { bg: 'rgba(255,255,255,0.06)',     fg: 'var(--color-text-muted)' },
  never_scraped:      { bg: 'rgba(255,255,255,0.06)',     fg: 'var(--color-text-muted)' },
  pending_login:      { bg: 'var(--color-accent-muted)',  fg: 'var(--color-accent)' },
  login_failed:       { bg: 'var(--color-danger-muted)',  fg: 'var(--color-danger)' },
};

export default function StatusBadge({ status, className }) {
  const style = STYLES[status] ?? { bg: 'rgba(255,255,255,0.06)', fg: 'var(--color-text-muted)' };
  return (
    <span
      className={cn(
        'inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap',
        className,
      )}
      style={{ background: style.bg, color: style.fg }}
    >
      {(status ?? 'never_scraped').replaceAll('_', ' ')}
    </span>
  );
}
