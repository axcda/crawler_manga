import logging
from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import (
    MONGO_URI, MONGO_DB, 
    MONGO_COLLECTION_MANGA,
    MONGO_COLLECTION_CHAPTERS,
    MONGO_COLLECTION_IMAGES
)
from models.manga import MangaInfo, Chapter, Image
import uuid
from datetime import datetime
from typing import Optional, List

logger = logging.getLogger(__name__)

class DBManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBManager, cls).__new__(cls)
            cls._instance.client = None
            cls._instance.db = None
        return cls._instance
    
    async def connect(self):
        """连接到MongoDB"""
        try:
            if not self.client:
                self.client = AsyncIOMotorClient(MONGO_URI)
                self.db = self.client[MONGO_DB]
                logger.info("成功连接到MongoDB")
        except Exception as e:
            logger.error(f"连接MongoDB失败: {str(e)}")
            raise
            
    async def close(self):
        """关闭MongoDB连接"""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("已关闭MongoDB连接")
            
    async def save_manga(self, manga: MangaInfo, path: str = None) -> str:
        """
        保存漫画信息到数据库。
        如果提供了路径，则使用路径作为 manga_id；否则使用现有的 manga_id 或生成新的。
        
        Args:
            manga (MangaInfo): 漫画信息对象
            path (str, optional): 漫画路径
            
        Returns:
            str: 保存的漫画的 manga_id
        """
        try:
            # 如果提供了路径，使用路径作为 manga_id
            if path:
                manga.manga_id = path
            # 如果没有 manga_id，生成一个新的
            elif not manga.manga_id:
                manga.manga_id = str(uuid.uuid4())
            
            # 清理标题（移除状态信息和多余的空格）
            manga.title = manga.title.replace("連載中", "").strip()
            
            # 转换为字典并保存
            manga_dict = manga.dict()
            await self.db[MONGO_COLLECTION_MANGA].update_one(
                {"manga_id": manga.manga_id},
                {"$set": manga_dict},
                upsert=True
            )
            
            # 添加示例章节
            chapter = Chapter(
                manga_id=manga.manga_id,
                chapter_id=str(uuid.uuid4()),
                title="第1话",
                link=f"{manga.manga_id}/1",
                order=1,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            await self.save_chapter(chapter)
            
            logger.info(f"保存漫画成功: {manga.title} (ID: {manga.manga_id})")
            return manga.manga_id
            
        except Exception as e:
            logger.error(f"保存漫画时出错: {str(e)}")
            raise
            
    async def save_chapter(self, chapter: Chapter) -> str:
        """保存章节信息"""
        try:
            if not chapter.chapter_id:
                chapter.chapter_id = str(uuid.uuid4())
            chapter.updated_at = datetime.now()
            
            chapter_dict = chapter.dict()
            await self.db[MONGO_COLLECTION_CHAPTERS].update_one(
                {"chapter_id": chapter.chapter_id},
                {"$set": chapter_dict},
                upsert=True
            )
            logger.info(f"保存章节信息成功: {chapter.title}")
            return chapter.chapter_id
        except Exception as e:
            logger.error(f"保存章节信息失败: {str(e)}")
            raise
            
    async def save_images(self, images: list[Image]):
        """批量保存图片信息"""
        try:
            if not images:
                return
                
            # 为没有ID的图片生成ID
            for image in images:
                if not image.image_id:
                    image.image_id = str(uuid.uuid4())
                image.updated_at = datetime.now()
                
            # 批量更新
            operations = [
                {
                    "update_one": {
                        "filter": {"image_id": image.image_id},
                        "update": {"$set": image.dict()},
                        "upsert": True
                    }
                }
                for image in images
            ]
            
            result = await self.db[MONGO_COLLECTION_IMAGES].bulk_write(operations)
            logger.info(f"批量保存图片信息成功: {len(images)}张")
            return result
        except Exception as e:
            logger.error(f"批量保存图片信息失败: {str(e)}")
            raise
            
    async def get_manga(self, manga_id: str) -> MangaInfo:
        """获取漫画信息"""
        try:
            manga_dict = await self.db[MONGO_COLLECTION_MANGA].find_one(
                {"manga_id": manga_id}
            )
            if manga_dict:
                return MangaInfo(**manga_dict)
            return None
        except Exception as e:
            logger.error(f"获取漫画信息失败: {str(e)}")
            raise
            
    async def get_chapters(self, manga_id: str) -> list[Chapter]:
        """获取漫画的所有章节"""
        try:
            chapters = []
            cursor = self.db[MONGO_COLLECTION_CHAPTERS].find(
                {"manga_id": manga_id}
            ).sort("order", 1)
            
            async for doc in cursor:
                chapters.append(Chapter(**doc))
            return chapters
        except Exception as e:
            logger.error(f"获取章节列表失败: {str(e)}")
            raise
            
    async def get_chapter_images(self, chapter_id: str) -> list[Image]:
        """获取章节的所有图片"""
        try:
            images = []
            cursor = self.db[MONGO_COLLECTION_IMAGES].find(
                {"chapter_id": chapter_id}
            ).sort("order", 1)
            
            async for doc in cursor:
                images.append(Image(**doc))
            return images
        except Exception as e:
            logger.error(f"获取章节图片失败: {str(e)}")
            raise
            
    async def search_manga(self, keyword: str, skip: int = 0, limit: int = 20) -> list[MangaInfo]:
        """搜索漫画"""
        try:
            manga_list = []
            cursor = self.db[MONGO_COLLECTION_MANGA].find(
                {"title": {"$regex": keyword, "$options": "i"}}
            ).skip(skip).limit(limit)
            
            async for doc in cursor:
                manga_list.append(MangaInfo(**doc))
            return manga_list
        except Exception as e:
            logger.error(f"搜索漫画失败: {str(e)}")
            raise
            
    async def get_manga_by_path(self, path: str) -> Optional[MangaInfo]:
        """
        通过路径获取漫画信息。
        首先尝试使用路径作为 manga_id 进行查询，如果找不到，则尝试使用标题进行查询。
        
        Args:
            path (str): 漫画路径
            
        Returns:
            Optional[MangaInfo]: 如果找到漫画则返回 MangaInfo 对象，否则返回 None
        """
        try:
            # 首先尝试使用路径作为 manga_id 进行查询
            manga = await self.db[MONGO_COLLECTION_MANGA].find_one({"manga_id": path})
            
            if not manga:
                # 如果找不到，则尝试从路径中提取标题进行查询
                manga_name = path.replace("-", "").strip()
                logger.info(f"使用标题搜索漫画: {manga_name}")
                
                # 使用正则表达式进行不区分大小写的搜索
                manga = await self.db[MONGO_COLLECTION_MANGA].find_one({
                    "title": {"$regex": f".*{manga_name}.*", "$options": "i"}
                })
                
                if manga:
                    # 如果找到了漫画，更新其 manga_id 为路径
                    await self.db[MONGO_COLLECTION_MANGA].update_one(
                        {"_id": manga["_id"]},
                        {"$set": {"manga_id": path}}
                    )
                    logger.info(f"更新漫画 ID: {path}")
            
            if manga:
                # 清理标题（移除状态信息和多余的空格）
                title = manga["title"].replace("連載中", "").strip()
                manga["title"] = title
                return MangaInfo(**manga)
            else:
                logger.warning(f"未找到漫画: {path}")
                return None
            
        except Exception as e:
            logger.error(f"获取漫画时出错: {str(e)}")
            return None 