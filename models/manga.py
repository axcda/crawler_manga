from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class MangaInfo:
    """漫画基本信息"""
    title: str
    link: str
    image_url: str
    time: Optional[str] = None
    chapter: Optional[str] = None
    rank: Optional[int] = None

@dataclass
class ChapterInfo:
    """章节信息"""
    manga_title: str
    chapter_title: str
    image_urls: List[str]
    prev_chapter: Optional[str] = None
    next_chapter: Optional[str] = None

@dataclass
class HomePageData:
    """首页数据"""
    updates: List[MangaInfo]
    popular_manga: List[MangaInfo]
    new_manga: List[MangaInfo]
    hot_updates: List[MangaInfo]
    timestamp: int = int(datetime.now().timestamp())

@dataclass
class ApiResponse:
    """API响应格式"""
    code: int
    message: str
    data: Optional[any] = None
    timestamp: int = int(datetime.now().timestamp()) 