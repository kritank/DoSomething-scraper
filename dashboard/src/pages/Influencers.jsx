import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PlayCircle, RefreshCw } from 'lucide-react';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { getDashboardStatus } from '../services/dashboardService';
import { getCategories, triggerScrape } from '../services/influencerService';
import StatusBadge from '../components/common/StatusBadge';
import Button from '../components/common/Button';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import AddCategoryForm from '../components/influencers/AddCategoryForm';
import AddInfluencerForm from '../components/influencers/AddInfluencerForm';

const IN_FLIGHT_STATUSES = new Set(['queued', 'running']);

export default function Influencers() {
  const [categories, setCategories] = useState([]);
  const [statusRows, setStatusRows] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(() => new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cats, rows] = await Promise.all([getCategories(), getDashboardStatus()]);
      setCategories(cats);
      setStatusRows(rows);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => {
    const byCategory = new Map(categories.map((c) => [c.id, { category: c, influencers: [] }]));
    for (const row of statusRows) {
      if (!byCategory.has(row.category_id)) {
        byCategory.set(row.category_id, { category: { id: row.category_id, name: row.category_name }, influencers: [] });
      }
      byCategory.get(row.category_id).influencers.push(row);
    }
    return [...byCategory.values()].sort((a, b) => a.category.name.localeCompare(b.category.name));
  }, [categories, statusRows]);

  const handleScrapeNow = async (row) => {
    setTriggering((prev) => new Set(prev).add(row.influencer_id));
    try {
      await triggerScrape(row.influencer_id);
      toast.success(`Scrape queued for @${row.handle}`);
      // Optimistic update -- avoids waiting on a full refetch to reflect
      // the click, since the actual job may sit behind others in the
      // single-account queue for a while.
      setStatusRows((rows) =>
        rows.map((r) => (r.influencer_id === row.influencer_id ? { ...r, last_job_status: 'queued' } : r)),
      );
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

  if (error) {
    return <ErrorState title="Couldn't load influencers" description={error} onRetry={load} />;
  }

  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>Influencers</h2>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
            Add categories/influencers and trigger manual scrapes
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={load} loading={loading}>
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </Button>
      </div>

      <div className="card p-5 flex flex-col gap-5">
        <AddCategoryForm onCreated={load} />
        <div style={{ borderTop: '1px solid var(--color-border-subtle)' }} />
        <AddInfluencerForm categories={categories} onCreated={load} />
      </div>

      {loading ? (
        <div className="card p-5 h-64 animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
      ) : grouped.length === 0 ? (
        <EmptyState title="No categories yet" message="Add your first category above to get started." />
      ) : (
        <div className="flex flex-col gap-4">
          {grouped.map(({ category, influencers }) => (
            <div key={category.id} className="card p-5 flex flex-col gap-3 min-w-0">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                {category.name} <span style={{ color: 'var(--color-text-muted)' }}>({influencers.length})</span>
              </h3>

              {influencers.length === 0 ? (
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>No influencers in this category yet.</p>
              ) : (
                <div className="flex flex-col divide-y" style={{ borderColor: 'var(--color-border-subtle)' }}>
                  {influencers.map((row) => {
                    const isInFlight = triggering.has(row.influencer_id) || IN_FLIGHT_STATUSES.has(row.last_job_status);
                    return (
                      <div
                        key={row.influencer_id}
                        className="flex items-center justify-between gap-3 py-2.5 flex-wrap"
                        style={{ borderColor: 'var(--color-border-subtle)' }}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="font-medium text-sm truncate" style={{ color: 'var(--color-text-primary)' }}>
                            @{row.handle}
                          </span>
                          <StatusBadge status={row.last_job_status} />
                        </div>
                        <div className="flex items-center gap-4 shrink-0">
                          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                            {row.last_job_finished_at
                              ? `Last scraped ${format(new Date(row.last_job_finished_at), 'MMM d, HH:mm')}`
                              : 'Never scraped'}
                          </span>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => handleScrapeNow(row)}
                            loading={triggering.has(row.influencer_id)}
                            disabled={isInFlight}
                          >
                            <PlayCircle className="w-3.5 h-3.5" />
                            Scrape now
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
