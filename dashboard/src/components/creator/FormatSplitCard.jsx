import React from 'react';
import InfoTip from '../common/InfoTip';
import Banner from '../common/Banner';
import Skeleton from '../common/Skeleton';
import { formatCompactNumber } from '../../utils/format';

const RANGES = [
  { label: '7D', days: 7 },
  { label: '28D', days: 28 },
  { label: '3M', days: 90 },
  { label: '1Y', days: 365 },
  { label: 'Max', days: 3650 },
];

const FORMAT_COLOR = {
  long_form: 'var(--color-accent)',
  short_form: 'var(--color-chart-2)',
};

export default function FormatSplitCard({ breakdown, loading, days, onDaysChange, longFormLabel, shortFormLabel, infoTip }) {
  const long = breakdown?.formats.find((f) => f.format === 'long_form');
  const short = breakdown?.formats.find((f) => f.format === 'short_form');
  const longShare = long ? Math.round(long.views_share * 100) : 0;
  const shortShare = short ? Math.round(short.views_share * 100) : 0;

  return (
    <div className="card p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            {longFormLabel} vs {shortFormLabel}
          </h3>
          <InfoTip text={infoTip} />
        </div>
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

      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : !breakdown || breakdown.total_views === 0 ? (
        <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)' }}>
          No views recorded for either format in this period yet.
        </p>
      ) : (
        <>
          <div className="flex h-3 w-full rounded-full overflow-hidden" style={{ background: 'var(--color-bg-card-hover)' }}>
            {longShare > 0 && <div style={{ width: `${longShare}%`, background: FORMAT_COLOR.long_form }} />}
            {shortShare > 0 && <div style={{ width: `${shortShare}%`, background: FORMAT_COLOR.short_form }} />}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FormatColumn label={longFormLabel} color={FORMAT_COLOR.long_form} share={longShare} stats={long} />
            <FormatColumn label={shortFormLabel} color={FORMAT_COLOR.short_form} share={shortShare} stats={short} />
          </div>

          {(long?.post_count === 0 || short?.post_count === 0) && (
            <Banner variant="info">
              {long?.post_count === 0 && `No ${longFormLabel.toLowerCase()} in this period.`}
              {short?.post_count === 0 && `No ${shortFormLabel.toLowerCase()} in this period.`}
            </Banner>
          )}
        </>
      )}
    </div>
  );
}

function FormatColumn({ label, color, share, stats }) {
  // avg_views can come back non-zero even when total_views is 0 -- some
  // backend paths fall back to a likes-based average when view counts
  // aren't available for a format, which reads as broken next to a "Views:
  // 0" tile right beside it. Suppress the average in that case instead of
  // showing two numbers that contradict each other.
  const avgViews = stats?.total_views ? stats.avg_views : null;
  return (
    <div className="rounded-xl p-3 flex flex-col gap-1.5" style={{ background: 'var(--color-bg-secondary)' }}>
      <div className="flex items-center gap-1.5">
        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
        <span className="text-xs font-semibold" style={{ color: 'var(--color-text-primary)' }}>{label}</span>
        <span className="text-xs ml-auto" style={{ color: 'var(--color-text-muted)' }}>{share}% of views</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
        <Stat label="Posts" value={stats?.post_count ?? 0} />
        <Stat label="Views" value={formatCompactNumber(stats?.total_views ?? 0)} />
        <Stat label="Avg views" value={avgViews != null ? formatCompactNumber(avgViews) : '—'} />
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="font-semibold" style={{ color: 'var(--color-text-primary)' }}>{value}</div>
      <div style={{ color: 'var(--color-text-muted)' }}>{label}</div>
    </div>
  );
}
