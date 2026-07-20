import React from 'react';
import { cn } from '../../utils/cn';
import { platformLabel, profileUrl } from '../../utils/platform';
import PlatformIcon from './PlatformIcon';

const STYLES = {
  instagram: { bg: 'rgba(214,41,118,0.12)', fg: '#d62976' },
  youtube: { bg: 'rgba(255,0,0,0.12)', fg: '#ff0000' },
};

// `handle`, when passed, turns the whole pill into a link out to the real
// Instagram profile / YouTube channel -- optional so spots with no handle
// in scope (aggregate summaries etc.) render exactly as before.
export default function PlatformBadge({ platform, className, handle }) {
  const style = STYLES[platform] ?? STYLES.instagram;
  const content = (
    <>
      <PlatformIcon platform={platform} className="w-3.5 h-3.5 rounded-[4px]" />
      {platformLabel(platform)}
    </>
  );
  const sharedProps = {
    className: cn(
      'inline-flex items-center gap-1.5 pl-1 pr-2.5 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap',
      className,
    ),
    style: { background: style.bg, color: style.fg },
  };
  const url = profileUrl(handle, platform);
  if (!url) return <span {...sharedProps}>{content}</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      title={`Open on ${platformLabel(platform)}`}
      onClick={(e) => e.stopPropagation()}
      {...sharedProps}
    >
      {content}
    </a>
  );
}
