import React, { useMemo, useState } from 'react';
import { BadgeCheck, ChevronUp, History, Search } from 'lucide-react';
import { format } from 'date-fns';
import { toast } from 'sonner';
import StatusBadge from '../common/StatusBadge';
import PlatformIcon from '../common/PlatformIcon';
import Input from '../common/Input';
import EmptyState from '../common/EmptyState';
import JobHistoryPanel from '../influencers/JobHistoryPanel';
import { refreshVerified } from '../../services/influencerService';
import { formatHandle, platformLabel } from '../../utils/platform';

const IN_FLIGHT_STATUSES = new Set(['queued', 'running', 'retry_pending']);

// Which pill click maps to which status filter -- "in flight" isn't a real
// ScrapeJob.status value, it's queued/running/retry_pending combined, so it
// needs its own synthetic filter value rather than matching one column.
const PILL_FILTERS = {
  total: 'all',
  inFlight: 'in_flight',
  completed: 'completed',
  failed: 'failed',
};

// Recent verify jobs, deduped to the most recent run per influencer --
// get_recent_by_job_type intentionally returns a flat, un-deduped recency
// feed (an influencer re-triggered a few times shows up several times),
// which made this table balloon with repeat rows for the same handful of
// influencers instead of reading as "current status per influencer". Full
// history per influencer is still one click away via the History button.
function dedupeToLatestPerInfluencer(jobs) {
  const seen = new Set();
  const result = [];
  for (const job of jobs) {
    if (seen.has(job.influencer_id)) continue;
    seen.add(job.influencer_id);
    result.push(job);
  }
  return result;
}

export default function VerifyJobsPanel({ jobs, summary }) {
  const [platformFilter, setPlatformFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [expandedHistory, setExpandedHistory] = useState(() => new Set());
  const [triggering, setTriggering] = useState(() => new Set());
  const [statusOverride, setStatusOverride] = useState(() => new Map());

  const latestPerInfluencer = useMemo(() => dedupeToLatestPerInfluencer(jobs ?? []), [jobs]);

  const statuses = useMemo(
    () => [...new Set(latestPerInfluencer.map((j) => j.status))],
    [latestPerInfluencer],
  );

  const filtered = useMemo(() => {
    let result = latestPerInfluencer;
    if (platformFilter !== 'all') {
      result = result.filter((j) => j.platform === platformFilter);
    }
    if (statusFilter === 'in_flight') {
      result = result.filter((j) => IN_FLIGHT_STATUSES.has(j.status));
    } else if (statusFilter !== 'all') {
      result = result.filter((j) => j.status === statusFilter);
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter((j) => j.handle.toLowerCase().includes(q));
    }
    return result;
  }, [latestPerInfluencer, platformFilter, statusFilter, search]);

  const selectPill = (platform, pillKey) => {
    setPlatformFilter(platform);
    setStatusFilter(PILL_FILTERS[pillKey]);
  };

  const toggleHistory = (influencerId) => {
    setExpandedHistory((prev) => {
      const next = new Set(prev);
      next.has(influencerId) ? next.delete(influencerId) : next.add(influencerId);
      return next;
    });
  };

  const handleForceVerify = async (job) => {
    setTriggering((prev) => new Set(prev).add(job.influencer_id));
    try {
      await refreshVerified(job.influencer_id);
      toast.success(`Verify job queued for ${formatHandle(job.handle, job.platform)}`);
      setStatusOverride((prev) => new Map(prev).set(job.influencer_id, 'queued'));
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setTriggering((prev) => {
        const next = new Set(prev);
        next.delete(job.influencer_id);
        return next;
      });
    }
  };

  return (
    <div>
      {summary && summary.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-4">
          {summary.map((s) => {
            const inFlight = s.queued + s.running + s.retry_pending;
            const total = inFlight + s.completed + s.failed + s.cancelled;
            const isActivePlatform = platformFilter === s.platform;
            return (
              <div
                key={s.platform}
                className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs"
                style={{
                  background: isActivePlatform ? 'var(--color-bg-card)' : 'var(--color-bg-card-hover)',
                  border: '1px solid ' + (isActivePlatform ? 'var(--color-accent)' : 'var(--color-border-subtle)'),
                }}
              >
                <PlatformIcon platform={s.platform} className="w-4 h-4 rounded" />
                <span className="font-medium" style={{ color: 'var(--color-text-primary)' }}>{platformLabel(s.platform)}</span>
                <button
                  type="button"
                  className="hover:underline"
                  style={{ color: 'var(--color-text-muted)' }}
                  onClick={() => selectPill(s.platform, 'total')}
                  title={`Show every ${platformLabel(s.platform)} verify job`}
                >
                  {total} total
                </button>
                {inFlight > 0 && (
                  <button
                    type="button"
                    className="hover:underline"
                    style={{ color: 'var(--color-accent)' }}
                    onClick={() => selectPill(s.platform, 'inFlight')}
                    title={`Show only queued/running/retry_pending ${platformLabel(s.platform)} verify jobs`}
                  >
                    {inFlight} in flight
                  </button>
                )}
                <button
                  type="button"
                  className="hover:underline"
                  style={{ color: 'var(--color-success)' }}
                  onClick={() => selectPill(s.platform, 'completed')}
                  title={`Show only completed ${platformLabel(s.platform)} verify jobs`}
                >
                  {s.completed} completed
                </button>
                {s.failed > 0 && (
                  <button
                    type="button"
                    className="hover:underline"
                    style={{ color: 'var(--color-danger)' }}
                    onClick={() => selectPill(s.platform, 'failed')}
                    title={`Show only failed ${platformLabel(s.platform)} verify jobs`}
                  >
                    {s.failed} failed
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {!jobs || jobs.length === 0 ? (
        <p className="text-sm text-center py-6" style={{ color: 'var(--color-text-muted)' }}>
          No verify jobs have run yet.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <div className="relative flex-1 min-w-[160px]">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-muted)' }} />
              <Input
                placeholder="Search handle…"
                className="pl-8 py-1.5 text-xs"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select
              value={platformFilter}
              onChange={(e) => setPlatformFilter(e.target.value)}
              className="px-3 py-1.5 rounded-xl text-xs outline-none border"
              style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)', borderColor: 'var(--color-border-default)' }}
            >
              <option value="all">All platforms</option>
              {[...new Set(latestPerInfluencer.map((j) => j.platform))].map((p) => (
                <option key={p} value={p}>{platformLabel(p)}</option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-1.5 rounded-xl text-xs outline-none border"
              style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)', borderColor: 'var(--color-border-default)' }}
            >
              <option value="all">All statuses</option>
              <option value="in_flight">In flight (queued/running/retry)</option>
              {statuses.map((s) => (
                <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>
              ))}
            </select>
            <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              {filtered.length} of {latestPerInfluencer.length} influencer(s)
            </span>
          </div>

          {filtered.length === 0 ? (
            <EmptyState title="No matches" message="No verify jobs match the current filters." />
          ) : (
            <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0" style={{ background: 'var(--color-bg-card)' }}>
                  <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    {['Status', 'Influencer', 'Platform', 'Started', 'Duration', 'Error', 'History', 'Actions'].map((h) => (
                      <th key={h} className="text-left py-2 px-3 font-medium whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((j) => (
                    <React.Fragment key={j.influencer_id}>
                      <tr style={{ borderBottom: expandedHistory.has(j.influencer_id) ? 'none' : '1px solid var(--color-border-subtle)' }}>
                        <td className="py-2 px-3">
                          <StatusBadge status={statusOverride.get(j.influencer_id) ?? j.status} />
                        </td>
                        <td className="py-2 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-primary)' }}>
                          {formatHandle(j.handle, j.platform)}
                        </td>
                        <td className="py-2 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                          {platformLabel(j.platform)}
                        </td>
                        <td className="py-2 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                          {format(new Date(j.created_at), 'MMM d, HH:mm')}
                        </td>
                        <td className="py-2 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                          {j.duration_s != null ? `${j.duration_s.toFixed(1)}s` : '—'}
                        </td>
                        <td className="py-2 px-3 text-xs max-w-[260px]" style={{ color: 'var(--color-text-muted)' }} title={j.error_message ?? undefined}>
                          <div className="truncate">{j.error_message ?? '—'}</div>
                        </td>
                        <td className="py-2 px-3">
                          <button
                            onClick={() => toggleHistory(j.influencer_id)}
                            className="inline-flex items-center justify-center rounded-lg p-1.5 transition-colors hover:bg-[var(--color-bg-card-hover)]"
                            title={expandedHistory.has(j.influencer_id) ? 'Hide run history' : 'Show run history'}
                          >
                            {expandedHistory.has(j.influencer_id) ? (
                              <ChevronUp className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                            ) : (
                              <History className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                            )}
                          </button>
                        </td>
                        <td className="py-2 px-3">
                          <button
                            onClick={() => handleForceVerify(j)}
                            disabled={
                              triggering.has(j.influencer_id) ||
                              IN_FLIGHT_STATUSES.has(statusOverride.get(j.influencer_id) ?? j.status)
                            }
                            className="inline-flex items-center justify-center rounded-lg p-1.5 transition-colors hover:bg-[var(--color-bg-card-hover)] disabled:opacity-40 disabled:cursor-not-allowed"
                            title="Force start verify job"
                          >
                            <BadgeCheck
                              className={`w-3.5 h-3.5 ${triggering.has(j.influencer_id) ? 'animate-pulse' : ''}`}
                              style={{ color: 'var(--color-text-muted)' }}
                            />
                          </button>
                        </td>
                      </tr>
                      {expandedHistory.has(j.influencer_id) && (
                        <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                          <td colSpan={8} className="px-3 pb-3">
                            <JobHistoryPanel influencerId={j.influencer_id} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
