from pydantic import BaseModel, Field


class UserRead(BaseModel):
    id: int
    username: str
    email: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3)
    email: str
