import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Users, CheckCircle2, Clock, FileText, MessageSquare, Layers, ListOrdered, RefreshCw } from 'lucide-react';
import { format } from 'date-fns';
import {
  getDashboardStatus, getDashboardMetrics, getAlerts, getQueueStatus, getDlqContents,
  getCredentialHealth, getQueueHistory,
} from '../services/dashboardService';
import { getCategories } from '../services/influencerService';
import KPICard from '../components/common/KPICard';
import PlatformIcon from '../components/common/PlatformIcon';
import PlatformFilter from '../components/common/PlatformFilter';
import { SkeletonKPICard } from '../components/common/Skeleton';
import ErrorState from '../components/common/ErrorState';
import Button from '../components/common/Button';
import JobStatusChart from '../components/charts/JobStatusChart';
import PerformanceChart from '../components/charts/PerformanceChart';
import CredentialHealthChart from '../components/charts/CredentialHealthChart';
import QueueDepthChart from '../components/charts/QueueDepthChart';
import StatusTable from '../components/dashboard/StatusTable';
import DateRangeSelector from '../components/dashboard/DateRangeSelector';
import AlertsBanner from '../components/dashboard/AlertsBanner';
import { useAppStore } from '../store/useAppStore';
import { platformLabel } from '../utils/platform';

function toIso(d) {
  return format(d, 'yyyy-MM-dd');
}

function platformBreakdownFor(status, metricsBuckets, platform) {
  const rows = status.filter((r) => r.platform === platform);
  const scraped = rows.filter((r) => r.last_job_status != null);
  const successes = scraped.filter((r) => r.last_job_status === 'completed').length;

  const platformBuckets = metricsBuckets.filter((b) => b.platform === platform);
  const postsProcessed = platformBuckets.reduce((sum, b) => sum + b.posts_processed, 0);
  const commentsProcessed = platformBuckets.reduce((sum, b) => sum + b.comments_processed, 0);
  const quotaBuckets = platformBuckets.filter((b) => b.quota_units_used != null);
  const quotaUsed = quotaBuckets.length ? quotaBuckets.reduce((sum, b) => sum + b.quota_units_used, 0) : null;

  return {
    platform,
    total: rows.length,
    successRate: scraped.length ? Math.round((successes / scraped.length) * 100) : 0,
    backfilling: rows.filter((r) => !r.backfill_completed).length,
    postsProcessed,
    commentsProcessed,
    quotaUsed,
  };
}

export default function Overview() {
  const enabledPlatforms = useAppStore((s) => s.enabledPlatforms);

  const [status, setStatus] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [categoryCount, setCategoryCount] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [queueStatus, setQueueStatus] = useState(null);
  const [dlqMessages, setDlqMessages] = useState([]);
  const [credentialHealth, setCredentialHealth] = useState(null);
  const [queueHistory, setQueueHistory] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  // Defaults to today only (1d) -- a wide 30d window loaded a lot of
  // history for something whose main job is "is everything healthy right
  // now"; 1d matches that better, and the preset buttons make widening the
  // window a single click away when history is actually what's needed.
  const [startDate, setStartDate] = useState(() => toIso(new Date()));
  const [endDate, setEndDate] = useState(() => toIso(new Date()));

  // Local, further-narrowing scope within the Header's global filter --
  // drives the main KPI row / status table below. The per-platform
  // breakdown strip always shows every globally-enabled platform side by
  // side regardless of this, so narrowing focus here never hides the
  // holistic cross-platform comparison.
  const [selectedPlatforms, setSelectedPlatforms] = useState(enabledPlatforms);

  useEffect(() => {
    setSelectedPlatforms((prev) => prev.filter((p) => enabledPlatforms.includes(p)));
  }, [enabledPlatforms]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRows, metricsData, categories, alertRows, queue, dlq, health, queueHist] = await Promise.all([
        getDashboardStatus(),
        getDashboardMetrics(startDate, endDate),
        getCategories(),
        getAlerts(),
        getQueueStatus(),
        getDlqContents(),
        getCredentialHealth(startDate, endDate),
        getQueueHistory(startDate, endDate),
      ]);
      setStatus(statusRows);
      setMetrics(metricsData);
      setCategoryCount(categories.length);
      setAlerts(alertRows);
      setQueueStatus(queue);
      setDlqMessages(dlq);
      setCredentialHealth(health);
      setQueueHistory(queueHist);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate]);

  useEffect(() => {
    load();
  }, [load]);

  const handleRangeChange = (nextStart, nextEnd) => {
    setStartDate(nextStart);
    setEndDate(nextEnd);
  };

  // Window-scoped totals derived from the metrics buckets (already filtered
  // server-side to [startDate, endDate]) -- posts/comments scraped and avg
  // comments/post all reflect the selected window, not all-time. Combined
  // across every platform on purpose (a quick-scan total) -- the two
  // charts below show the same data split per platform.
  const windowTotals = useMemo(() => {
    const buckets = metrics?.buckets ?? [];
    const postsProcessed = buckets.reduce((sum, b) => sum + b.posts_processed, 0);
    const commentsProcessed = buckets.reduce((sum, b) => sum + b.comments_processed, 0);
    const avgCommentsPerPost = postsProcessed > 0 ? commentsProcessed / postsProcessed : 0;
    return { postsProcessed, commentsProcessed, avgCommentsPerPost };
  }, [metrics]);

  const filteredStatus = useMemo(
    () => (status ? status.filter((r) => selectedPlatforms.includes(r.platform)) : status),
    [status, selectedPlatforms],
  );

  const kpis = useMemo(() => {
    if (!filteredStatus) return null;
    const total = filteredStatus.length;
    const scraped = filteredStatus.filter((r) => r.last_job_status != null);
    const successes = scraped.filter((r) => r.last_job_status === 'completed').length;
    const successRate = scraped.length ? Math.round((successes / scraped.length) * 100) : 0;
    const backfilling = filteredStatus.filter((r) => !r.backfill_completed).length;
    return { total, successRate, backfilling };
  }, [filteredStatus]);

  const platformBreakdown = useMemo(() => {
    if (!status || !metrics) return null;
    return enabledPlatforms.map((platform) => platformBreakdownFor(status, metrics.buckets ?? [], platform));
  }, [status, metrics, enabledPlatforms]);

  if (error) {
    return <ErrorState title="Couldn't load dashboard data" description={error} onRetry={load} />;
  }

  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>Overview</h2>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
            Scrape status across every tracked influencer
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={load} loading={loading}>
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </Button>
      </div>

      <AlertsBanner alerts={alerts} />

      {/* Holistic cross-platform picture -- always shows every globally-
          enabled platform side by side, independent of the KPI row's own
          narrower filter below. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {(!platformBreakdown ? enabledPlatforms.map((p) => ({ platform: p })) : platformBreakdown).map((b) => (
          <div
            key={b.platform}
            className="card p-4 flex items-center gap-4"
          >
            <PlatformIcon platform={b.platform} className="w-11 h-11 rounded-xl shrink-0" />
            <div className="flex flex-col min-w-0 flex-1">
              <span className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                {platformLabel(b.platform)}
              </span>
              {b.total == null ? (
                <div className="h-4 w-32 mt-1 rounded animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
              ) : (
                <>
                  <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    {b.total} tracked · {b.successRate}% success · {b.backfilling} backfilling
                  </span>
                  <span className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                    {b.postsProcessed.toLocaleString()} posts · {b.commentsProcessed.toLocaleString()} comments (window)
                    {b.quotaUsed != null && ` · ${b.quotaUsed.toLocaleString()} quota units`}
                  </span>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <DateRangeSelector startDate={startDate} endDate={endDate} onChange={handleRangeChange} />
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium" style={{ color: 'var(--color-text-muted)' }}>Focus</span>
          <PlatformFilter value={selectedPlatforms} onChange={setSelectedPlatforms} options={enabledPlatforms} size="sm" />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {loading || !kpis ? (
          <>
            <SkeletonKPICard /><SkeletonKPICard /><SkeletonKPICard /><SkeletonKPICard /><SkeletonKPICard />
          </>
        ) : (
          <>
            <KPICard label="Tracked influencers" value={kpis.total} icon={<Users className="w-4 h-4" />} />
            <KPICard label="Categories" value={categoryCount ?? '—'} icon={<Layers className="w-4 h-4" />} />
            <KPICard
              label="Last-scrape success rate"
              value={`${kpis.successRate}%`}
              icon={<CheckCircle2 className="w-4 h-4" />}
              color={kpis.successRate >= 80 ? 'var(--color-success)' : 'var(--color-warning)'}
            />
            <KPICard
              label="Still backfilling"
              value={kpis.backfilling}
              icon={<Clock className="w-4 h-4" />}
              color={kpis.backfilling > 0 ? 'var(--color-warning)' : undefined}
            />
            <KPICard
              label="Queue depth"
              value={queueStatus?.main_depth != null ? `${queueStatus.main_depth}${queueStatus.dlq_depth ? ` (+${queueStatus.dlq_depth} DLQ)` : ''}` : 'n/a'}
              icon={<ListOrdered className="w-4 h-4" />}
              color={queueStatus?.dlq_depth > 0 ? 'var(--color-danger)' : undefined}
            />
          </>
        )}
      </div>

      {dlqMessages.length > 0 && (
        <div className="card p-5">
          <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--color-text-primary)' }}>
            Dead-letter queue contents
          </h3>
          <p className="text-xs mb-3" style={{ color: 'var(--color-text-muted)' }}>
            These jobs' workers died mid-run (OOM/crash) before cleaning up -- a different failure
            mode than a job that ran and failed normally. Check job history for each handle below.
          </p>
          <div className="flex flex-col gap-1.5">
            {dlqMessages.map((m) => (
              <div key={m.job_id} className="flex items-center gap-3 text-xs px-3 py-2 rounded-lg" style={{ background: 'var(--color-bg-secondary)' }}>
                <span className="font-medium" style={{ color: 'var(--color-text-primary)' }}>@{m.handle}</span>
                <span style={{ color: 'var(--color-text-muted)' }}>job {m.job_id}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {loading ? (
          <>
            <SkeletonKPICard /><SkeletonKPICard /><SkeletonKPICard />
          </>
        ) : (
          <>
            <KPICard label="Posts scraped (window, all platforms)" value={windowTotals.postsProcessed.toLocaleString()} icon={<FileText className="w-4 h-4" />} />
            <KPICard label="Comments scraped (window, all platforms)" value={windowTotals.commentsProcessed.toLocaleString()} icon={<MessageSquare className="w-4 h-4" />} />
            <KPICard label="Avg comments / post (window, all platforms)" value={windowTotals.avgCommentsPerPost.toFixed(1)} icon={<MessageSquare className="w-4 h-4" />} />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 min-w-0">
        <div className="card p-5 min-w-0">
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-primary)' }}>
            Jobs per day <span className="font-normal text-xs" style={{ color: 'var(--color-text-muted)' }}>by platform &amp; status</span>
          </h3>
          {loading ? <ChartSkeleton /> : <JobStatusChart buckets={metrics?.buckets ?? []} />}
        </div>
        <div className="card p-5 min-w-0">
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-primary)' }}>
            Throughput &amp; duration <span className="font-normal text-xs" style={{ color: 'var(--color-text-muted)' }}>by platform</span>
          </h3>
          {loading ? <ChartSkeleton /> : <PerformanceChart buckets={metrics?.buckets ?? []} />}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 min-w-0">
        {enabledPlatforms.map((platform) => (
          <div key={platform} className="card p-5 min-w-0">
            <h3 className="text-sm font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--color-text-primary)' }}>
              <PlatformIcon platform={platform} className="w-4 h-4 rounded" />
              {platformLabel(platform)} account/key health
              <span className="font-normal text-xs" style={{ color: 'var(--color-text-muted)' }}>
                {platform === 'youtube' ? '(quota exhaustion shown in amber)' : '(checkpoints shown in red)'}
              </span>
            </h3>
            {loading ? (
              <ChartSkeleton short />
            ) : (
              <CredentialHealthChart
                buckets={(credentialHealth?.buckets ?? []).filter((b) => b.platform === platform)}
              />
            )}
          </div>
        ))}
      </div>

      <div className="card p-5 min-w-0">
        <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-primary)' }}>
          Scrape queue depth <span className="font-normal text-xs" style={{ color: 'var(--color-text-muted)' }}>hourly, all platforms share one queue</span>
        </h3>
        {loading ? <ChartSkeleton short /> : <QueueDepthChart buckets={queueHistory?.buckets ?? []} />}
      </div>

      {loading ? (
        <div className="card p-5 h-64 animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
      ) : selectedPlatforms.length === 0 ? (
        <div className="card p-5">
          <p className="text-sm text-center py-8" style={{ color: 'var(--color-text-muted)' }}>
            Select at least one platform above ("Focus") to see its influencer status table.
          </p>
        </div>
      ) : (
        <StatusTable rows={filteredStatus ?? []} />
      )}
    </div>
  );
}

function ChartSkeleton({ short = false }) {
  return <div className={`${short ? 'h-56' : 'h-64'} rounded-lg animate-shimmer`} style={{ background: 'var(--color-bg-card-hover)' }} />;
}
