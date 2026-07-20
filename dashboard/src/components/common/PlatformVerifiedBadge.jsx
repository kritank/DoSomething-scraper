import React from 'react';
import { BadgeCheck } from 'lucide-react';
import { cn } from '../../utils/cn';
import { platformLabel, profileUrl } from '../../utils/platform';
import PlatformIcon from './PlatformIcon';
import ScrapeStatusIndicator from './ScrapeStatusIndicator';

// Compact square platform-logo badge with a small verified checkmark
// overlaid on its bottom-right corner when `verified` is true, and (when
// `scrapeStatus` is passed) a status dot overlaid on the top-right corner
// -- replaces the old wide text pill (PlatformBadge) in spots where
// several platforms sit side by side and per-platform verification/sync
// status matters (e.g. the combined creator header), since a name+icon
// pill can't show either without also spelling out the platform name
// every time.
//
// `handle`, when passed, turns the logo into a link out to the real
// Instagram profile / YouTube channel.
export default function PlatformVerifiedBadge({ platform, verified, className, handle, scrapeStatus }) {
  const label = verified ? `Verified on ${platformLabel(platform)}` : platformLabel(platform);
  const url = profileUrl(handle, platform);
  const Wrapper = url ? 'a' : 'span';
  const wrapperProps = url
    ? { href: url, target: '_blank', rel: 'noreferrer', onClick: (e) => e.stopPropagation() }
    : {};
  return (
    <Wrapper
      className={cn('relative inline-flex shrink-0', className)}
      title={url ? `Open on ${platformLabel(platform)}` : label}
      aria-label={label}
      {...wrapperProps}
    >
      <PlatformIcon platform={platform} className="w-6 h-6 rounded-lg" />
      {verified && (
        <span
          className="absolute -bottom-1 -right-1 flex items-center justify-center rounded-full"
          style={{ background: 'var(--color-bg-card)', padding: 1 }}
        >
          <BadgeCheck className="w-3 h-3" style={{ color: 'var(--color-accent)' }} />
        </span>
      )}
      {scrapeStatus !== undefined && (
        <span
          className="absolute -top-1 -right-1 flex items-center justify-center rounded-full"
          style={{ background: 'var(--color-bg-card)', padding: 2 }}
        >
          <ScrapeStatusIndicator status={scrapeStatus} />
        </span>
      )}
    </Wrapper>
  );
}
