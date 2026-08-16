from pydantic import BaseModel, Field


class JygsSessionInput(BaseModel):
    session: str = Field(min_length=1)


class JygsSyncInput(BaseModel):
    start_date: str
    end_date: str
