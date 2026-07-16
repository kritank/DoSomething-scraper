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

// Reuses the same status vocabulary as StatusBadge, but for pooled
// credentials (InstagramAccount.status / YouTubeApiKey.status) rather than
// ScrapeJob.status -- quota_exhausted specifically gets its own warning
// color so a key sitting out of quota for part of a day shows up as a
// visible amber band, not just a number in a table.
const STATUS_COLORS = {
  active: 'var(--color-success)',
  in_use: 'var(--color-accent)',
  pending_login: 'var(--color-accent)',
  checkpoint_required: 'var(--color-danger)',
  login_failed: 'var(--color-danger)',
  invalid: 'var(--color-danger)',
  quota_exhausted: 'var(--color-warning)',
  disabled: 'var(--color-text-muted)',
};

// buckets: [{date, platform, status, snapshot_count}] for ONE platform
// (caller filters/passes the right slice -- see Overview.jsx, which
// renders one of these per platform). Pivoted into one row per date with
// a column per status, stacked -- a full-height green bar means "healthy
// the whole day"; any colored band cutting into it is a real incident.
function pivotByDate(buckets) {
  const byDate = new Map();
  for (const b of buckets) {
    if (!byDate.has(b.date)) byDate.set(b.date, { date: b.date });
    byDate.get(b.date)[b.status] = b.snapshot_count;
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export default function CredentialHealthChart({ buckets }) {
  const data = useMemo(() => pivotByDate(buckets ?? []), [buckets]);
  const statuses = useMemo(
    () => [...new Set((buckets ?? []).map((b) => b.status))],
    [buckets],
  );

  if (data.length === 0) {
    return (
      <EmptyState
        title="No health snapshots yet"
        message="Collected every 10 minutes by the scheduler -- check back shortly, or widen the date range."
      />
    );
  }

  return (
    <div className="w-full h-56">
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
            formatter={(value, name) => [value, name.replaceAll('_', ' ')]}
            contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-default)', borderRadius: 10 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => v.replaceAll('_', ' ')} />
          {statuses.map((status) => (
            <Bar key={status} dataKey={status} stackId="health" fill={STATUS_COLORS[status] ?? 'var(--color-text-muted)'} radius={[0, 0, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
