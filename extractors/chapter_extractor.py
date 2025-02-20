import logging
from urllib.parse import urljoin
from config.settings import BASE_URL

logger = logging.getLogger(__name__)

class ChapterExtractor:
    @staticmethod
    async def extract_chapter_data(page):
        """提取章节页面的数据"""
        try:
            # 等待页面加载完成
            logger.info('等待页面加载完成...')
            await page.wait_for_load_state('networkidle', timeout=60000)
            logger.info('页面加载完成')

            # 等待Cloudflare验证完成
            logger.info('等待Cloudflare验证...')
            try:
                await page.wait_for_selector('#challenge-running', state='hidden', timeout=60000)
                await page.wait_for_selector('#challenge-form', state='hidden', timeout=60000)
                logger.info('Cloudflare验证完成')
            except Exception as e:
                logger.warning(f'等待Cloudflare验证时出错: {str(e)}')

            # 提取页面标题
            logger.info('提取页面标题...')
            page_title = await page.title()
            manga_title = page_title.split('-')[0].strip()
            chapter_title = page_title.split('-')[1].strip()
            logger.info(f'提取到标题: {manga_title} - {chapter_title}')

            # 提取图片
            chapter_images = await ChapterExtractor._extract_chapter_images(page)
            
            # 提取导航链接
            nav_links = await ChapterExtractor._extract_navigation_links(page)
            
            # 合并结果
            result = {
                'manga_title': manga_title,
                'chapter_title': chapter_title,
                'image_urls': chapter_images,
                'prev_chapter': nav_links.get('prev'),
                'next_chapter': nav_links.get('next')
            }
            
            logger.info(f"提取结果: {result}")
            return result
            
        except Exception as e:
            logger.error(f"提取章节数据时出错: {str(e)}")
            raise
            
    @staticmethod
    async def _extract_chapter_images(page):
        """提取章节图片"""
        try:
            logger.info('开始提取图片...')
            image_elements = await page.query_selector_all('img')
            logger.info(f'找到 {len(image_elements)} 个图片元素')
            
            chapter_images = set()  # 使用集合去重
            
            for img in image_elements:
                src = await img.get_attribute('src') or ''
                alt = await img.get_attribute('alt') or ''
                class_name = await img.get_attribute('class') or ''
                logger.info(f'检查图片: src={src}, alt={alt}, class={class_name}')
                
                # 检查图片是否为章节内容图片
                if ('g-mh.online/hp/' in src or 'baozimh.org' in src) and not ('cover' in src):
                    logger.info(f'找到章节图片: {src}')
                    chapter_images.add(src)
                    
            # 按照图片序号排序
            sorted_images = sorted(list(chapter_images), key=ChapterExtractor._get_image_number)
            logger.info(f'图片排序完成,共 {len(sorted_images)} 张')
            
            return sorted_images
            
        except Exception as e:
            logger.error(f"提取章节图片时出错: {str(e)}")
            return []
            
    @staticmethod
    async def _extract_navigation_links(page):
        """提取上一章和下一章的链接"""
        nav_links = {'prev': None, 'next': None}
        try:
            logger.info('提取导航链接...')
            links = await page.query_selector_all('a')
            
            for link in links:
                text = await link.inner_text()
                href = await link.get_attribute('href')
                if text and href:
                    if '上一' in text:
                        nav_links['prev'] = href
                        logger.info(f'找到上一章链接: {href}')
                    elif '下一' in text:
                        nav_links['next'] = href
                        logger.info(f'找到下一章链接: {href}')
                        
            return nav_links
            
        except Exception as e:
            logger.error(f"提取导航链接时出错: {str(e)}")
            return nav_links
            
    @staticmethod
    def _get_image_number(url):
        """从URL中提取图片序号"""
        try:
            filename = url.split('/')[-1]
            number = filename.split('_')[0]
            return int(number)
        except:
            return 0 