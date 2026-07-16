import React, { useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import { format, startOfYear } from 'date-fns';
import Input from '../common/Input';
import Button from '../common/Button';
import { cn } from '../../utils/cn';
import { formatHandle } from '../../utils/platform';
import { createInfluencer } from '../../services/influencerService';

// Jan 1 of the current year -- a sensible default backfill boundary so a
// new influencer doesn't silently pull years of history unless someone
// deliberately clears this field.
function defaultScrapeSince() {
  return format(startOfYear(new Date()), 'yyyy-MM-dd');
}

const PLATFORMS = [
  { id: 'instagram', label: 'Instagram' },
  { id: 'youtube', label: 'YouTube' },
];

export default function AddInfluencerForm({ categories, creators = [], onCreated }) {
  const [platform, setPlatform] = useState('instagram');
  const [handle, setHandle] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [creatorName, setCreatorName] = useState('');
  const [scrapePostsSince, setScrapePostsSince] = useState(defaultScrapeSince);
  const [submitting, setSubmitting] = useState(false);

  const effectiveCategoryId = categoryId || categories[0]?.id || '';

  // Case-insensitive match against existing creators -- mirrors the
  // backend's own get-or-create-by-name matching (CreatorRepo), so the
  // hint shown here always agrees with what registering will actually do.
  const matchedCreator = creatorName.trim()
    ? creators.find((c) => c.name.toLowerCase() === creatorName.trim().toLowerCase())
    : null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    // Backend normalizes the final form (bare name / "@name" / a full
    // channel URL all resolve the same way for YouTube -- see
    // InfluencerRepo.normalize_handle) -- stripping a leading "@" here is
    // just tidying up the common case, not the only accepted input.
    const cleanHandle = handle.trim().replace(/^@/, '');
    if (!cleanHandle || !effectiveCategoryId || submitting) return;
    setSubmitting(true);
    try {
      const created = await createInfluencer(
        cleanHandle, effectiveCategoryId, scrapePostsSince, platform, creatorName.trim(),
      );
      toast.success(`${formatHandle(created.handle, created.platform)} added`);
      setHandle('');
      setCreatorName('');
      setScrapePostsSince(defaultScrapeSince());
      onCreated();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <div className="flex gap-2">
        {PLATFORMS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setPlatform(p.id)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
              platform === p.id ? 'text-white' : '',
            )}
            style={{
              background: platform === p.id ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
              color: platform === p.id ? 'white' : 'var(--color-text-secondary)',
              border: '1px solid ' + (platform === p.id ? 'var(--color-accent)' : 'var(--color-border-default)'),
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="flex items-end gap-3 flex-wrap">
        <div className="flex-1 min-w-[160px]">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            {platform === 'youtube' ? 'YouTube channel' : 'Instagram handle'}
          </label>
          <Input
            placeholder={platform === 'youtube' ? '@handle, name, or channel URL' : 'username'}
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
          />
        </div>

        <div className="min-w-[180px]">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            Category
          </label>
          <select
            value={effectiveCategoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            className="w-full px-3.5 py-2.5 rounded-xl text-sm outline-none border"
            style={{
              background: 'var(--color-bg-secondary)',
              color: 'var(--color-text-primary)',
              borderColor: 'var(--color-border-default)',
            }}
          >
            {categories.length === 0 && <option value="">No categories yet</option>}
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        <div className="min-w-[150px]">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            Scrape posts since <span style={{ color: 'var(--color-text-muted)' }}>(optional)</span>
          </label>
          <Input type="date" value={scrapePostsSince} onChange={(e) => setScrapePostsSince(e.target.value)} />
        </div>

        <div className="min-w-[180px] flex-1">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            Creator <span style={{ color: 'var(--color-text-muted)' }}>(optional -- links platforms together)</span>
          </label>
          <Input
            list="creator-name-options"
            placeholder="e.g. MrBeast"
            value={creatorName}
            onChange={(e) => setCreatorName(e.target.value)}
          />
          <datalist id="creator-name-options">
            {creators.map((c) => (
              <option key={c.id} value={c.name} />
            ))}
          </datalist>
        </div>

        <Button type="submit" size="md" loading={submitting} disabled={!handle.trim() || !effectiveCategoryId}>
          <Plus className="w-3.5 h-3.5" />
          Add influencer
        </Button>
      </div>

      {matchedCreator && (
        <p className="text-xs" style={{ color: 'var(--color-accent)' }}>
          Links to the existing creator "{matchedCreator.name}"
          {matchedCreator.platforms.length > 0 && ` (already on ${matchedCreator.platforms.join(', ')})`} --
          the same person/brand will show as one cross-platform entry.
        </p>
      )}
    </form>
  );
}
