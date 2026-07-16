import React from 'react';
import { cn } from '../../utils/cn';
import { platformLabel } from '../../utils/platform';
import PlatformIcon from './PlatformIcon';

const STYLES = {
  instagram: { bg: 'rgba(214,41,118,0.12)', fg: '#d62976' },
  youtube: { bg: 'rgba(255,0,0,0.12)', fg: '#ff0000' },
};

export default function PlatformBadge({ platform, className }) {
  const style = STYLES[platform] ?? STYLES.instagram;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 pl-1 pr-2.5 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap',
        className,
      )}
      style={{ background: style.bg, color: style.fg }}
    >
      <PlatformIcon platform={platform} className="w-3.5 h-3.5 rounded-[4px]" />
      {platformLabel(platform)}
    </span>
  );
}
