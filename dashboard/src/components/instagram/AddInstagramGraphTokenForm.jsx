import React, { useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import Input from '../common/Input';
import Button from '../common/Button';
import { registerInstagramGraphToken } from '../../services/instagramGraphTokensService';

export default function AddInstagramGraphTokenForm({ onRegistered, initialLabel, lockLabel = false }) {
  const [label, setLabel] = useState(initialLabel ?? '');
  const [accessToken, setAccessToken] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    const cleanLabel = label.trim();
    const cleanToken = accessToken.trim();
    if (!cleanLabel || !cleanToken) return;

    setSubmitting(true);
    try {
      await registerInstagramGraphToken({ label: cleanLabel, accessToken: cleanToken });
      toast.success(lockLabel ? `"${cleanLabel}" rotated` : `"${cleanLabel}" added and active`);
      setLabel('');
      setAccessToken('');
      onRegistered();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit = label.trim() && accessToken.trim();

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex items-end gap-3 flex-wrap">
        <div className="min-w-[160px]">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            Label
          </label>
          <Input
            placeholder="e.g. meta-business-1"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            disabled={lockLabel}
          />
        </div>

        <div className="min-w-[280px] flex-1">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            Access token
          </label>
          <Input
            type="password"
            placeholder="EAAB..."
            value={accessToken}
            onChange={(e) => setAccessToken(e.target.value)}
          />
        </div>

        <Button type="submit" size="md" loading={submitting} disabled={!canSubmit}>
          <Plus className="w-3.5 h-3.5" />
          {lockLabel ? 'Rotate' : 'Add token'}
        </Button>
      </div>

      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
        {lockLabel
          ? 'Re-registering this label updates its token in place (upsert-by-label) and resets its failure counters -- this does not create a second token.'
          : 'Store a Meta Instagram Graph API access token here. The token is encrypted at rest and can be re-used across jobs; there is no automatic 1-hour recovery unless the backend explicitly marks the token as recoverable later.'}
      </p>
    </form>
  );
}
