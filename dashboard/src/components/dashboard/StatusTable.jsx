import React, { useMemo, useState } from 'react';
import { ArrowUpDown, Search } from 'lucide-react';
import { format } from 'date-fns';
import StatusBadge from '../common/StatusBadge';
import Input from '../common/Input';
import EmptyState from '../common/EmptyState';

const COLUMNS = [
  { key: 'category_name', label: 'Category' },
  { key: 'handle', label: 'Influencer' },
  { key: 'last_job_status', label: 'Last Scrape' },
  { key: 'last_job_finished_at', label: 'When' },
  { key: 'last_job_duration_s', label: 'Duration' },
  { key: 'last_job_posts_processed', label: 'Posts' },
  { key: 'last_job_comments_processed', label: 'Comments' },
];

function formatDuration(s) {
  if (s == null) return '—';
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

export default function StatusTable({ rows }) {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortKey, setSortKey] = useState('handle');
  const [sortDir, setSortDir] = useState('asc');

  const statuses = useMemo(
    () => [...new Set(rows.map((r) => r.last_job_status ?? 'never_scraped'))],
    [rows],
  );

  const filtered = useMemo(() => {
    let result = rows;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter(
        (r) => r.handle.toLowerCase().includes(q) || r.category_name.toLowerCase().includes(q),
      );
    }
    if (statusFilter !== 'all') {
      result = result.filter((r) => (r.last_job_status ?? 'never_scraped') === statusFilter);
    }
    return [...result].sort((a, b) => {
      const av = a[sortKey] ?? '';
      const bv = b[sortKey] ?? '';
      const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [rows, search, statusFilter, sortKey, sortDir]);

  const toggleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  return (
    <div className="card p-5 flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-muted)' }} />
          <Input
            placeholder="Search handle or category…"
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2.5 rounded-xl text-sm outline-none border"
          style={{
            background: 'var(--color-bg-secondary)',
            color: 'var(--color-text-primary)',
            borderColor: 'var(--color-border-default)',
          }}
        >
          <option value="all">All statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>
          ))}
        </select>
      </div>

      {filtered.length === 0 ? (
        <EmptyState title="No influencers match" message="Try clearing your search or filter." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => toggleSort(col.key)}
                    className="text-left py-2.5 px-3 font-medium cursor-pointer select-none whitespace-nowrap"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.label}
                      <ArrowUpDown className="w-3 h-3 opacity-50" />
                    </span>
                  </th>
                ))}
                <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Flags</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr
                  key={row.influencer_id}
                  className="transition-colors hover:bg-[var(--color-bg-card-hover)]"
                  style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
                  title={row.last_job_error_message ?? undefined}
                >
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{row.category_name}</td>
                  <td className="py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-primary)' }}>@{row.handle}</td>
                  <td className="py-2.5 px-3"><StatusBadge status={row.last_job_status} /></td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {row.last_job_finished_at ? format(new Date(row.last_job_finished_at), 'MMM d, HH:mm') : '—'}
                  </td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {formatDuration(row.last_job_duration_s)}
                  </td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {row.last_job_posts_processed ?? '—'}
                  </td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {row.last_job_comments_processed ?? '—'}
                  </td>
                  <td className="py-2.5 px-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    {!row.is_active && <span className="mr-2">paused</span>}
                    {!row.backfill_completed && <span>backfilling</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
