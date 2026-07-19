import React, { useMemo, useState } from 'react';
import { AlertTriangle, ArrowUpDown, ChevronUp, History, PlayCircle, Search } from 'lucide-react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import StatusBadge from '../common/StatusBadge';
import PlatformBadge from '../common/PlatformBadge';
import Input from '../common/Input';
import InfoTip from '../common/InfoTip';
import EmptyState from '../common/EmptyState';
import JobHistoryPanel from '../influencers/JobHistoryPanel';
import { triggerScrape } from '../../services/influencerService';
import { formatHandle } from '../../utils/platform';

// Matches Influencers.jsx's "Scrape now" button -- a job already
// queued/running for this influencer can't be triggered again.
const IN_FLIGHT_STATUSES = new Set(['queued', 'running']);

const COLUMNS = [
  { key: 'category_name', label: 'Category' },
  { key: 'handle', label: 'Influencer' },
  { key: 'platform', label: 'Platform' },
  { key: 'last_job_status', label: 'Last Scrape' },
  { key: 'last_job_finished_at', label: 'When' },
  { key: 'last_job_duration_s', label: 'Duration' },
  { key: 'last_job_posts_processed', label: 'Posts' },
  { key: 'last_job_comments_processed', label: 'Comments' },
  { key: 'last_job_scraper_account', label: 'Account' },
  { key: 'job_success_rate', label: 'Reliability' },
];

// A streak this long means every recent attempt has failed -- worth
// calling out even before the job is old enough to have a poor lifetime
// average. Matches SCRAPER_MAX_RETRIES (app/core/config.py) -- one streak
// this long is exactly "this influencer just burned through its retries".
const FAILING_STREAK_THRESHOLD = 3;

const RELIABILITY_WINDOWS = [
  { label: 'Lifetime', value: null },
  { label: '7D', value: 7 },
  { label: '28D', value: 28 },
  { label: '90D', value: 90 },
];

function reliabilityTooltip(windowDays) {
  const scope = windowDays ? `the last ${windowDays} days'` : "the account's lifetime";
  return (
    `Scrape success rate over ${scope} completed / (completed + failed) jobs, excludes cancelled and ` +
    "still-running. The streak count is how many of the most recent jobs (within the same window) failed " +
    'in a row -- 0 means the last attempt succeeded, however poor the rate.'
  );
}

function formatDuration(s) {
  if (s == null) return '—';
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

export default function StatusTable({ rows, reliabilityWindowDays = null, onReliabilityWindowChange }) {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [failingOnly, setFailingOnly] = useState(false);
  const [sortKey, setSortKey] = useState('handle');
  const [sortDir, setSortDir] = useState('asc');
  const [expandedHistory, setExpandedHistory] = useState(() => new Set());
  const [triggering, setTriggering] = useState(() => new Set());
  // influencer_id -> optimistic status, so the badge flips to "queued"
  // immediately after a manual trigger without waiting for the parent's
  // next poll/refetch of `rows`.
  const [statusOverride, setStatusOverride] = useState(() => new Map());

  const handleScrapeNow = async (row) => {
    setTriggering((prev) => new Set(prev).add(row.influencer_id));
    try {
      await triggerScrape(row.influencer_id);
      toast.success(`Scrape queued for ${formatHandle(row.handle, row.platform)}`);
      setStatusOverride((prev) => new Map(prev).set(row.influencer_id, 'queued'));
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setTriggering((prev) => {
        const next = new Set(prev);
        next.delete(row.influencer_id);
        return next;
      });
    }
  };

  const toggleHistory = (influencerId) => {
    setExpandedHistory((prev) => {
      const next = new Set(prev);
      next.has(influencerId) ? next.delete(influencerId) : next.add(influencerId);
      return next;
    });
  };

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
    if (failingOnly) {
      result = result.filter((r) => (r.consecutive_job_failures ?? 0) >= FAILING_STREAK_THRESHOLD);
    }
    return [...result].sort((a, b) => {
      const av = a[sortKey] ?? '';
      const bv = b[sortKey] ?? '';
      const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [rows, search, statusFilter, failingOnly, sortKey, sortDir]);

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
        <button
          onClick={() => setFailingOnly((v) => !v)}
          className="px-3 py-2.5 rounded-xl text-sm font-medium border inline-flex items-center gap-1.5 transition-colors"
          style={{
            background: failingOnly ? 'var(--color-danger-muted)' : 'var(--color-bg-secondary)',
            color: failingOnly ? 'var(--color-danger)' : 'var(--color-text-secondary)',
            borderColor: failingOnly ? 'var(--color-danger)' : 'var(--color-border-default)',
          }}
          title={`Show only influencers whose last ${FAILING_STREAK_THRESHOLD}+ scrape attempts all failed in a row`}
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          Failing frequently
        </button>
        {onReliabilityWindowChange && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium" style={{ color: 'var(--color-text-muted)' }}>Reliability</span>
            <div className="flex items-center gap-1 rounded-lg p-0.5" style={{ background: 'var(--color-bg-card-hover)' }}>
              {RELIABILITY_WINDOWS.map((opt) => (
                <button
                  key={opt.label}
                  onClick={() => onReliabilityWindowChange(opt.value)}
                  className="px-2.5 py-1 rounded-md text-xs font-semibold transition-colors"
                  style={{
                    background: reliabilityWindowDays === opt.value ? 'var(--color-accent)' : 'transparent',
                    color: reliabilityWindowDays === opt.value ? '#fff' : 'var(--color-text-muted)',
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        )}
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
                      {col.key === 'job_success_rate' && (
                        <span onClick={(e) => e.stopPropagation()}>
                          <InfoTip text={reliabilityTooltip(reliabilityWindowDays)} side="bottom" />
                        </span>
                      )}
                    </span>
                  </th>
                ))}
                <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Flags</th>
                <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>History</th>
                <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <React.Fragment key={row.influencer_id}>
                <tr
                  className="transition-colors hover:bg-[var(--color-bg-card-hover)]"
                  style={{ borderBottom: expandedHistory.has(row.influencer_id) ? 'none' : '1px solid var(--color-border-subtle)' }}
                  title={row.last_job_error_message ?? undefined}
                >
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{row.category_name}</td>
                  <td className="py-2.5 px-3 font-medium whitespace-nowrap">
                    <Link
                      to={row.creator_id ? `/creators/${row.creator_id}` : `/influencers/${row.influencer_id}`}
                      className="hover:underline"
                      style={{ color: 'var(--color-text-primary)' }}
                    >
                      {formatHandle(row.handle, row.platform)}
                    </Link>
                  </td>
                  <td className="py-2.5 px-3">
                    <PlatformBadge platform={row.platform} handle={row.handle} />
                  </td>
                  <td className="py-2.5 px-3"><StatusBadge status={statusOverride.get(row.influencer_id) ?? row.last_job_status} /></td>
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
                  <td className="py-2.5 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                    {row.last_job_scraper_account ?? '—'}
                  </td>
                  <td className="py-2.5 px-3 whitespace-nowrap">
                    <ReliabilityCell row={row} windowDays={reliabilityWindowDays} />
                  </td>
                  <td className="py-2.5 px-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    {row.deactivation_reason === 'handle_not_found' ? (
                      <span style={{ color: 'var(--color-danger)' }}>handle not found -- recheck</span>
                    ) : !row.is_active ? (
                      <span className="mr-2">{row.paused_by_category ? 'held with category' : 'paused'}</span>
                    ) : null}
                    {!row.backfill_completed && <span>backfilling</span>}
                  </td>
                  <td className="py-2.5 px-3">
                    <button
                      onClick={() => toggleHistory(row.influencer_id)}
                      className="inline-flex items-center justify-center rounded-lg p-1.5 transition-colors hover:bg-[var(--color-bg-card-hover)]"
                      title={expandedHistory.has(row.influencer_id) ? 'Hide run history' : 'Show run history'}
                    >
                      {expandedHistory.has(row.influencer_id) ? (
                        <ChevronUp className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                      ) : (
                        <History className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                      )}
                    </button>
                  </td>
                  <td className="py-2.5 px-3">
                    <button
                      onClick={() => handleScrapeNow(row)}
                      disabled={
                        triggering.has(row.influencer_id) ||
                        IN_FLIGHT_STATUSES.has(statusOverride.get(row.influencer_id) ?? row.last_job_status)
                      }
                      className="inline-flex items-center justify-center rounded-lg p-1.5 transition-colors hover:bg-[var(--color-bg-card-hover)] disabled:opacity-40 disabled:cursor-not-allowed"
                      title="Scrape now"
                    >
                      <PlayCircle
                        className={`w-3.5 h-3.5 ${triggering.has(row.influencer_id) ? 'animate-pulse' : ''}`}
                        style={{ color: 'var(--color-text-muted)' }}
                      />
                    </button>
                  </td>
                </tr>
                {expandedHistory.has(row.influencer_id) && (
                  <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    <td colSpan={COLUMNS.length + 3} className="px-3 pb-3">
                      <JobHistoryPanel influencerId={row.influencer_id} />
                    </td>
                  </tr>
                )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ReliabilityCell({ row, windowDays }) {
  const total = row.total_job_runs ?? 0;
  if (total === 0) {
    return (
      <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
        {windowDays ? `No runs in ${windowDays}D` : 'Never scraped'}
      </span>
    );
  }
  const rate = row.job_success_rate;
  const streak = row.consecutive_job_failures ?? 0;
  const isFailing = streak >= FAILING_STREAK_THRESHOLD;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span style={{ color: rate == null ? 'var(--color-text-muted)' : isFailing ? 'var(--color-danger)' : 'var(--color-text-secondary)' }}>
        {rate == null ? '—' : `${Math.round(rate * 100)}%`}
        <span style={{ color: 'var(--color-text-muted)' }}> ({row.completed_job_runs}/{row.completed_job_runs + row.failed_job_runs})</span>
      </span>
      {isFailing && (
        <AlertTriangle
          className="w-3.5 h-3.5"
          style={{ color: 'var(--color-danger)' }}
          aria-label={`Failed its last ${streak} attempts in a row`}
          title={`Failed its last ${streak} attempts in a row`}
        />
      )}
    </span>
  );
}
