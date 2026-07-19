import React, { useMemo } from 'react';
import { Layers, Image, Clapperboard, Sparkles } from 'lucide-react';
import InfoTip from '../common/InfoTip';
import Skeleton from '../common/Skeleton';
import PlatformIcon from '../common/PlatformIcon';
import SponsorshipChart from '../charts/SponsorshipChart';
import { platformLabel } from '../../utils/platform';

const RANGES = [
  { label: '28D', days: 28 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
  { label: 'Max', days: 3650 },
];

const ORGANIC_COLOR = '#6366f1';
const SPONSORED_COLOR = '#f59e0b';

// Sample size below which a share-comparison insight gets softened --
// sponsored posts are sparse for most creators, so a 1-2 post bucket
// shouldn't be compared with the same confidence as a larger one.
const MIN_SAMPLE_FOR_CONFIDENT_INSIGHT = 5;

const BUCKETS = [
  { key: 'overall', label: 'Overall', icon: Layers },
  { key: 'long_form', label: 'Long-form', icon: Image },
  { key: 'short_form', label: 'Short-form', icon: Clapperboard },
];

export default function SponsorshipCard({
  breakdown,
  loading,
  days,
  onDaysChange,
  platforms,
  selectedPlatform = 'all',
  onPlatformChange,
}) {
  const showPlatformToggle = platforms && platforms.length > 1;

  const bucketStats = useMemo(() => {
    if (!breakdown) return {};
    const longForm = breakdown.formats.find((f) => f.format === 'long_form');
    const shortForm = breakdown.formats.find((f) => f.format === 'short_form');
    return {
      overall: { organic: breakdown.organic, sponsored: breakdown.sponsored },
      long_form: { organic: longForm?.organic, sponsored: longForm?.sponsored },
      short_form: { organic: shortForm?.organic, sponsored: shortForm?.sponsored },
    };
  }, [breakdown]);

  // Comparing sponsored SHARE (not raw count) between long-form and
  // short-form is the one genuinely strategic read here: it tells a
  // creator which format they actually run partnerships in, which raw
  // counts alone can't (a format with 10x more posts will always have
  // more sponsored posts in absolute terms even with a lower rate).
  const insight = useMemo(() => {
    const shareOf = (bucket) => {
      const total = (bucket?.organic?.post_count ?? 0) + (bucket?.sponsored?.post_count ?? 0);
      return total > 0 ? { share: bucket.sponsored.post_count / total, total } : null;
    };
    const long = shareOf(bucketStats.long_form);
    const short = shareOf(bucketStats.short_form);
    if (!long || !short) return null;
    if (long.total < MIN_SAMPLE_FOR_CONFIDENT_INSIGHT || short.total < MIN_SAMPLE_FOR_CONFIDENT_INSIGHT) return null;
    const diffPoints = Math.round((long.share - short.share) * 100);
    if (Math.abs(diffPoints) < 3) return null;
    const [higherLabel, lowerLabel] = diffPoints > 0 ? ['long-form', 'short-form'] : ['short-form', 'long-form'];
    return { text: `You tag partnerships in ${higherLabel} content ${Math.abs(diffPoints)} percentage points more often than in ${lowerLabel}.` };
  }, [bucketStats]);

  return (
    <div className="card p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Sponsored vs organic
          </h3>
          <InfoTip text="Compares posts officially tagged with the platform's paid-partnership / paid-promotion disclosure against everything else. Creators who run sponsored content without using that disclosure tool show up as organic here, so this undercounts real sponsorships." />
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
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {BUCKETS.map((b) => (
              <BucketCard key={b.key} label={b.label} icon={b.icon} stats={bucketStats[b.key]} />
            ))}
          </div>

          <SponsorshipChart breakdown={breakdown} />

          {insight && (
            <div
              className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
              style={{ background: 'rgba(245, 158, 11, 0.12)', color: '#f59e0b' }}
            >
              <Sparkles className="w-3.5 h-3.5 shrink-0" />
              {insight.text}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function BucketCard({ label, icon: Icon, stats }) {
  const organicCount = stats?.organic?.post_count ?? 0;
  const sponsoredCount = stats?.sponsored?.post_count ?? 0;
  const total = organicCount + sponsoredCount;
  const sponsoredShare = total > 0 ? Math.round((sponsoredCount / total) * 100) : 0;

  return (
    <div
      className="rounded-xl p-3.5 flex flex-col gap-2.5"
      style={{ background: 'var(--color-bg-secondary)' }}
    >
      <div className="flex items-center gap-2">
        <span
          className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: 'color-mix(in srgb, var(--color-accent) 16%, transparent)', color: 'var(--color-accent)' }}
        >
          <Icon className="w-3.5 h-3.5" />
        </span>
        <span className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{label}</span>
        <span
          className="text-xs ml-auto px-1.5 py-0.5 rounded-full font-medium"
          style={{ background: 'rgba(245, 158, 11, 0.14)', color: SPONSORED_COLOR }}
        >
          {sponsoredShare}% sponsored
        </span>
      </div>

      {total > 0 && (
        <div className="flex h-2 w-full rounded-full overflow-hidden" style={{ background: 'var(--color-bg-card-hover)' }}>
          {organicCount > 0 && <div style={{ width: `${(organicCount / total) * 100}%`, background: ORGANIC_COLOR }} />}
          {sponsoredCount > 0 && <div style={{ width: `${(sponsoredCount / total) * 100}%`, background: SPONSORED_COLOR }} />}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
        <Stat label="Organic" value={organicCount} color={ORGANIC_COLOR} />
        <Stat label="Sponsored" value={sponsoredCount} color={SPONSORED_COLOR} />
      </div>
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div>
      <div className="text-base font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>{value}</div>
      <div className="flex items-center gap-1" style={{ color: 'var(--color-text-muted)' }}>
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
        {label}
      </div>
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
