import React from 'react';
import InfoTip from '../common/InfoTip';
import Skeleton from '../common/Skeleton';
import PlatformIcon from '../common/PlatformIcon';
import EngagementTrendChart from '../charts/EngagementTrendChart';
import { platformLabel } from '../../utils/platform';

const RANGES = [
  { label: '28D', days: 28 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
];

const COMBINED_COLOR = '#8b5cf6';
const PLATFORM_COLOR = { youtube: '#ff0000', instagram: '#d62976' };

export default function EngagementTrendCard({
  points,
  loading,
  days,
  onDaysChange,
  platforms,
  selectedPlatform = 'all',
  onPlatformChange,
}) {
  const showPlatformToggle = platforms && platforms.length > 1;
  const color = selectedPlatform === 'all' ? COMBINED_COLOR : (PLATFORM_COLOR[selectedPlatform] ?? COMBINED_COLOR);

  return (
    <div className="card p-5 flex flex-col gap-4 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Engagement rate trend
          </h3>
          <InfoTip text="(Likes + comments) / current follower count, averaged across posts published each week. Uses the current follower count as the denominator for every post rather than reconstructing historical follower counts, same simplification as the headline engagement rate stat." />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {showPlatformToggle && (
            <div className="flex items-center gap-1 rounded-lg p-0.5" style={{ background: 'var(--color-bg-card-hover)' }}>
              <PlatformToggleButton active={selectedPlatform === 'all'} onClick={() => onPlatformChange?.('all')} label="All" />
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

      {loading ? <Skeleton className="h-60 w-full" /> : <EngagementTrendChart points={points} color={color} />}
    </div>
  );
}

function PlatformToggleButton({ active, onClick, label, icon }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition-colors"
      style={{ background: active ? 'var(--color-accent)' : 'transparent', color: active ? '#fff' : 'var(--color-text-muted)' }}
    >
      {icon && <PlatformIcon platform={icon} className="w-3.5 h-3.5 rounded-[3px]" />}
      {label}
    </button>
  );
}
