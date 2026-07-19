import React, { useMemo, useState } from 'react';
import { Image, Clapperboard, Sparkles } from 'lucide-react';
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

const FORMAT_ICON = {
  long_form: Image,
  short_form: Clapperboard,
};

export default function FormatSplitCard({ breakdown, loading, days, onDaysChange, longFormLabel, shortFormLabel, infoTip }) {
  const [hovered, setHovered] = useState(null); // 'long_form' | 'short_form' | null

  const long = breakdown?.formats.find((f) => f.format === 'long_form');
  const short = breakdown?.formats.find((f) => f.format === 'short_form');
  const longShare = long ? Math.round(long.views_share * 100) : 0;
  const shortShare = short ? Math.round(short.views_share * 100) : 0;

  // Auto-generated headline comparing the two formats -- only when both
  // have a real (non-suppressed, see FormatColumn's avgViews rule) average
  // to compare, otherwise there's nothing honest to say.
  const insight = useMemo(() => {
    const longAvg = long?.avg_views ?? null;
    const shortAvg = short?.avg_views ?? null;
    if (!longAvg || !shortAvg) return null;
    const [winner, winnerLabel, loserLabel, winnerAvg, loserAvg] =
      shortAvg >= longAvg
        ? ['short_form', shortFormLabel, longFormLabel, shortAvg, longAvg]
        : ['long_form', longFormLabel, shortFormLabel, longAvg, shortAvg];
    const pct = loserAvg > 0 ? Math.round(((winnerAvg - loserAvg) / loserAvg) * 100) : 0;
    if (pct < 5) return null; // too close to call an "insight"
    return { format: winner, text: `${winnerLabel} average ${pct}% more views per post than ${loserLabel.toLowerCase()}.` };
  }, [long, short, longFormLabel, shortFormLabel]);

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
          <div
            className="flex h-3 w-full rounded-full overflow-hidden"
            style={{ background: 'var(--color-bg-card-hover)' }}
            onMouseLeave={() => setHovered(null)}
          >
            {longShare > 0 && (
              <div
                onMouseEnter={() => setHovered('long_form')}
                className="transition-opacity duration-150"
                style={{
                  width: `${longShare}%`,
                  background: FORMAT_COLOR.long_form,
                  opacity: hovered && hovered !== 'long_form' ? 0.35 : 1,
                }}
              />
            )}
            {shortShare > 0 && (
              <div
                onMouseEnter={() => setHovered('short_form')}
                className="transition-opacity duration-150"
                style={{
                  width: `${shortShare}%`,
                  background: FORMAT_COLOR.short_form,
                  opacity: hovered && hovered !== 'short_form' ? 0.35 : 1,
                }}
              />
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FormatColumn
              format="long_form"
              label={longFormLabel}
              color={FORMAT_COLOR.long_form}
              icon={FORMAT_ICON.long_form}
              share={longShare}
              stats={long}
              hovered={hovered}
              onHover={setHovered}
            />
            <FormatColumn
              format="short_form"
              label={shortFormLabel}
              color={FORMAT_COLOR.short_form}
              icon={FORMAT_ICON.short_form}
              share={shortShare}
              stats={short}
              hovered={hovered}
              onHover={setHovered}
            />
          </div>

          {insight && (
            <div
              className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
              style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)' }}
            >
              <Sparkles className="w-3.5 h-3.5 shrink-0" />
              {insight.text}
            </div>
          )}

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

function FormatColumn({ format, label, color, icon: Icon, share, stats, hovered, onHover }) {
  // The backend already falls back to a likes-derived average when a
  // format has no usable view counts (e.g. Instagram photo/carousel posts),
  // and returns null only when NO post in the bucket has any usable metric
  // at all -- so avg_views is already null-safe and must not be re-gated on
  // total_views here (that incorrectly blanked every likes-derived average).
  const avgViews = stats?.avg_views ?? null;
  const dimmed = hovered && hovered !== format;
  return (
    <div
      onMouseEnter={() => onHover(format)}
      onMouseLeave={() => onHover(null)}
      className="card-hover rounded-xl p-3.5 flex flex-col gap-2.5 transition-opacity duration-150"
      style={{
        background: 'var(--color-bg-secondary)',
        border: `1px solid ${hovered === format ? color : 'transparent'}`,
        opacity: dimmed ? 0.6 : 1,
      }}
    >
      <div className="flex items-center gap-2">
        <span
          className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color }}
        >
          <Icon className="w-3.5 h-3.5" />
        </span>
        <span className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{label}</span>
        <span
          className="text-xs ml-auto px-1.5 py-0.5 rounded-full font-medium"
          style={{ background: `color-mix(in srgb, ${color} 14%, transparent)`, color }}
        >
          {share}% of views
        </span>
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
      <div className="text-base font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>{value}</div>
      <div style={{ color: 'var(--color-text-muted)' }}>{label}</div>
    </div>
  );
}
