from uuid import UUID

from pydantic import BaseModel


class CreatorRename(BaseModel):
    name: str


class CreatorOut(BaseModel):
    id: UUID
    name: str
    # Which platforms this creator has a linked Influencer row on, e.g.
    # ["instagram", "youtube"] -- lets the frontend show "already linked
    # to Instagram" when registering a creator's YouTube account, and flag
    # true cross-platform creators (2+ platforms) at a glance.
    platforms: list[str]
    influencer_count: int
    # No ConfigDict(from_attributes=True) -- platforms/influencer_count are
    # derived from Creator.influencers (a relationship), assembled in the
    # API layer rather than mapped straight off the ORM object, same
    # convention as DashboardStatusRow.


class CreatorInfluencerRef(BaseModel):
    # Just enough to route to /influencers/{influencer_id} per platform --
    # the combined creator view fetches each one's full stats separately
    # via the existing single-influencer endpoints rather than duplicating
    # that aggregation here.
    influencer_id: UUID
    platform: str
    handle: str


class CreatorDetailOut(BaseModel):
    id: UUID
    name: str
    influencers: list[CreatorInfluencerRef]
