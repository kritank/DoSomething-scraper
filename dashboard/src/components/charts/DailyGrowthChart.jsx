import React from 'react';
import { ResponsiveContainer, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from 'recharts';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';
import { formatSignedCompact } from '../../utils/format';

// The vidiq-style "Daily Subscriber Growth" view -- day-over-day change
// as green (gain) / red (loss) bars, distinct from GrowthChart's
// cumulative area above it. Points with daily_delta == null (the series'
// first day, or a gap where no snapshot was captured) are dropped rather
// than drawn as a 0-height bar, which would misleadingly read as "no
// change" instead of "no data."
export default function DailyGrowthChart({ points, label = 'Followers' }) {
  const data = (points ?? []).filter((p) => p.daily_delta !== null && p.daily_delta !== undefined);

  if (data.length === 0) {
    return (
      <EmptyState
        title="Not enough history yet"
        message="Daily change needs at least two consecutive days of snapshots to plot."
      />
    );
  }

  return (
    <div className="w-full h-48">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
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
            tickFormatter={formatSignedCompact}
            width={52}
          />
          <ReferenceLine y={0} stroke="var(--color-border-default)" />
          <Tooltip
            labelFormatter={(val) => format(parseISO(val), 'MMM d, yyyy')}
            formatter={(value) => [formatSignedCompact(value), `Daily ${label.toLowerCase()} change`]}
            contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-default)', borderRadius: 10 }}
            labelStyle={{ color: 'var(--color-text-primary)', fontWeight: 600, marginBottom: 4 }}
            itemStyle={{ color: 'var(--color-text-secondary)' }}
          />
          <Bar dataKey="daily_delta" radius={[3, 3, 3, 3]}>
            {data.map((p) => (
              <Cell key={p.date} fill={p.daily_delta >= 0 ? 'var(--color-success)' : 'var(--color-danger)'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
