import React from 'react';
import { ResponsiveContainer, ComposedChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceDot } from 'recharts';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';
import { formatCompactNumber, formatUsdRange } from '../../utils/format';

const METRIC_LABELS = {
  followers: 'Followers',
  total_views: 'Total views',
  posts: 'Posts',
  earnings: 'Estimated earnings',
};

const EVENT_COLORS = {
  top_post: 'var(--color-success)',
  milestone: 'var(--color-accent)',
};
const EVENT_TYPE_LABELS = {
  top_post: 'Standout post',
  milestone: 'Follower milestone',
};

function CustomTooltip({ active, label, payload, metric, isEarnings, clustersByDate }) {
  if (!active || !label) return null;
  const cluster = clustersByDate.get(label);

  let seriesLine = null;
  if (isEarnings) {
    const range = payload?.find((p) => p.dataKey === 'value_range')?.value;
    if (range) seriesLine = `${METRIC_LABELS.earnings}: ${formatUsdRange(range[0], range[1])}`;
  } else {
    const value = payload?.find((p) => p.dataKey === 'value')?.value;
    if (value !== undefined) seriesLine = `${METRIC_LABELS[metric] ?? metric}: ${formatCompactNumber(value)}`;
  }

  return (
    <div
      className="px-3 py-2 rounded-lg text-xs shadow-lg max-w-[260px]"
      style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-default)' }}
    >
      <div className="font-semibold mb-1" style={{ color: 'var(--color-text-primary)' }}>
        {format(parseISO(label), 'MMM d, yyyy')}
      </div>
      {seriesLine && <div style={{ color: 'var(--color-text-secondary)' }}>{seriesLine}</div>}
      {cluster && cluster.items.map((e, i) => (
        <div key={i} className="mt-2 pt-2" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
          <div className="flex items-center gap-1.5 font-medium" style={{ color: EVENT_COLORS[e.type] ?? 'var(--color-text-primary)' }}>
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: EVENT_COLORS[e.type] ?? 'var(--color-text-muted)' }} />
            {EVENT_TYPE_LABELS[e.type] ?? e.type}
            {/* Events snap to the nearest chart point (see nearestPointDate
                above), which can be days or weeks off from when the event
                actually happened when snapshots are sparse. Show the
                event's own date whenever it doesn't match the header's
                axis date, so the tooltip doesn't imply the event happened
                on a day it didn't. */}
            {e.date !== label && (
              <span className="ml-auto font-normal shrink-0" style={{ color: 'var(--color-text-muted)' }}>
                {format(parseISO(e.date), 'MMM d')}
              </span>
            )}
          </div>
          <div style={{ color: 'var(--color-text-primary)' }}>{e.label}</div>
        </div>
      ))}
    </div>
  );
}

// Cumulative growth chart -- an Area for normal metrics (followers/views/
// posts), or a low/high band for the derived "earnings" metric, which has
// no single value. Key events (standout posts, follower milestones) are
// plotted as colored dots on top.
export default function GrowthChart({ points, metric, color = 'var(--color-accent)', events = [], onEventClick }) {
  const isEarnings = metric === 'earnings';
  // Same [min, max]-array recharts idiom as PerformanceChart's
  // duration_range / QueueDepthChart's main_range -- a single Area fed a
  // two-element array per point renders the band between them.
  const chartData = isEarnings
    ? (points ?? []).map((p) => ({ ...p, value_range: [p.value_low, p.value_high] }))
    : points;

  if (!points || points.length === 0) {
    return (
      <EmptyState
        title="Not enough history yet"
        message={isEarnings
          ? 'Earnings estimates need at least two days of view-count history to show a daily figure.'
          : 'Growth charts need at least a couple of days of snapshots to plot.'}
      />
    );
  }

  // Key events are snapped to the NEAREST chart point, not matched by
  // exact date: an event's date is a post's publish date or a milestone-
  // crossing day, which will almost never land exactly on a snapshot day
  // (snapshots are daily at best, and can have gaps) -- an exact-match
  // lookup silently drops nearly every event. The x position must also be
  // one of the chart's actual category values (this XAxis is a category
  // axis keyed on `date`, not a continuous time scale), or ReferenceDot
  // can't place it at all.
  const pointDates = points.map((p) => p.date);
  const nearestPointDate = (targetDate) => {
    const targetMs = new Date(targetDate).getTime();
    let nearest = pointDates[0];
    let smallestDiffMs = Infinity;
    for (const d of pointDates) {
      const diffMs = Math.abs(new Date(d).getTime() - targetMs);
      if (diffMs < smallestDiffMs) {
        smallestDiffMs = diffMs;
        nearest = d;
      }
    }
    return nearest;
  };
  const valueByDate = new Map(
    points.map((p) => [p.date, isEarnings ? ((p.value_low ?? 0) + (p.value_high ?? 0)) / 2 : p.value]),
  );

  // Sparse snapshot history means many events snap to the SAME point --
  // e.g. right after a backfill there may be only one snapshot, so every
  // event in the window lands on it. Rendering one dot per event there
  // would silently stack them into indistinguishable, overlapping shapes.
  // Cluster by snapped date instead: one visible marker per date, sized/
  // labeled by how many events it holds. Hover/click info is surfaced via
  // the chart's own Tooltip (see CustomTooltip) rather than per-dot mouse
  // handlers -- recharts renders an invisible full-chart hover-tracking
  // overlay ON TOP of everything for its own Tooltip/cursor, which
  // silently swallows mouse events aimed at a custom shape underneath it.
  const clustersByDate = new Map();
  for (const e of events) {
    const snappedDate = nearestPointDate(e.date);
    const y = valueByDate.get(snappedDate);
    if (y === undefined || y === null) continue;
    if (!clustersByDate.has(snappedDate)) clustersByDate.set(snappedDate, { date: snappedDate, y, items: [] });
    clustersByDate.get(snappedDate).items.push(e);
  }
  const clusters = [...clustersByDate.values()];

  const handleChartClick = (chartEvent) => {
    const cluster = chartEvent?.activeLabel ? clustersByDate.get(chartEvent.activeLabel) : null;
    const withLink = cluster?.items.find((e) => e.permalink);
    if (withLink) onEventClick?.(withLink);
  };

  return (
    <div className="w-full h-64 relative">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }} onClick={handleChartClick}>
          <defs>
            <linearGradient id="growthFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.25} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border-subtle)" />
          <XAxis
            dataKey="date"
            tickFormatter={(val) => format(parseISO(val), 'MMM d')}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 12, fill: 'var(--color-text-muted)' }}
            dy={10}
            minTickGap={24}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 12, fill: 'var(--color-text-muted)' }}
            tickFormatter={isEarnings ? (v) => `$${formatCompactNumber(v)}` : formatCompactNumber}
            width={52}
          />
          <Tooltip content={<CustomTooltip metric={metric} isEarnings={isEarnings} clustersByDate={clustersByDate} />} />
          {isEarnings ? (
            <Area type="monotone" dataKey="value_range" stroke={color} strokeWidth={1.5} fill="url(#growthFill)" connectNulls isAnimationActive={false} />
          ) : (
            <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill="url(#growthFill)" dot={false} />
          )}
          {clusters.map((cluster) => {
            const singleType = cluster.items.every((e) => e.type === cluster.items[0].type) ? cluster.items[0].type : null;
            const dotColor = singleType ? EVENT_COLORS[singleType] : 'var(--color-text-primary)';
            const radius = cluster.items.length > 1 ? 7 : 5;
            return (
              <ReferenceDot
                key={cluster.date}
                x={cluster.date}
                y={cluster.y}
                r={radius}
                fill={dotColor}
                stroke="var(--color-bg-card)"
                strokeWidth={2}
                isFront
                shape={(shapeProps) => <EventDotShape {...shapeProps} cluster={cluster} />}
              />
            );
          })}
        </ComposedChart>
      </ResponsiveContainer>

      {clusters.length > 0 && (
        <div className="flex items-center gap-4 mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: EVENT_COLORS.top_post }} />
            Standout post
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: EVENT_COLORS.milestone }} />
            Follower milestone
          </span>
          <span>· hover a point on the chart for details, click to open a post</span>
        </div>
      )}
    </div>
  );
}

function EventDotShape({ cx, cy, fill, r, stroke, strokeWidth, cluster }) {
  return (
    <g style={{ cursor: 'pointer' }}>
      <circle cx={cx} cy={cy} r={r} fill={fill} stroke={stroke} strokeWidth={strokeWidth} />
      {cluster.items.length > 1 && (
        <text x={cx} y={cy} dy={3} textAnchor="middle" fontSize={9} fontWeight={700} fill="var(--color-bg-card)">
          {cluster.items.length}
        </text>
      )}
    </g>
  );
}
