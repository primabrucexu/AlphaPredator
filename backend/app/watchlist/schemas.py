from pydantic import BaseModel, Field


class WatchlistAdd(BaseModel):
    symbol: str


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class TagOrderInput(BaseModel):
    tag_ids: list[int]


class TagStockOrderInput(BaseModel):
    symbols: list[str]
