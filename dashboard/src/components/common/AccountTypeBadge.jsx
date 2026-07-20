import React from 'react';
import { Briefcase, User } from 'lucide-react';
import { cn } from '../../utils/cn';

const STYLES = {
  business: { bg: 'rgba(245,158,11,0.12)', fg: '#f59e0b', icon: Briefcase, label: 'Business' },
  individual: { bg: 'var(--color-bg-card-hover)', fg: 'var(--color-text-muted)', icon: User, label: 'Individual' },
};

export default function AccountTypeBadge({ accountType, className }) {
  const style = STYLES[accountType] ?? STYLES.individual;
  const Icon = style.icon;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 pl-1 pr-2.5 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap',
        className,
      )}
      style={{ background: style.bg, color: style.fg }}
    >
      <Icon className="w-3 h-3" />
      {style.label}
    </span>
  );
}
