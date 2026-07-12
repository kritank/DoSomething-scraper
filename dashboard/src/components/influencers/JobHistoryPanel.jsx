import React, { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { getInfluencerJobs } from '../../services/influencerJobsService';
import StatusBadge from '../common/StatusBadge';
import LoadingSpinner from '../common/LoadingSpinner';
import EmptyState from '../common/EmptyState';

function formatDuration(s) {
  if (s == null) return '—';
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

export default function JobHistoryPanel({ influencerId }) {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getInfluencerJobs(influencerId);
        if (!cancelled) setJobs(data);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => { cancelled = true; };
  }, [influencerId]);

  if (error) {
    return <p className="text-xs px-3 py-2" style={{ color: 'var(--color-danger)' }}>{error}</p>;
  }

  if (!jobs) {
    return (
      <div className="flex items-center justify-center py-4">
        <LoadingSpinner size="sm" />
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <div className="py-2">
        <EmptyState title="No runs yet" message="This influencer hasn't been scraped." />
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg" style={{ background: 'var(--color-bg-secondary)' }}>
      <table className="w-full text-xs">
        <thead>
          <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
            {['Status', 'Started', 'Duration', 'Posts', 'Comments', 'Retries', 'Error'].map((h) => (
              <th key={h} className="text-left py-2 px-3 font-medium whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id} style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
              <td className="py-2 px-3"><StatusBadge status={job.status} /></td>
              <td className="py-2 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                {job.started_at ? format(new Date(job.started_at), 'MMM d, HH:mm') : '—'}
              </td>
              <td className="py-2 px-3" style={{ color: 'var(--color-text-secondary)' }}>{formatDuration(job.duration_s)}</td>
              <td className="py-2 px-3" style={{ color: 'var(--color-text-secondary)' }}>{job.posts_processed}</td>
              <td className="py-2 px-3" style={{ color: 'var(--color-text-secondary)' }}>{job.comments_processed}</td>
              <td className="py-2 px-3" style={{ color: 'var(--color-text-secondary)' }}>{job.retry_count}</td>
              <td className="py-2 px-3 max-w-[240px] truncate" style={{ color: 'var(--color-text-muted)' }} title={job.error_message ?? undefined}>
                {job.error_message ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
