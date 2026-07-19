import React from 'react';

// Compact dot summarizing whether the most recent scrape for one platform
// account succeeded -- for spots (creator profile headers) where a full
// StatusBadge pill would be too wide next to a platform logo/handle, but
// "is this platform actually working" still needs to be visible without
// digging into job history.
const STYLES = {
  completed: { color: 'var(--color-success)', label: 'Last scrape succeeded' },
  failed: { color: 'var(--color-danger)', label: 'Last scrape failed' },
  running: { color: 'var(--color-accent)', label: 'Scrape running now' },
  queued: { color: 'var(--color-warning)', label: 'Scrape queued' },
  retry_pending: { color: 'var(--color-warning)', label: 'Last scrape failed -- retrying' },
  cancelled: { color: 'var(--color-text-muted)', label: 'Last scrape was cancelled' },
};

export default function ScrapeStatusIndicator({ status, className }) {
  const style = STYLES[status] ?? { color: 'var(--color-text-muted)', label: 'Never scraped yet' };
  return (
    <span
      className={className}
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: style.color,
        flexShrink: 0,
      }}
      title={style.label}
      aria-label={style.label}
    />
  );
}
