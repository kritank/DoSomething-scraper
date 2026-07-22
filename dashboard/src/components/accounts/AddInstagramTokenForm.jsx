import React, { useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import Input from '../common/Input';
import Button from '../common/Button';
import { cn } from '../../utils/cn';
import { registerInstagramTokenFacebookLogin, registerInstagramTokenInstagramLogin } from '../../services/instagramTokensService';

const FLAVORS = [
  { id: 'facebook_login', label: 'Facebook Login (recommended)' },
  { id: 'instagram_login', label: 'Instagram Login' },
];

export default function AddInstagramTokenForm({ onRegistered, initialLabel, lockLabel = false }) {
  const [flavor, setFlavor] = useState('facebook_login');
  const [submitting, setSubmitting] = useState(false);

  const [label, setLabel] = useState(initialLabel ?? '');
  const [appId, setAppId] = useState('');
  const [appSecret, setAppSecret] = useState('');
  const [token, setToken] = useState('');
  const [igUserId, setIgUserId] = useState('');

  const reset = () => {
    setLabel(initialLabel ?? ''); setAppId(''); setAppSecret(''); setToken(''); setIgUserId('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    const cleanLabel = label.trim();
    if (!cleanLabel || !appId.trim() || !appSecret.trim() || !token.trim()) return;

    setSubmitting(true);
    try {
      if (flavor === 'facebook_login') {
        await registerInstagramTokenFacebookLogin({
          label: cleanLabel,
          appId: appId.trim(),
          appSecret: appSecret.trim(),
          shortToken: token.trim(),
        });
      } else {
        if (!igUserId.trim()) return;
        await registerInstagramTokenInstagramLogin({
          label: cleanLabel,
          appId: appId.trim(),
          appSecret: appSecret.trim(),
          token: token.trim(),
          igUserId: igUserId.trim(),
        });
      }
      toast.success(lockLabel ? `"${cleanLabel}" rotated -- active and available to the scrape pool` : `"${cleanLabel}" added -- active and available to the scrape pool`);
      reset();
      onRegistered();
    } catch {
      // apiClient's interceptor already toasts the error detail (e.g. a
      // failed live Business Discovery validation, missing scopes, etc).
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit = label.trim() && appId.trim() && appSecret.trim() && token.trim()
    && (flavor === 'facebook_login' || igUserId.trim());

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex gap-2">
        {FLAVORS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFlavor(f.id)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
              flavor === f.id ? 'text-white' : '',
            )}
            style={{
              background: flavor === f.id ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
              color: flavor === f.id ? 'white' : 'var(--color-text-secondary)',
              border: '1px solid ' + (flavor === f.id ? 'var(--color-accent)' : 'var(--color-border-default)'),
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="flex items-end gap-3 flex-wrap">
        <div className="min-w-[160px]">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            Label
          </label>
          <Input
            placeholder="e.g. reader-1"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            disabled={lockLabel}
          />
        </div>

        <div className="min-w-[160px]">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Meta app ID</label>
          <Input value={appId} onChange={(e) => setAppId(e.target.value)} />
        </div>

        <div className="min-w-[200px]">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Meta app secret</label>
          <Input type="password" value={appSecret} onChange={(e) => setAppSecret(e.target.value)} />
        </div>

        <div className="min-w-[220px] flex-1">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            {flavor === 'facebook_login' ? 'Short-lived token (Graph API Explorer)' : 'Long-lived token'}
          </label>
          <Input type="password" value={token} onChange={(e) => setToken(e.target.value)} />
        </div>

        {flavor === 'instagram_login' && (
          <div className="min-w-[160px]">
            <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>IG User ID</label>
            <Input value={igUserId} onChange={(e) => setIgUserId(e.target.value)} />
          </div>
        )}

        <Button type="submit" size="md" loading={submitting} disabled={!canSubmit}>
          <Plus className="w-3.5 h-3.5" />
          {lockLabel ? 'Rotate' : 'Add token'}
        </Button>
      </div>

      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
        {flavor === 'facebook_login'
          ? 'Paste the short-lived User token from Graph API Explorer -- exchanged server-side for a non-expiring Page token and validated with a live Business Discovery call before it\'s stored. Requires instagram_basic, instagram_manage_insights, and pages_show_list granted.'
          : 'Paste the final long-lived token and IG User ID from the app dashboard\'s own token generator -- validated with a live Business Discovery call before it\'s stored. Expires in ~60 days; re-register with the same label to rotate.'}
        {' '}Both app secret and token are encrypted at rest.
      </p>
    </form>
  );
}
