import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Users, CheckCircle2, Clock, FileText, MessageSquare, Layers, ListOrdered, RefreshCw } from 'lucide-react';
import { format, subDays } from 'date-fns';
import { getDashboardStatus, getDashboardMetrics, getAlerts, getQueueStatus, getDlqContents } from '../services/dashboardService';
import { getCategories } from '../services/influencerService';
import KPICard from '../components/common/KPICard';
import { SkeletonKPICard } from '../components/common/Skeleton';
import ErrorState from '../components/common/ErrorState';
import Button from '../components/common/Button';
import JobStatusChart from '../components/charts/JobStatusChart';
import PerformanceChart from '../components/charts/PerformanceChart';
import StatusTable from '../components/dashboard/StatusTable';
import DateRangeSelector from '../components/dashboard/DateRangeSelector';
import AlertsBanner from '../components/dashboard/AlertsBanner';

function toIso(d) {
  return format(d, 'yyyy-MM-dd');
}

export default function Overview() {
  const [status, setStatus] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [categoryCount, setCategoryCount] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [queueStatus, setQueueStatus] = useState(null);
  const [dlqMessages, setDlqMessages] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const [startDate, setStartDate] = useState(() => toIso(subDays(new Date(), 29)));
  const [endDate, setEndDate] = useState(() => toIso(new Date()));

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRows, metricsData, categories, alertRows, queue, dlq] = await Promise.all([
        getDashboardStatus(),
        getDashboardMetrics(startDate, endDate),
        getCategories(),
        getAlerts(),
        getQueueStatus(),
        getDlqContents(),
      ]);
      setStatus(statusRows);
      setMetrics(metricsData);
      setCategoryCount(categories.length);
      setAlerts(alertRows);
      setQueueStatus(queue);
      setDlqMessages(dlq);
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
  // comments/post all reflect the selected window, not all-time.
  const windowTotals = useMemo(() => {
    const buckets = metrics?.buckets ?? [];
    const postsProcessed = buckets.reduce((sum, b) => sum + b.posts_processed, 0);
    const commentsProcessed = buckets.reduce((sum, b) => sum + b.comments_processed, 0);
    const avgCommentsPerPost = postsProcessed > 0 ? commentsProcessed / postsProcessed : 0;
    return { postsProcessed, commentsProcessed, avgCommentsPerPost };
  }, [metrics]);

  const kpis = useMemo(() => {
    if (!status) return null;
    const total = status.length;
    const scraped = status.filter((r) => r.last_job_status != null);
    const successes = scraped.filter((r) => r.last_job_status === 'completed').length;
    const successRate = scraped.length ? Math.round((successes / scraped.length) * 100) : 0;
    const backfilling = status.filter((r) => !r.backfill_completed).length;
    return { total, successRate, backfilling };
  }, [status]);

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

      <DateRangeSelector startDate={startDate} endDate={endDate} onChange={handleRangeChange} />

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
            <KPICard label="Posts scraped (window)" value={windowTotals.postsProcessed.toLocaleString()} icon={<FileText className="w-4 h-4" />} />
            <KPICard label="Comments scraped (window)" value={windowTotals.commentsProcessed.toLocaleString()} icon={<MessageSquare className="w-4 h-4" />} />
            <KPICard label="Avg comments / post (window)" value={windowTotals.avgCommentsPerPost.toFixed(1)} icon={<MessageSquare className="w-4 h-4" />} />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 min-w-0">
        <div className="card p-5 min-w-0">
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-primary)' }}>
            Jobs per day
          </h3>
          {loading ? <ChartSkeleton /> : <JobStatusChart buckets={metrics?.buckets ?? []} />}
        </div>
        <div className="card p-5 min-w-0">
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-primary)' }}>
            Throughput &amp; duration
          </h3>
          {loading ? <ChartSkeleton /> : <PerformanceChart buckets={metrics?.buckets ?? []} />}
        </div>
      </div>

      {loading ? (
        <div className="card p-5 h-64 animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
      ) : (
        <StatusTable rows={status ?? []} />
      )}
    </div>
  );
}

function ChartSkeleton() {
  return <div className="h-64 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />;
}
