import React from 'react';
import { LogOut } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import Button from './Button';
import PlatformFilter from './PlatformFilter';

export default function Header() {
  const clearApiKey = useAppStore((s) => s.clearApiKey);
  const enabledPlatforms = useAppStore((s) => s.enabledPlatforms);
  const setEnabledPlatforms = useAppStore((s) => s.setEnabledPlatforms);

  return (
    <header
      className="flex items-center justify-between px-6 py-4 shrink-0 flex-wrap gap-3"
      style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
    >
      <div className="flex items-center gap-2.5">
        <span className="text-xs font-medium" style={{ color: 'var(--color-text-muted)' }}>
          Platforms
        </span>
        <PlatformFilter value={enabledPlatforms} onChange={setEnabledPlatforms} size="sm" />
      </div>
      <Button variant="ghost" size="sm" onClick={clearApiKey} title="Forget the stored API key">
        <LogOut className="w-3.5 h-3.5" />
        Disconnect
      </Button>
    </header>
  );
}
