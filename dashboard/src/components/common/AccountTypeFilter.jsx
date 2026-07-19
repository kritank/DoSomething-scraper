import React from 'react';
import { Briefcase, User } from 'lucide-react';
import { cn } from '../../utils/cn';

const TYPES = [
  { id: 'business', label: 'Business', icon: Briefcase },
  { id: 'individual', label: 'Individual', icon: User },
];

/**
 * Multi-select account-type toggle -- same controlled value/onChange
 * contract and pill styling as PlatformFilter, scoped to the fixed
 * "business" | "individual" pair (see Influencer.account_type).
 */
export default function AccountTypeFilter({ value, onChange, size = 'md' }) {
  const toggle = (id) => {
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  };

  const isCompact = size === 'sm';

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {TYPES.map(({ id, label, icon: Icon }) => {
        const isActive = value.includes(id);
        return (
          <button
            key={id}
            type="button"
            onClick={() => toggle(id)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full font-medium transition-all duration-150',
              isCompact ? 'pl-2 pr-2.5 py-1 text-xs' : 'pl-2.5 pr-3 py-1.5 text-sm',
            )}
            style={{
              background: isActive ? 'var(--color-bg-card-hover)' : 'transparent',
              color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
              border: '1px solid ' + (isActive ? 'var(--color-border-default)' : 'var(--color-border-subtle)'),
              opacity: isActive ? 1 : 0.55,
            }}
            title={isActive ? `Hide ${label}` : `Show ${label}`}
          >
            <Icon className={isCompact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
            {label}
          </button>
        );
      })}
    </div>
  );
}
