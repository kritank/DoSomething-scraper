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
