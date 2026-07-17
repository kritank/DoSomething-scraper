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
import { platformLabel } from '../../utils/platform';

const STATUS_COLORS = {
  completed: 'var(--color-chart-3)',
  failed: 'var(--color-chart-5)',
  running: 'var(--color-chart-1)',
  queued: 'var(--color-chart-4)',
  retry_pending: 'var(--color-chart-2)',
};

// buckets: [{date, status, platform, job_count, ...}] -- one row per (date,
// status, platform) triple, straight from GET /admin/dashboard/metrics.
// Pivoted into one row per date, with a `${platform}_${status}` column per
// combination. Bars for the same platform share a stackId, so each date
// renders two clusters side by side (Instagram, YouTube), each internally
// stacked by status color -- both dimensions visible without a toggle.
function pivotByDate(buckets) {
  const byDate = new Map();
  for (const b of buckets) {
    if (!byDate.has(b.date)) byDate.set(b.date, { date: b.date });
    byDate.get(b.date)[`${b.platform}_${b.status}`] = b.job_count;
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export default function JobStatusChart({ buckets }) {
  const data = useMemo(() => pivotByDate(buckets ?? []), [buckets]);
  const statuses = useMemo(
    () => [...new Set((buckets ?? []).map((b) => b.status))],
    [buckets],
  );
  const platforms = useMemo(
    () => [...new Set((buckets ?? []).map((b) => b.platform))],
    [buckets],
  );

  if (data.length === 0) {
    return <EmptyState title="No scrape jobs yet" message="Once jobs run, daily counts show up here." />;
  }

  return (
    <div className="w-full h-64 flex flex-col gap-1">
      <div className="flex-1 min-h-0">
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
              formatter={(value, name) => {
                const sepIndex = name.indexOf('_');
                const platform = name.slice(0, sepIndex);
                const status = name.slice(sepIndex + 1);
                return [value, `${platformLabel(platform)} · ${status.replaceAll('_', ' ')}`];
              }}
              contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-default)', borderRadius: 10 }}
              labelStyle={{ color: 'var(--color-text-primary)', fontWeight: 600, marginBottom: 4 }}
              itemStyle={{ color: 'var(--color-text-secondary)' }}
            />
            {/* One legend entry per status (color is shared across
                platforms -- platform is distinguished by cluster position,
                not color) instead of the verbose default of one entry per
                dataKey. */}
            <Legend
              wrapperStyle={{ fontSize: 12 }}
              payload={statuses.map((s) => ({
                value: s.replaceAll('_', ' '),
                type: 'square',
                color: STATUS_COLORS[s] ?? 'var(--color-text-muted)',
              }))}
            />
            {platforms.flatMap((platform) =>
              statuses.map((status) => (
                <Bar
                  key={`${platform}_${status}`}
                  dataKey={`${platform}_${status}`}
                  stackId={platform}
                  fill={STATUS_COLORS[status] ?? 'var(--color-text-muted)'}
                  radius={[0, 0, 0, 0]}
                />
              )),
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>
      {platforms.length > 1 && (
        <p className="text-xs text-center" style={{ color: 'var(--color-text-muted)' }}>
          Each day is grouped into one bar cluster per platform ({platforms.map(platformLabel).join(', ')}), stacked by status — hover for exact counts.
        </p>
      )}
    </div>
  );
}
