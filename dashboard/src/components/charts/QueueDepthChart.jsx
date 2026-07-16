import React, { useMemo } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';

// buckets: [{hour, avg_main_depth, max_main_depth, avg_dlq_depth, max_dlq_depth}]
// Hour-granularity (not day, like the rest of this dashboard) -- queue
// depth moves on the order of minutes, and the whole point of watching it
// is catching a backlog building up within a single day, which day
// buckets would flatten away entirely.
export default function QueueDepthChart({ buckets }) {
  const data = useMemo(
    () =>
      (buckets ?? [])
        .map((b) => ({
          hour: b.hour,
          avg_main_depth: b.avg_main_depth,
          // [avg, max] range band, same recharts idiom as the duration
          // range in PerformanceChart -- surfaces spikes an average alone
          // would hide.
          main_range: b.avg_main_depth != null && b.max_main_depth != null
            ? [b.avg_main_depth, b.max_main_depth]
            : null,
          avg_dlq_depth: b.avg_dlq_depth,
        }))
        .sort((a, b) => a.hour.localeCompare(b.hour)),
    [buckets],
  );
  const hasDlq = useMemo(() => (buckets ?? []).some((b) => b.avg_dlq_depth != null), [buckets]);

  if (data.length === 0) {
    return (
      <EmptyState
        title="No queue depth samples yet"
        message="Collected every 10 minutes by the scheduler -- check back shortly, or widen the date range."
      />
    );
  }

  return (
    <div className="w-full h-56">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border-subtle)" />
          <XAxis
            dataKey="hour"
            tickFormatter={(val) => format(parseISO(val), 'MMM d, ha')}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 12, fill: 'var(--color-text-muted)' }}
            dy={10}
            minTickGap={30}
          />
          <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: 'var(--color-text-muted)' }} allowDecimals={false} />
          <Tooltip
            labelFormatter={(val) => format(parseISO(val), 'MMM d, yyyy h:mma')}
            formatter={(value, name) => {
              if (name === 'main_range') return [`${value[0].toFixed(1)} – ${value[1].toFixed(1)}`, 'Queue depth range'];
              if (name === 'avg_dlq_depth') return [value.toFixed(1), 'DLQ depth'];
              return [value.toFixed(1), 'Queue depth'];
            }}
            contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-default)', borderRadius: 10 }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12 }}
            payload={[
              { value: 'Queue depth (avg)', type: 'line', color: 'var(--color-chart-1)' },
              { value: 'Range', type: 'rect', color: 'var(--color-chart-1)' },
              ...(hasDlq ? [{ value: 'DLQ depth (avg)', type: 'line', color: 'var(--color-danger)' }] : []),
            ]}
          />
          <Area
            type="monotone"
            dataKey="main_range"
            stroke="none"
            fill="var(--color-chart-1)"
            fillOpacity={0.15}
            connectNulls
            isAnimationActive={false}
          />
          <Line type="monotone" dataKey="avg_main_depth" stroke="var(--color-chart-1)" strokeWidth={2} dot={false} connectNulls />
          {hasDlq && (
            <Line type="monotone" dataKey="avg_dlq_depth" stroke="var(--color-danger)" strokeWidth={2} dot={false} connectNulls />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
