import React, { useMemo } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';

const STATUS_COLORS = {
  completed: 'var(--color-chart-3)',
  failed: 'var(--color-chart-5)',
  running: 'var(--color-chart-1)',
  queued: 'var(--color-chart-4)',
  retry_pending: 'var(--color-chart-2)',
};

// buckets: [{date, status, job_count, ...}] -- one row per (date, status)
// pair, straight from GET /admin/dashboard/metrics. Pivot into one row per
// date with a column per status, which is what a stacked bar chart needs.
function pivotByDate(buckets) {
  const byDate = new Map();
  for (const b of buckets) {
    if (!byDate.has(b.date)) byDate.set(b.date, { date: b.date });
    byDate.get(b.date)[b.status] = b.job_count;
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export default function JobStatusChart({ buckets }) {
  const data = useMemo(() => pivotByDate(buckets ?? []), [buckets]);
  const statuses = useMemo(
    () => [...new Set((buckets ?? []).map((b) => b.status))],
    [buckets],
  );

  if (data.length === 0) {
    return <EmptyState title="No scrape jobs yet" message="Once jobs run, daily counts show up here." />;
  }

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
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
          <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: 'var(--color-text-muted)' }} allowDecimals={false} />
          <Tooltip
            labelFormatter={(val) => format(parseISO(val), 'MMM d, yyyy')}
            contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-default)', borderRadius: 10 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => v.replaceAll('_', ' ')} />
          {statuses.map((status) => (
            <Bar key={status} dataKey={status} stackId="jobs" fill={STATUS_COLORS[status] ?? 'var(--color-text-muted)'} radius={[0, 0, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
