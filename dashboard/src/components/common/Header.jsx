import React from 'react';
import { LogOut } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import Button from './Button';

export default function Header() {
  const clearApiKey = useAppStore((s) => s.clearApiKey);

  return (
    <header
      className="flex items-center justify-end px-6 py-4 shrink-0"
      style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
    >
      <Button variant="ghost" size="sm" onClick={clearApiKey} title="Forget the stored API key">
        <LogOut className="w-3.5 h-3.5" />
        Disconnect
      </Button>
    </header>
  );
}
