import React from 'react';
import InfoTip from '../common/InfoTip';
import Skeleton from '../common/Skeleton';
import PlatformIcon from '../common/PlatformIcon';
import PostingCalendarHeatmap from '../charts/PostingCalendarHeatmap';
import PostingTimeHeatmap from '../charts/PostingTimeHeatmap';
import { platformLabel } from '../../utils/platform';

const RANGES = [
  { label: '7D', days: 7 },
  { label: '28D', days: 28 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
];

// Posting-frequency calendar heatmap (GitHub-contributions style -- fixed
// footprint regardless of post volume, so it never reads as "mostly empty"
// the way a bar chart does for a quiet account) plus a weekday x hour
// heatmap for "best time to post." Both are computed purely from
// Post.posted_at (see CreatorStatsService.get_posting_frequency /
// get_posting_time_distribution), so no scrape/backfill was needed.
//
// `platforms` (optional) lists the platform keys with data available (e.g.
// ['youtube', 'instagram']) -- when there's more than one, a segmented
// "All / YouTube / Instagram" control lets the combined creator page split
// the same two charts by platform without a second fetch: the caller
// already has per-platform data in memory and just swaps which slice this
// card renders via onPlatformChange.
export default function PostingFrequencyCard({
  frequencyPoints,
  timeDistribution,
  loading,
  days,
  onDaysChange,
  platforms,
  selectedPlatform = 'all',
  onPlatformChange,
}) {
  const showPlatformToggle = platforms && platforms.length > 1;

  return (
    <div className="card p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Posting frequency
          </h3>
          <InfoTip text="Each square is one day -- darker means more posts that day. The heatmap below shows which day/hour combinations they post in most, in UTC." />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {showPlatformToggle && (
            <div className="flex items-center gap-1 rounded-lg p-0.5" style={{ background: 'var(--color-bg-card-hover)' }}>
              <PlatformToggleButton
                active={selectedPlatform === 'all'}
                onClick={() => onPlatformChange?.('all')}
                label="All"
              />
              {platforms.map((platform) => (
                <PlatformToggleButton
                  key={platform}
                  active={selectedPlatform === platform}
                  onClick={() => onPlatformChange?.(platform)}
                  label={platformLabel(platform)}
                  icon={platform}
                />
              ))}
            </div>
          )}
          <div className="flex items-center gap-1">
            {RANGES.map((r) => (
              <button
                key={r.days}
                onClick={() => onDaysChange(r.days)}
                className="px-2.5 py-1 rounded-lg text-xs font-medium transition-colors"
                style={{
                  background: days === r.days ? 'var(--color-accent-dim)' : 'transparent',
                  color: days === r.days ? 'var(--color-accent)' : 'var(--color-text-muted)',
                }}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <PostingCalendarHeatmap points={frequencyPoints} days={days} />
          <PostingTimeHeatmap distribution={timeDistribution} />
        </div>
      )}
    </div>
  );
}

function PlatformToggleButton({ active, onClick, label, icon }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition-colors"
      style={{
        background: active ? 'var(--color-accent)' : 'transparent',
        color: active ? '#fff' : 'var(--color-text-muted)',
      }}
    >
      {icon && <PlatformIcon platform={icon} className="w-3.5 h-3.5 rounded-[3px]" />}
      {label}
    </button>
  );
}
