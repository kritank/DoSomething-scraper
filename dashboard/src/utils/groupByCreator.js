// Groups a list of DashboardStatusRow-shaped rows by creator_id -- every
// influencer has a creator_id (see InfluencerRepo.create's auto-linking and
// scripts/backfill_creator_groups.py for pre-existing rows), so in practice
// every row ends up in a creator group, even a "solo" one with just itself.
// A row can still lack a creator_id after an explicit unlink (see
// CreatorRepo.delete, ON DELETE SET NULL) -- those fall into `solo` groups
// with no creator name/link at all, matching that action's intent.
//
// Sorted by display name so creator groups and any unlinked handles
// interleave alphabetically rather than creators always floating to one end.
export function groupByCreator(influencers) {
  const creatorGroups = new Map();
  const solo = [];
  for (const row of influencers) {
    if (row.creator_id) {
      if (!creatorGroups.has(row.creator_id)) creatorGroups.set(row.creator_id, []);
      creatorGroups.get(row.creator_id).push(row);
    } else {
      solo.push(row);
    }
  }
  const groups = [];
  for (const [creatorId, rows] of creatorGroups) {
    groups.push({
      key: `creator-${creatorId}`,
      creatorId,
      creatorName: rows[0].creator_name,
      rows: [...rows].sort((a, b) => a.platform.localeCompare(b.platform)),
    });
  }
  for (const row of solo) {
    groups.push({ key: `solo-${row.influencer_id}`, creatorId: null, creatorName: null, rows: [row] });
  }
  groups.sort((a, b) => (a.creatorName || a.rows[0].handle).localeCompare(b.creatorName || b.rows[0].handle));
  return groups;
}
