from uuid import UUID
from pydantic import BaseModel, ConfigDict


class InfluencerCreate(BaseModel):
    handle: str
    category_id: UUID


class InfluencerOut(BaseModel):
    id: UUID
    handle: str
    category_id: UUID
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
