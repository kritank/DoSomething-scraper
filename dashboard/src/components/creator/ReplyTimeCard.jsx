import React from 'react';
import InfoTip from '../common/InfoTip';
import Skeleton from '../common/Skeleton';
import PlatformIcon from '../common/PlatformIcon';
import ReplyTimeHeatmap from '../charts/ReplyTimeHeatmap';
import { platformLabel } from '../../utils/platform';

const RANGES = [
  { label: '28D', days: 28 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
];

// Creator comment reply speed, bucketed by time-since-post and crossed
// with format -- built from FeatureStore.time_to_first_creator_reply_s
// (real comment timestamps, already synced daily), no new scraping. All
// the actual numbers (post count, avg reply time, avg comment volume)
// live per-cell in the heatmap's tooltip -- no separate summary row, since
// an "overall average" here reads as a confusing single number without
// the format/time-bucket context that gives it meaning.
export default function ReplyTimeCard({
  heatmap,
  loading,
  days,
  onDaysChange,
  longFormLabel = 'Long-form',
  shortFormLabel = 'Short-form',
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
            Response Insights
          </h3>
          <InfoTip text="How quickly the creator's first reply to a comment lands after posting, bucketed by time-since-post and split by format. Hover a cell for that bucket's post count, average reply time, and average comments per post. Only counts posts with at least one creator reply." />
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
        <ReplyTimeHeatmap
          heatmap={heatmap}
          longFormLabel={longFormLabel}
          shortFormLabel={shortFormLabel}
        />
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
