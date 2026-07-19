import React from 'react';

// Compact dot summarizing whether the most recent update for one platform
// account succeeded -- for spots (creator profile headers) where a full
// StatusBadge pill would be too wide next to a platform logo/handle, but
// "is this platform actually working" still needs to be visible without
// digging into job history. Labels deliberately avoid the word "scrape" --
// this is user-facing chrome on a public-account view, not an internal
// ops tool.
const STYLES = {
  completed: { color: 'var(--color-success)', label: 'Up to date' },
  failed: { color: 'var(--color-danger)', label: 'Update failed' },
  running: { color: 'var(--color-accent)', label: 'Updating now' },
  queued: { color: 'var(--color-warning)', label: 'Update queued' },
  retry_pending: { color: 'var(--color-warning)', label: 'Update failed -- retrying' },
  cancelled: { color: 'var(--color-text-muted)', label: 'Update cancelled' },
};

export default function ScrapeStatusIndicator({ status, className }) {
  const style = STYLES[status] ?? { color: 'var(--color-text-muted)', label: 'Not yet synced' };
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
