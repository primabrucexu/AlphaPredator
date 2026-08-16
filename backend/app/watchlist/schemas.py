from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class WatchlistAdd(BaseModel):
    symbol: str


class WatchlistMove(BaseModel):
    group_id: int


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=32)
