import React, { useState } from 'react';
import { ExternalLink, Copy, Check } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import Skeleton from '../common/Skeleton';
import EmptyState from '../common/EmptyState';

function CopyableId({ value }) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span>—</span>;
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      }}
      className="inline-flex items-center gap-1 font-mono text-xs hover:underline"
      style={{ color: 'var(--color-text-primary)' }}
      title="Copy"
    >
      {value}
      {copied ? <Check className="w-3 h-3" style={{ color: 'var(--color-success)' }} /> : <Copy className="w-3 h-3" style={{ color: 'var(--color-text-muted)' }} />}
    </button>
  );
}

function MetaRow({ label, value }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="flex items-center justify-between gap-3 py-1.5" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
      <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{label}</span>
      <span className="text-xs font-medium text-right" style={{ color: 'var(--color-text-primary)' }}>{value}</span>
    </div>
  );
}

function ChipList({ items, max = 10 }) {
  const [expanded, setExpanded] = useState(false);
  if (!items || items.length === 0) return null;
  const shown = expanded ? items : items.slice(0, max);
  return (
    <div className="flex flex-wrap gap-1.5">
      {shown.map((item) => (
        <span
          key={item}
          className="px-2 py-0.5 rounded-full text-xs"
          style={{ background: 'var(--color-bg-card-hover)', color: 'var(--color-text-secondary)' }}
        >
          {item}
        </span>
      ))}
      {!expanded && items.length > max && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="px-2 py-0.5 rounded-full text-xs hover:underline"
          style={{ color: 'var(--color-accent)' }}
        >
          +{items.length - max} more
        </button>
      )}
    </div>
  );
}

export default function AboutSection({ about, loading, isYoutube }) {
  const [descExpanded, setDescExpanded] = useState(false);

  if (loading) {
    return (
      <div className="card p-5 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!about || (!about.description && !about.platform_user_id)) {
    return (
      <div className="card p-5">
        <EmptyState title="No profile info yet" message="About details appear here after the next scrape." />
      </div>
    );
  }

  const links = [about.external_url, ...about.bio_links].filter(Boolean);
  const description = about.description || '';
  const isLong = description.split('\n').length > 6 || description.length > 400;

  return (
    <div className="card p-5 grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="flex flex-col gap-3 min-w-0">
        <h4 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--color-text-muted)' }}>Description</h4>
        {description ? (
          <p
            className="text-sm whitespace-pre-wrap"
            style={{
              color: 'var(--color-text-secondary)',
              display: '-webkit-box',
              WebkitLineClamp: isLong && !descExpanded ? 6 : 'unset',
              WebkitBoxOrient: 'vertical',
              overflow: isLong && !descExpanded ? 'hidden' : 'visible',
            }}
          >
            {description}
          </p>
        ) : (
          <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>No description provided.</p>
        )}
        {isLong && (
          <button
            type="button"
            onClick={() => setDescExpanded((v) => !v)}
            className="text-xs font-medium self-start hover:underline"
            style={{ color: 'var(--color-accent)' }}
          >
            {descExpanded ? 'Show less' : 'Show more'}
          </button>
        )}

        {links.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-1">
            {links.map((link) => (
              <a
                key={link}
                href={link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs hover:underline"
                style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)' }}
              >
                <ExternalLink className="w-3 h-3" />
                {link.replace(/^https?:\/\//, '').slice(0, 40)}
              </a>
            ))}
          </div>
        )}

        {about.topics.length > 0 && (
          <div className="mt-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--color-text-muted)' }}>Topics</h4>
            <ChipList items={about.topics} />
          </div>
        )}
        {about.keywords.length > 0 && (
          <div className="mt-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--color-text-muted)' }}>Keywords</h4>
            <ChipList items={about.keywords} />
          </div>
        )}
      </div>

      <div className="flex flex-col min-w-0">
        <h4 className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--color-text-muted)' }}>Details</h4>
        <MetaRow label="Country" value={about.country} />
        <MetaRow
          label="Created on platform"
          value={about.created_at_platform ? format(parseISO(about.created_at_platform), 'MMM d, yyyy') : null}
        />
        <MetaRow label="Business category" value={about.business_category} />
        <MetaRow label="Verified" value={about.is_verified ? 'Yes' : null} />
        <MetaRow label="Business account" value={about.is_business_account ? 'Yes' : null} />
        <MetaRow label="Made for kids" value={about.made_for_kids === null || about.made_for_kids === undefined ? null : (about.made_for_kids ? 'Yes' : 'No')} />
        <div className="flex items-center justify-between gap-3 py-1.5">
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{isYoutube ? 'Channel ID' : 'Account ID'}</span>
          <CopyableId value={about.platform_user_id} />
        </div>
      </div>
    </div>
  );
}
