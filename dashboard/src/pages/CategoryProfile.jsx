import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, ChevronDown, ChevronUp, RefreshCw, Link2, Briefcase, User, Users, PowerOff } from 'lucide-react';
import { format } from 'date-fns';
import { getCategories } from '../services/influencerService';
import { getDashboardStatus } from '../services/dashboardService';
import Button from '../components/common/Button';
import HeaderPill from '../components/common/HeaderPill';
import EmptyState from '../components/common/EmptyState';
import ErrorState from '../components/common/ErrorState';
import Skeleton from '../components/common/Skeleton';
import PlatformBadge from '../components/common/PlatformBadge';
import StatusBadge from '../components/common/StatusBadge';
import { formatHandle } from '../utils/platform';
import { groupByCreator } from '../utils/groupByCreator';

const TYPE_SECTIONS = [
  { key: 'business', label: 'Business', icon: Briefcase },
  { key: 'individual', label: 'Individual', icon: User },
];

export default function CategoryProfile() {
  const { categoryId } = useParams();

  const [category, setCategory] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState(null);
  // Presence means expanded -- both default empty so every type-section
  // and creator group starts collapsed, same convention as Influencers.jsx.
  const [expandedSections, setExpandedSections] = useState(() => new Set());
  const [expandedGroups, setExpandedGroups] = useState(() => new Set());

  const toggleSectionExpanded = (key) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const toggleGroupExpanded = (key) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      const [categories, status] = await Promise.all([getCategories(), getDashboardStatus()]);
      const found = categories.find((c) => c.id === categoryId);
      if (!found) {
        setNotFound(true);
        return;
      }
      setCategory(found);
      setRows(status.filter((r) => r.category_id === categoryId));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [categoryId]);

  useEffect(() => {
    load();
  }, [load]);

  const byType = useMemo(() => {
    const grouped = { business: [], individual: [] };
    for (const row of rows) {
      (grouped[row.account_type] ?? grouped.individual).push(row);
    }
    return grouped;
  }, [rows]);

  if (notFound) {
    return <EmptyState title="Category not found" message="This category may have been deleted." />;
  }
  if (error) {
    return <ErrorState title="Couldn't load category" description={error} onRetry={load} />;
  }

  return (
    <div className="flex flex-col gap-8 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/influencers">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="w-3.5 h-3.5" />
              Back
            </Button>
          </Link>
          <div className="min-w-0">
            <h2 className="text-xl font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
              {loading ? 'Loading…' : category?.name}
            </h2>
            {!loading && category && (
              <div className="flex items-center flex-wrap gap-1.5 mt-1.5">
                <HeaderPill icon={Users}>{rows.length} account{rows.length === 1 ? '' : 's'}</HeaderPill>
                <HeaderPill icon={Briefcase}>{byType.business.length} business</HeaderPill>
                <HeaderPill icon={User}>{byType.individual.length} individual</HeaderPill>
                {category.is_active === false && (
                  <HeaderPill icon={PowerOff}>inactive</HeaderPill>
                )}
              </div>
            )}
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={load} loading={loading}>
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState title="No accounts yet" message="This category has no scraped accounts." />
      ) : (
        <div className="flex flex-col gap-6">
          {TYPE_SECTIONS.map(({ key, label, icon: Icon }) => (
            <div key={key} className="card p-5 flex flex-col gap-3 min-w-0">
              <button
                onClick={() => toggleSectionExpanded(key)}
                className="flex items-center gap-1.5 text-left"
              >
                <Icon className="w-4 h-4" style={{ color: 'var(--color-text-muted)' }} />
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                  {label} <span style={{ color: 'var(--color-text-muted)' }}>({byType[key].length})</span>
                </h3>
                {expandedSections.has(key) ? (
                  <ChevronUp className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                )}
              </button>
              {byType[key].length === 0 ? (
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>None in this category.</p>
              ) : !expandedSections.has(key) ? null : (
                <div className="flex flex-col gap-2">
                  {groupByCreator(byType[key]).map((group) => (
                    <CategoryAccountGroup
                      key={group.key}
                      group={group}
                      expanded={expandedGroups.has(group.key)}
                      onToggleExpanded={() => toggleGroupExpanded(group.key)}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CategoryAccountGroup({ group, expanded, onToggleExpanded }) {
  // Solo (unlinked) groups are a single row with no header of their own --
  // nothing to collapse, so they always render their row directly.
  const collapsible = Boolean(group.creatorId);
  return (
    <div
      className="rounded-xl p-3 flex flex-col gap-1.5"
      style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}
    >
      {group.creatorId && (
        <button onClick={onToggleExpanded} className="flex items-center gap-1.5 px-1 text-left">
          <Link2 className="w-3 h-3 shrink-0" style={{ color: 'var(--color-accent)' }} />
          <Link
            to={`/creators/${group.creatorId}`}
            onClick={(e) => e.stopPropagation()}
            className="text-xs font-semibold hover:underline"
            style={{ color: 'var(--color-accent)' }}
          >
            {group.creatorName}
          </Link>
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            — linked across {group.rows.length} platform{group.rows.length === 1 ? '' : 's'}
          </span>
          {expanded ? (
            <ChevronUp className="w-3 h-3 ml-auto" style={{ color: 'var(--color-text-muted)' }} />
          ) : (
            <ChevronDown className="w-3 h-3 ml-auto" style={{ color: 'var(--color-text-muted)' }} />
          )}
        </button>
      )}
      {(!collapsible || expanded) && (
      <div className="flex flex-col divide-y" style={{ borderColor: 'var(--color-border-subtle)' }}>
        {group.rows.map((row) => (
          <div key={row.influencer_id} className="flex items-center justify-between gap-3 flex-wrap py-2 first:pt-0 last:pb-0">
            <div className="flex items-center gap-3 min-w-0">
              <Link
                to={group.creatorId ? `/creators/${group.creatorId}` : `/influencers/${row.influencer_id}`}
                className="font-medium text-sm truncate hover:underline"
                style={{ color: 'var(--color-text-primary)' }}
              >
                {formatHandle(row.handle, row.platform)}
              </Link>
              <PlatformBadge platform={row.platform} handle={row.handle} />
              <StatusBadge status={row.last_job_status} />
              {!row.is_active && (
                <HeaderPill icon={PowerOff}>
                  {row.paused_by_category ? 'held with category' : 'inactive'}
                </HeaderPill>
              )}
            </div>
            <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              {row.last_job_finished_at
                ? `Last scraped ${format(new Date(row.last_job_finished_at), 'MMM d, HH:mm')}`
                : 'Never scraped'}
            </span>
          </div>
        ))}
      </div>
      )}
    </div>
  );
}
