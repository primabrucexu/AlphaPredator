from pydantic import BaseModel, Field


class JygsSessionInput(BaseModel):
    session: str = Field(min_length=1)


class JygsLoginInput(BaseModel):
    timeout_seconds: int = Field(default=300, ge=30, le=900)
