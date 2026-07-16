import React, { useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import Input from '../common/Input';
import Button from '../common/Button';
import { registerYoutubeKey } from '../../services/youtubeKeysService';

export default function AddYoutubeKeyForm({ onRegistered, initialLabel, lockLabel = false }) {
  const [label, setLabel] = useState(initialLabel ?? '');
  const [apiKey, setApiKey] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    const cleanLabel = label.trim();
    const cleanKey = apiKey.trim();
    if (!cleanLabel || !cleanKey) return;

    setSubmitting(true);
    try {
      await registerYoutubeKey({ label: cleanLabel, apiKey: cleanKey });
      toast.success(lockLabel ? `"${cleanLabel}" rotated` : `"${cleanLabel}" added and active`);
      setLabel('');
      setApiKey('');
      onRegistered();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit = label.trim() && apiKey.trim();

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex items-end gap-3 flex-wrap">
        <div className="min-w-[160px]">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            Label
          </label>
          <Input
            placeholder="e.g. gcp-project-1"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            disabled={lockLabel}
          />
        </div>

        <div className="min-w-[280px] flex-1">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            API key
          </label>
          <Input
            type="password"
            placeholder="AIza..."
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>

        <Button type="submit" size="md" loading={submitting} disabled={!canSubmit}>
          <Plus className="w-3.5 h-3.5" />
          {lockLabel ? 'Rotate' : 'Add key'}
        </Button>
      </div>

      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
        {lockLabel
          ? 'Re-registering this label updates its key in place (upsert-by-label) and resets today\'s quota counter -- this does not create a second key.'
          : 'Generate a key in Google Cloud Console (APIs & Services → Credentials) with the YouTube Data API v3 enabled. Stored encrypted at rest -- not validated until its first real use, so a bad key surfaces as "invalid" after its first failed call rather than being caught here.'}
      </p>
    </form>
  );
}
