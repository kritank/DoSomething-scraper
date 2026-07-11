import React, { useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import Input from '../common/Input';
import Button from '../common/Button';
import { createInfluencer } from '../../services/influencerService';

export default function AddInfluencerForm({ categories, onCreated }) {
  const [handle, setHandle] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [scrapePostsSince, setScrapePostsSince] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const effectiveCategoryId = categoryId || categories[0]?.id || '';

  const handleSubmit = async (e) => {
    e.preventDefault();
    const cleanHandle = handle.trim().replace(/^@/, '');
    if (!cleanHandle || !effectiveCategoryId || submitting) return;
    setSubmitting(true);
    try {
      await createInfluencer(cleanHandle, effectiveCategoryId, scrapePostsSince);
      toast.success(`@${cleanHandle} added`);
      setHandle('');
      setScrapePostsSince('');
      onCreated();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-3 flex-wrap">
      <div className="flex-1 min-w-[160px]">
        <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
          Instagram handle
        </label>
        <Input placeholder="username" value={handle} onChange={(e) => setHandle(e.target.value)} />
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

      <Button type="submit" size="md" loading={submitting} disabled={!handle.trim() || !effectiveCategoryId}>
        <Plus className="w-3.5 h-3.5" />
        Add influencer
      </Button>
    </form>
  );
}
