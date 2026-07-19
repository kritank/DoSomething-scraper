import React from 'react';
import { profileUrl, platformLabel } from '../../utils/platform';

// Simplified, tasteful glyphs that evoke each platform for quick visual
// scanning -- not pixel-traced reproductions of the official trademarked
// logo files. lucide-react ships no brand icons at all (removed for
// licensing reasons), so this is the app's only source of platform
// iconography; every other platform indicator (PlatformBadge, tab
// switcher) renders through this one component.
function InstagramGlyph({ className }) {
  return (
    <svg viewBox="0 0 40 40" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="platform-icon-ig" x1="0" y1="40" x2="40" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FEDA75" />
          <stop offset="28%" stopColor="#FA7E1E" />
          <stop offset="55%" stopColor="#D62976" />
          <stop offset="78%" stopColor="#962FBF" />
          <stop offset="100%" stopColor="#4F5BD5" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill="url(#platform-icon-ig)" />
      <rect x="10" y="10" width="20" height="20" rx="6" stroke="white" strokeWidth="2.2" fill="none" />
      <circle cx="20" cy="20" r="5.3" stroke="white" strokeWidth="2.2" fill="none" />
      <circle cx="27.2" cy="12.8" r="1.4" fill="white" />
    </svg>
  );
}

function YoutubeGlyph({ className }) {
  return (
    <svg viewBox="0 0 40 40" className={className} xmlns="http://www.w3.org/2000/svg">
      <rect width="40" height="40" rx="11" fill="#FF0000" />
      <path d="M17 14.5L27 20L17 25.5V14.5Z" fill="white" />
    </svg>
  );
}

// `handle`, when passed, turns the icon into a link out to the real
// Instagram profile / YouTube channel -- optional so every other spot this
// renders purely decoratively (no handle in scope) is unaffected.
export default function PlatformIcon({ platform, className = 'w-6 h-6 rounded-md', handle }) {
  const glyph = platform === 'youtube' ? <YoutubeGlyph className={className} /> : <InstagramGlyph className={className} />;
  const url = profileUrl(handle, platform);
  if (!url) return glyph;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      title={`Open on ${platformLabel(platform)}`}
      // Icons often sit inside a row/card that's itself a Link -- stop the
      // click from also triggering that outer navigation.
      onClick={(e) => e.stopPropagation()}
      className="inline-flex shrink-0"
    >
      {glyph}
    </a>
  );
}
