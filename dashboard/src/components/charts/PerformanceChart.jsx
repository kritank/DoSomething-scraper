import React, { useMemo } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';
import { platformLabel, PLATFORM_COLORS } from '../../utils/platform';

// One row per (date, status, platform) -> one row per date: posts/comments
// processed summed per platform (throughput split by platform, not just an
// all-platforms-combined total), YouTube quota units spent, and job
// duration -- mean plus a min/max range (a day where the average looks
// fine can still hide a handful of jobs that ran far longer than usual;
// the average alone hides that, the range band surfaces it). Duration
// itself isn't split by platform ("throughput" is about volume; the range
// band already reveals what averaging would otherwise hide, without a
// second axis' worth of extra series).
function aggregateByDate(buckets) {
  const byDate = new Map();
  for (const b of buckets) {
    if (!byDate.has(b.date)) byDate.set(b.date, { date: b.date, durations: [], mins: [], maxes: [] });
    const row = byDate.get(b.date);
    row[`${b.platform}_posts`] = (row[`${b.platform}_posts`] ?? 0) + b.posts_processed;
    row[`${b.platform}_comments`] = (row[`${b.platform}_comments`] ?? 0) + b.comments_processed;
    if (b.quota_units_used != null) {
      row.youtube_quota = (row.youtube_quota ?? 0) + b.quota_units_used;
    }
    if (b.avg_duration_s != null) row.durations.push(b.avg_duration_s);
    if (b.min_duration_s != null) row.mins.push(b.min_duration_s);
    if (b.max_duration_s != null) row.maxes.push(b.max_duration_s);
  }
  return [...byDate.values()]
    .map((row) => {
      const min = row.mins.length ? Math.min(...row.mins) : null;
      const max = row.maxes.length ? Math.max(...row.maxes) : null;
      return {
        ...row,
        avg_duration_s: row.durations.length
          ? row.durations.reduce((a, b) => a + b, 0) / row.durations.length
          : null,
        // Recharts' range-area idiom: an Area fed a [min, max] tuple per
        // point renders the band between them.
        duration_range: min != null && max != null ? [min, max] : null,
      };
    })
    .sort((a, b) => a.date.localeCompare(b.date));
}

export default function PerformanceChart({ buckets }) {
  const data = useMemo(() => aggregateByDate(buckets ?? []), [buckets]);
  const platforms = useMemo(
    () => [...new Set((buckets ?? []).map((b) => b.platform))],
    [buckets],
  );
  const hasQuota = useMemo(() => (buckets ?? []).some((b) => b.quota_units_used != null), [buckets]);

  if (data.length === 0) {
    return <EmptyState title="No performance data yet" message="Duration and throughput trends show up here." />;
  }

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border-subtle)" />
          <XAxis
            dataKey="date"
            tickFormatter={(val) => format(parseISO(val), 'MMM d')}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 12, fill: 'var(--color-text-muted)' }}
            dy={10}
            minTickGap={20}
          />
          <YAxis
            yAxisId="posts"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 12, fill: 'var(--color-text-muted)' }}
            allowDecimals={false}
          />
          <YAxis
            yAxisId="duration"
            orientation="right"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 12, fill: 'var(--color-text-muted)' }}
            tickFormatter={(v) => `${Math.round(v)}s`}
          />
          {/* Own axes, hidden -- comment volume typically runs 100-1000x
              post volume, and quota units are a different unit entirely;
              either would flatten against the posts/duration axes if it
              shared their scale. */}
          <YAxis yAxisId="comments" hide allowDecimals={false} />
          <YAxis yAxisId="quota" hide allowDecimals={false} />
          <Tooltip
            labelFormatter={(val) => format(parseISO(val), 'MMM d, yyyy')}
            formatter={(value, name) => {
              if (name === 'avg_duration_s') return [`${value?.toFixed(1)}s`, 'Avg duration'];
              if (name === 'duration_range') return [`${value[0].toFixed(1)}s – ${value[1].toFixed(1)}s`, 'Duration range'];
              if (name === 'youtube_quota') return [value, 'YouTube quota used'];
              const sepIndex = name.indexOf('_');
              const platform = name.slice(0, sepIndex);
              const kind = name.slice(sepIndex + 1);
              return [value, `${platformLabel(platform)} ${kind}`];
            }}
            contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-default)', borderRadius: 10 }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12 }}
            payload={[
              ...platforms.map((p) => ({ value: `${platformLabel(p)} posts`, type: 'square', color: PLATFORM_COLORS[p] })),
              ...platforms.map((p) => ({ value: `${platformLabel(p)} comments`, type: 'line', color: PLATFORM_COLORS[p] })),
              { value: 'Avg duration (s)', type: 'line', color: 'var(--color-chart-4)' },
              { value: 'Duration range', type: 'rect', color: 'var(--color-chart-4)' },
              ...(hasQuota ? [{ value: 'YouTube quota used', type: 'line', color: 'var(--color-warning)' }] : []),
            ]}
          />
          {platforms.map((p) => (
            <Bar key={`${p}_posts`} yAxisId="posts" dataKey={`${p}_posts`} stackId="posts" fill={PLATFORM_COLORS[p]} radius={[4, 4, 0, 0]} barSize={20} />
          ))}
          {platforms.map((p) => (
            <Line
              key={`${p}_comments`}
              yAxisId="comments"
              type="monotone"
              dataKey={`${p}_comments`}
              stroke={PLATFORM_COLORS[p]}
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
            />
          ))}
          <Area
            yAxisId="duration"
            type="monotone"
            dataKey="duration_range"
            stroke="none"
            fill="var(--color-chart-4)"
            fillOpacity={0.15}
            connectNulls
            isAnimationActive={false}
          />
          <Line yAxisId="duration" type="monotone" dataKey="avg_duration_s" stroke="var(--color-chart-4)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
          {hasQuota && (
            <Line
              yAxisId="quota"
              type="monotone"
              dataKey="youtube_quota"
              stroke="var(--color-warning)"
              strokeWidth={2}
              strokeDasharray="4 3"
              dot={{ r: 3 }}
              connectNulls
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
