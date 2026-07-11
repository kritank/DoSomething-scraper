import React, { useMemo } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';

// One row per (date, status) -> one row per date: total posts processed
// (summed across statuses) and mean scrape duration (averaged across the
// statuses that reported one -- a simple mean is a reasonable ops-dashboard
// approximation here, not a job-count-weighted average).
function aggregateByDate(buckets) {
  const byDate = new Map();
  for (const b of buckets) {
    if (!byDate.has(b.date)) byDate.set(b.date, { date: b.date, posts_processed: 0, durations: [] });
    const row = byDate.get(b.date);
    row.posts_processed += b.posts_processed;
    if (b.avg_duration_s != null) row.durations.push(b.avg_duration_s);
  }
  return [...byDate.values()]
    .map((row) => ({
      date: row.date,
      posts_processed: row.posts_processed,
      avg_duration_s: row.durations.length
        ? row.durations.reduce((a, b) => a + b, 0) / row.durations.length
        : null,
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export default function PerformanceChart({ buckets }) {
  const data = useMemo(() => aggregateByDate(buckets ?? []), [buckets]);

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
          <Tooltip
            labelFormatter={(val) => format(parseISO(val), 'MMM d, yyyy')}
            formatter={(value, name) => (name === 'avg_duration_s' ? [`${value?.toFixed(1)}s`, 'Avg duration'] : [value, 'Posts processed'])}
            contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-default)', borderRadius: 10 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => (v === 'avg_duration_s' ? 'Avg duration (s)' : 'Posts processed')} />
          <Bar yAxisId="posts" dataKey="posts_processed" fill="var(--color-chart-2)" radius={[4, 4, 0, 0]} barSize={20} />
          <Line yAxisId="duration" type="monotone" dataKey="avg_duration_s" stroke="var(--color-chart-4)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
