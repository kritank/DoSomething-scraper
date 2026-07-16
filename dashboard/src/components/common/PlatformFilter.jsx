import React from 'react';
import { cn } from '../../utils/cn';
import { platformLabel } from '../../utils/platform';
import PlatformIcon from './PlatformIcon';

/**
 * Multi-select platform toggle, shared by every page that needs to scope
 * its data to one or more platforms -- the Header's global instance and
 * each page's own (further-narrowing) local instance both render through
 * this one component, so platform filtering looks and behaves identically
 * everywhere instead of N bespoke implementations.
 *
 * value/onChange: controlled, `value` is the array of currently-selected
 * platform ids. `options` bounds which platforms are selectable at all --
 * a page's local filter should pass the globally-enabled set here so it
 * can never select a platform the user has turned off app-wide.
 */
export default function PlatformFilter({ value, onChange, options = ['instagram', 'youtube'], size = 'md' }) {
  const toggle = (id) => {
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  };

  const isCompact = size === 'sm';

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {options.map((id) => {
        const isActive = value.includes(id);
        return (
          <button
            key={id}
            type="button"
            onClick={() => toggle(id)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full font-medium transition-all duration-150',
              isCompact ? 'pl-1 pr-2.5 py-1 text-xs' : 'pl-1.5 pr-3 py-1.5 text-sm',
            )}
            style={{
              background: isActive ? 'var(--color-bg-card-hover)' : 'transparent',
              color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
              border: '1px solid ' + (isActive ? 'var(--color-border-default)' : 'var(--color-border-subtle)'),
              opacity: isActive ? 1 : 0.55,
            }}
            title={isActive ? `Hide ${platformLabel(id)}` : `Show ${platformLabel(id)}`}
          >
            <PlatformIcon platform={id} className={isCompact ? 'w-4 h-4 rounded-[4px]' : 'w-5 h-5 rounded-md'} />
            {platformLabel(id)}
          </button>
        );
      })}
    </div>
  );
}
