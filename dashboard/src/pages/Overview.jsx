import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Users, CheckCircle2, Clock, FileText, RefreshCw } from 'lucide-react';
import { getDashboardStatus, getDashboardMetrics } from '../services/dashboardService';
import KPICard from '../components/common/KPICard';
import { SkeletonKPICard } from '../components/common/Skeleton';
import ErrorState from '../components/common/ErrorState';
import Button from '../components/common/Button';
import JobStatusChart from '../components/charts/JobStatusChart';
import PerformanceChart from '../components/charts/PerformanceChart';
import StatusTable from '../components/dashboard/StatusTable';

export default function Overview() {
  const [status, setStatus] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRows, metricsData] = await Promise.all([
        getDashboardStatus(),
        getDashboardMetrics(30),
      ]);
      setStatus(statusRows);
      setMetrics(metricsData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const kpis = useMemo(() => {
    if (!status) return null;
    const total = status.length;
    const scraped = status.filter((r) => r.last_job_status != null);
    const successes = scraped.filter((r) => r.last_job_status === 'completed').length;
    const successRate = scraped.length ? Math.round((successes / scraped.length) * 100) : 0;
    const totalPosts = status.reduce((sum, r) => sum + (r.last_job_posts_processed ?? 0), 0);
    const backfilling = status.filter((r) => !r.backfill_completed).length;
    return { total, successRate, totalPosts, backfilling };
  }, [status]);

  if (error) {
    return <ErrorState title="Couldn't load dashboard data" description={error} onRetry={load} />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
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

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading || !kpis ? (
          <>
            <SkeletonKPICard /><SkeletonKPICard /><SkeletonKPICard /><SkeletonKPICard />
          </>
        ) : (
          <>
            <KPICard label="Tracked influencers" value={kpis.total} icon={<Users className="w-4 h-4" />} />
            <KPICard
              label="Last-scrape success rate"
              value={`${kpis.successRate}%`}
              icon={<CheckCircle2 className="w-4 h-4" />}
              color={kpis.successRate >= 80 ? 'var(--color-success)' : 'var(--color-warning)'}
            />
            <KPICard label="Total posts scraped" value={kpis.totalPosts.toLocaleString()} icon={<FileText className="w-4 h-4" />} />
            <KPICard
              label="Still backfilling"
              value={kpis.backfilling}
              icon={<Clock className="w-4 h-4" />}
              color={kpis.backfilling > 0 ? 'var(--color-warning)' : undefined}
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-5">
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-primary)' }}>
            Jobs per day (last 30 days)
          </h3>
          {loading ? <ChartSkeleton /> : <JobStatusChart buckets={metrics?.buckets ?? []} />}
        </div>
        <div className="card p-5">
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
