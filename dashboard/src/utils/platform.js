// Instagram handles are stored bare ("mkbhd"); YouTube handles are stored
// already prefixed ("@GoogleDevelopers") -- see
// InfluencerRepo.normalize_handle on the backend. Display must not
// blindly prepend "@" to both, or a YouTube handle renders as "@@name".
export function formatHandle(handle, platform) {
  if (!handle) return '';
  return platform === 'youtube' ? handle : `@${handle}`;
}

export function platformLabel(platform) {
  return platform === 'youtube' ? 'YouTube' : 'Instagram';
}

// Same brand colors as PlatformBadge/PlatformIcon -- shared here so charts
// (which color by platform, not by the app's generic accent palette) stay
// visually consistent with every other platform indicator in the app.
export const PLATFORM_COLORS = {
  instagram: '#d62976',
  youtube: '#ff0000',
};
