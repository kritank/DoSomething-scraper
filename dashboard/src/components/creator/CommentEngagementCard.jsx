import React from 'react';
import { Layers, Image, Clapperboard, MessageCircle } from 'lucide-react';
import InfoTip from '../common/InfoTip';
import Skeleton from '../common/Skeleton';
import PlatformIcon from '../common/PlatformIcon';
import { formatPercent } from '../../utils/format';
import { platformLabel } from '../../utils/platform';

const RANGES = [
  { label: '28D', days: 28 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
];

const BUCKETS = [
  { key: 'overall', label: 'Overall', icon: Layers },
  { key: 'long_form', label: 'Long-form', icon: Image },
  { key: 'short_form', label: 'Short-form', icon: Clapperboard },
];

export default function CommentEngagementCard({
  engagement,
  loading,
  days,
  onDaysChange,
  platforms,
  selectedPlatform = 'all',
  onPlatformChange,
}) {
  const showPlatformToggle = platforms && platforms.length > 1;
  const stats = {
    overall: engagement?.overall,
    long_form: engagement?.formats?.find((f) => f.format === 'long_form'),
    short_form: engagement?.formats?.find((f) => f.format === 'short_form'),
  };

  return (
    <div className="card p-5 flex flex-col gap-4 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Comment engagement depth
          </h3>
          <InfoTip text="Audience-quality signals from scraped comments: how often the creator replies, what share of commenters are platform-verified, and average thread/reply depth. Only covers posts that have had comments scraped, not the full post history." />
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

      {loading ? (
        <Skeleton className="h-32 w-full" />
      ) : !engagement || engagement.overall.comment_count === 0 ? (
        <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)' }}>
          No scraped comments for posts in this period yet.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {BUCKETS.map((b) => (
              <BucketCard key={b.key} label={b.label} icon={b.icon} stats={stats[b.key]} />
            ))}
          </div>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            Based on {engagement.overall.comment_count.toLocaleString()} comments across {engagement.posts_with_comments} post{engagement.posts_with_comments === 1 ? '' : 's'} with comment data.
          </p>
        </>
      )}
    </div>
  );
}

function BucketCard({ label, icon: Icon, stats }) {
  return (
    <div className="rounded-xl p-3.5 flex flex-col gap-2.5" style={{ background: 'var(--color-bg-secondary)' }}>
      <div className="flex items-center gap-2">
        <span
          className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: 'color-mix(in srgb, var(--color-accent) 16%, transparent)', color: 'var(--color-accent)' }}
        >
          <Icon className="w-3.5 h-3.5" />
        </span>
        <span className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{label}</span>
        <span className="text-xs ml-auto flex items-center gap-1" style={{ color: 'var(--color-text-muted)' }}>
          <MessageCircle className="w-3 h-3" />
          {stats?.comment_count ?? 0}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
        <Stat label="Creator reply rate" value={formatPercent(stats?.creator_reply_rate)} />
        <Stat label="Verified commenters" value={formatPercent(stats?.verified_commenter_rate)} />
        <Stat label="Avg thread depth" value={stats?.avg_child_comment_count?.toFixed(2) ?? '—'} />
        <Stat label="Avg likes/comment" value={stats?.avg_likes_per_comment?.toFixed(2) ?? '—'} />
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="text-sm font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>{value}</div>
      <div style={{ color: 'var(--color-text-muted)' }}>{label}</div>
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
