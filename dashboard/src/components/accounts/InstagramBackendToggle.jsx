import React, { useEffect, useState } from 'react';
import { Zap, Cookie } from 'lucide-react';
import { toast } from 'sonner';
import { getInstagramBackend, setInstagramBackend } from '../../services/accountsService';

const OPTIONS = [
  { value: 'cookies', label: 'Cookies only', icon: Cookie, description: 'Legacy scraper for every Instagram influencer.' },
  { value: 'hybrid', label: 'Hybrid (Graph API)', icon: Zap, description: 'Official API primary, cookies for comments/views enrichment.' },
];

// Live, DB-backed switch -- takes effect on the very next scrape dispatch,
// no redeploy. See AppSetting's docstring (app/models/app_setting.py) for
// why this can't be a simple in-memory toggle: api/worker/scheduler are
// separate processes, so only a DB row is visible to all three.
export default function InstagramBackendToggle() {
  const [current, setCurrent] = useState(null); // { backend, override_active }
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setCurrent(await getInstagramBackend());
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleSelect = async (backend) => {
    if (!current || backend === current.backend || saving) return;
    if (
      backend === 'hybrid' &&
      !window.confirm(
        'Switch ALL Instagram influencers to the hybrid Graph API pipeline? ' +
          'This affects every tracked Instagram account immediately and depends on the ' +
          'Graph API token pool having enough capacity. You can switch back to cookies instantly if needed.',
      )
    ) {
      return;
    }
    setSaving(true);
    try {
      const updated = await setInstagramBackend(backend);
      setCurrent(updated);
      toast.success(`Instagram backend switched to ${backend === 'hybrid' ? 'hybrid (Graph API)' : 'cookies only'}`);
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>Instagram scraping backend</h3>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
            Applies to every tracked Instagram influencer, live, on the next dispatch.
          </p>
        </div>
        {current?.override_active && (
          <span
            className="text-xs font-medium px-2 py-0.5 rounded-full"
            style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)' }}
          >
            live override active
          </span>
        )}
      </div>

      <div className="flex items-center gap-1 rounded-xl p-1 w-fit" style={{ background: 'var(--color-bg-card-hover)' }}>
        {OPTIONS.map((opt) => {
          const isActive = current?.backend === opt.value;
          const Icon = opt.icon;
          return (
            <button
              key={opt.value}
              type="button"
              disabled={loading || saving}
              onClick={() => handleSelect(opt.value)}
              title={opt.description}
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-60"
              style={{
                background: isActive ? 'var(--color-accent)' : 'transparent',
                color: isActive ? '#fff' : 'var(--color-text-muted)',
              }}
            >
              <Icon className="w-3.5 h-3.5" />
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
