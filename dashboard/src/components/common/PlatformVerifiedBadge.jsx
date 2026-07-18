import React from 'react';
import { BadgeCheck } from 'lucide-react';
import { cn } from '../../utils/cn';
import { platformLabel } from '../../utils/platform';
import PlatformIcon from './PlatformIcon';

// Compact square platform-logo badge with a small verified checkmark
// overlaid on its corner when `verified` is true -- replaces the old wide
// text pill (PlatformBadge) in spots where several platforms sit side by
// side and per-platform verification status matters (e.g. the combined
// creator header), since a name+icon pill can't show "verified on this
// platform" without also spelling out the platform name every time.
export default function PlatformVerifiedBadge({ platform, verified, className }) {
  const label = verified ? `Verified on ${platformLabel(platform)}` : platformLabel(platform);
  return (
    <span className={cn('relative inline-flex shrink-0', className)} title={label} aria-label={label}>
      <PlatformIcon platform={platform} className="w-6 h-6 rounded-lg" />
      {verified && (
        <span
          className="absolute -bottom-1 -right-1 flex items-center justify-center rounded-full"
          style={{ background: 'var(--color-bg-card)', padding: 1 }}
        >
          <BadgeCheck className="w-3 h-3" style={{ color: 'var(--color-accent)' }} />
        </span>
      )}
    </span>
  );
}
