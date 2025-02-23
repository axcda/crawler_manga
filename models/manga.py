from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class Author(BaseModel):
    names: List[str] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)

class Genre(BaseModel):
    names: List[str] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)

class Type(BaseModel):
    names: List[str] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)

class MangaInfo(BaseModel):
    manga_id: str = Field(default="")
    title: str = Field(default="")
    description: str = Field(default="")
    status: str = Field(default="")
    author: Author = Field(default_factory=Author)
    type: Genre = Field(default_factory=Genre)
    cover: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class Chapter(BaseModel):
    manga_id: str = Field(default="")
    chapter_id: str = Field(default="")
    title: str = Field(default="")
    link: str = Field(default="")
    order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class ChapterInfo(BaseModel):
    manga_id: str = Field(default="")
    chapter_id: str = Field(default="")
    title: str = Field(default="")
    link: str = Field(default="")
    order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class Image(BaseModel):
    image_id: str = Field(default="")
    chapter_id: str = Field(default="")
    manga_id: str = Field(default="")
    url: str = Field(default="")
    order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now) 