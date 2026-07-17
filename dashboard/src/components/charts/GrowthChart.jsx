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

// Cumulative growth chart -- an Area for normal metrics (followers/views/
// posts), or a low/high band for the derived "earnings" metric, which has
// no single value. Key events (standout posts, follower milestones) are
// plotted as colored dots on top; each dot gets a native <title> tooltip
// plus an onClick that opens the post's permalink for top_post events.
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
  // lookup silently drops nearly every event. Two things matter here:
  // (1) the y-value comes from the nearest point's series value, and (2)
  // the x position MUST also be one of the chart's actual category values
  // (recharts' XAxis here is a category axis from `date`, not a
  // continuous time scale) or ReferenceDot can't place it at all.
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
  const plottableEvents = events
    .map((e) => {
      const snappedDate = nearestPointDate(e.date);
      return { ...e, snappedDate, y: valueByDate.get(snappedDate) };
    })
    .filter((e) => e.y !== undefined && e.y !== null);

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
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
          <Tooltip
            labelFormatter={(val) => format(parseISO(val), 'MMM d, yyyy')}
            formatter={(value, name) => {
              if (name === 'value_range') return [formatUsdRange(value[0], value[1]), METRIC_LABELS.earnings];
              return [formatCompactNumber(value), METRIC_LABELS[metric] ?? metric];
            }}
            contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-default)', borderRadius: 10 }}
            labelStyle={{ color: 'var(--color-text-primary)', fontWeight: 600, marginBottom: 4 }}
            itemStyle={{ color: 'var(--color-text-secondary)' }}
          />
          {isEarnings ? (
            <Area type="monotone" dataKey="value_range" stroke={color} strokeWidth={1.5} fill="url(#growthFill)" connectNulls isAnimationActive={false} />
          ) : (
            <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill="url(#growthFill)" dot={false} />
          )}
          {plottableEvents.map((e) => (
            <ReferenceDot
              key={`${e.type}-${e.date}-${e.label}`}
              x={e.snappedDate}
              y={e.y}
              r={5}
              fill={EVENT_COLORS[e.type] ?? 'var(--color-accent)'}
              stroke="var(--color-bg-card)"
              strokeWidth={2}
              style={{ cursor: e.permalink ? 'pointer' : 'default' }}
              onClick={() => onEventClick?.(e)}
            >
              <title>{`${e.label} · ${format(parseISO(e.date), 'MMM d, yyyy')}`}</title>
            </ReferenceDot>
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
