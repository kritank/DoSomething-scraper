import React, { useCallback, useEffect, useState } from 'react';
import { getCategories } from '../services/influencerService';
import { getDashboardStatus } from '../services/dashboardService';
import { getBenchmark, getRecommendations } from '../services/insightsService';
import EmptyState from '../components/common/EmptyState';
import KPICard from '../components/common/KPICard';

const PRIORITY_COLOR = {
  high: 'var(--color-danger)',
  medium: 'var(--color-warning)',
  low: 'var(--color-text-muted)',
};

function SelectBox({ value, onChange, options, placeholder }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-3 py-2.5 rounded-xl text-sm outline-none border min-w-[220px]"
      style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)', borderColor: 'var(--color-border-default)' }}
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>{o.label}</option>
      ))}
    </select>
  );
}

export default function Insights() {
  const [categories, setCategories] = useState([]);
  const [influencers, setInfluencers] = useState([]);

  const [categoryId, setCategoryId] = useState('');
  const [benchmark, setBenchmark] = useState(null);
  const [benchmarkLoading, setBenchmarkLoading] = useState(false);
  const [benchmarkMissing, setBenchmarkMissing] = useState(false);

  const [influencerId, setInfluencerId] = useState('');
  const [recommendations, setRecommendations] = useState(null);
  const [recommendationsLoading, setRecommendationsLoading] = useState(false);

  useEffect(() => {
    (async () => {
      const [cats, status] = await Promise.all([getCategories(), getDashboardStatus()]);
      setCategories(cats);
      setInfluencers(status.map((r) => ({ id: r.influencer_id, handle: r.handle })));
    })();
  }, []);

  const loadBenchmark = useCallback(async (id) => {
    if (!id) { setBenchmark(null); setBenchmarkMissing(false); return; }
    setBenchmarkLoading(true);
    setBenchmarkMissing(false);
    try {
      setBenchmark(await getBenchmark(id));
    } catch {
      setBenchmark(null);
      setBenchmarkMissing(true);
    } finally {
      setBenchmarkLoading(false);
    }
  }, []);

  const loadRecommendations = useCallback(async (id) => {
    if (!id) { setRecommendations(null); return; }
    setRecommendationsLoading(true);
    try {
      setRecommendations(await getRecommendations(id));
    } catch {
      setRecommendations([]);
    } finally {
      setRecommendationsLoading(false);
    }
  }, []);

  const handleCategoryChange = (id) => {
    setCategoryId(id);
    loadBenchmark(id);
  };

  const handleInfluencerChange = (id) => {
    setInfluencerId(id);
    loadRecommendations(id);
  };

  return (
    <div className="flex flex-col gap-8 min-w-0">
      <div>
        <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>Insights</h2>
        <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
          Category benchmarks and per-influencer recommendations
        </p>
      </div>

      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>Category benchmark</h3>
          <SelectBox
            value={categoryId}
            onChange={handleCategoryChange}
            options={categories.map((c) => ({ id: c.id, label: c.name }))}
            placeholder="Select a category…"
          />
        </div>

        {!categoryId ? (
          <div className="card p-5">
            <EmptyState title="Pick a category" message="Select a category above to see its benchmark." />
          </div>
        ) : benchmarkLoading ? (
          <div className="card p-5 h-32 animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
        ) : benchmarkMissing ? (
          <div className="card p-5">
            <EmptyState
              title="Not yet computed for this category"
              message="Benchmark aggregation isn't implemented yet -- this page is wired up and ready for when it is."
            />
          </div>
        ) : benchmark ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard label="Avg followers" value={benchmark.avg_followers.toLocaleString()} />
            <KPICard label="Avg engagement rate" value={`${(benchmark.avg_engagement_rate * 100).toFixed(2)}%`} />
            <KPICard label="Median engagement rate" value={`${(benchmark.median_engagement_rate * 100).toFixed(2)}%`} />
            <KPICard label="Avg posts / week" value={benchmark.avg_posting_freq_week.toFixed(1)} />
            <KPICard label="Avg caption length" value={benchmark.avg_caption_length} />
            <KPICard label="Avg hashtags / post" value={benchmark.avg_hashtag_count.toFixed(1)} />
            <KPICard label="Best posting hour" value={`${benchmark.best_posting_hour}:00`} />
            <KPICard label="Sample size" value={benchmark.sample_size} />
          </div>
        ) : null}
      </section>

      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>Influencer recommendations</h3>
          <SelectBox
            value={influencerId}
            onChange={handleInfluencerChange}
            options={influencers.map((i) => ({ id: i.id, label: `@${i.handle}` }))}
            placeholder="Select an influencer…"
          />
        </div>

        {!influencerId ? (
          <div className="card p-5">
            <EmptyState title="Pick an influencer" message="Select an influencer above to see their recommendations." />
          </div>
        ) : recommendationsLoading ? (
          <div className="card p-5 h-32 animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
        ) : recommendations && recommendations.length === 0 ? (
          <div className="card p-5">
            <EmptyState
              title="No recommendations yet"
              message="Recommendation generation isn't implemented yet -- this page is wired up and ready for when it is."
            />
          </div>
        ) : recommendations ? (
          <div className="flex flex-col gap-3">
            {recommendations.map((r) => (
              <div key={r.id} className="card p-4 flex flex-col gap-1.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium text-sm" style={{ color: 'var(--color-text-primary)' }}>{r.title}</span>
                  <span
                    className="text-xs font-medium px-2 py-0.5 rounded-full"
                    style={{ color: PRIORITY_COLOR[r.priority] ?? 'var(--color-text-muted)', background: 'rgba(255,255,255,0.06)' }}
                  >
                    {r.priority}
                  </span>
                </div>
                <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>{r.body}</p>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
