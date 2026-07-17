import React from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';
import { formatCompactNumber } from '../../utils/format';

const METRIC_LABELS = {
  followers: 'Followers',
  total_views: 'Total views',
  posts: 'Posts',
};

export default function GrowthChart({ points, metric, color = 'var(--color-accent)' }) {
  if (!points || points.length === 0) {
    return (
      <EmptyState
        title="Not enough history yet"
        message="Growth charts need at least a couple of days of snapshots to plot."
      />
    );
  }

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
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
            tickFormatter={formatCompactNumber}
            width={48}
          />
          <Tooltip
            labelFormatter={(val) => format(parseISO(val), 'MMM d, yyyy')}
            formatter={(value) => [formatCompactNumber(value), METRIC_LABELS[metric] ?? metric]}
            contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-default)', borderRadius: 10 }}
          />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill="url(#growthFill)" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
