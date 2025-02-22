import logging
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from lxml import etree
from config.settings import BASE_URL

logger = logging.getLogger(__name__)

class MangaExtractor:
    @staticmethod
    def extract_updates(tree):
        """提取更新信息"""
        updates = []
        try:
            manga_cards = tree.xpath('//a[@class="slicarda"]')
            logger.info(f"找到 {len(manga_cards)} 个更新卡片")
            
            for card in manga_cards:
                try:
                    update = MangaExtractor._extract_update_card(card)
                    if update and ('小时前' in update['time'] or '分钟前' in update['time']):
                        updates.append(update)
                except Exception as e:
                    logger.warning(f"处理更新卡片时出错: {str(e)}")
                    
            return updates
        except Exception as e:
            logger.error(f"提取更新信息时出错: {str(e)}")
            return []
            
    @staticmethod
    def extract_hot_updates(tree):
        """提取热门更新"""
        hot_updates = []
        try:
            hot_updates_section = tree.xpath('/html/body/main/div/div[6]/div[1]/div[2]/div')
            logger.info(f"找到 {len(hot_updates_section)} 个热门更新")
            
            for index, item in enumerate(hot_updates_section, 1):
                try:
                    update = MangaExtractor._extract_hot_update_item(item, index, tree)
                    if update:
                        hot_updates.append(update)
                except Exception as e:
                    logger.warning(f"处理热门更新项时出错: {str(e)}")
                    
            return hot_updates
        except Exception as e:
            logger.error(f"提取热门更新时出错: {str(e)}")
            return []
            
    @staticmethod
    def extract_popular_manga(tree):
        """提取人气排行"""
        popular_manga = []
        try:
            rank_section = tree.xpath('/html/body/main/div/div[6]/div[2]/div[2]/div')
            logger.info(f"找到 {len(rank_section)} 个排行榜项目")
            
            for index, item in enumerate(rank_section, 1):
                try:
                    manga = MangaExtractor._extract_ranked_manga(item, index, tree)
                    if manga:
                        popular_manga.append(manga)
                except Exception as e:
                    logger.warning(f"处理排行榜项时出错: {str(e)}")
                    
            return popular_manga
        except Exception as e:
            logger.error(f"提取人气排行时出错: {str(e)}")
            return []
            
    @staticmethod
    def extract_new_manga(tree):
        """提取最新上架"""
        new_manga = []
        try:
            new_section = tree.xpath('/html/body/main/div/div[6]/div[3]/div[2]/div')
            logger.info(f"找到 {len(new_section)} 个最新上架")
            
            for index, item in enumerate(new_section, 1):
                try:
                    manga = MangaExtractor._extract_new_manga_item(item, index, tree)
                    if manga:
                        new_manga.append(manga)
                except Exception as e:
                    logger.warning(f"处理最新上架项时出错: {str(e)}")
                    
            return new_manga
        except Exception as e:
            logger.error(f"提取最新上架时出错: {str(e)}")
            return []
            
    @staticmethod
    def _check_element_exists(element_list):
        """检查元素列表是否存在且非空"""
        return element_list is not None and len(element_list) > 0
        
    @staticmethod
    def _get_text_from_element(element_list, default="未知标题"):
        """从元素列表中获取文本"""
        return element_list[0].strip() if MangaExtractor._check_element_exists(element_list) else default
        
    @staticmethod
    def _extract_update_card(card):
        """提取单个更新卡片信息"""
        try:
            title = card.xpath('.//h3[@class="slicardtitle"]/text()')[0].strip()
            link = urljoin(BASE_URL, card.get('href', ''))
            time_text = card.xpath('.//p[@class="slicardtagp"]/text()')[0].strip()
            chapter_text = card.xpath('.//p[@class="slicardtitlep"]/text()')[0].strip()
            img = card.xpath('.//img[@class="slicardimg"]')[0]
            img_url = MangaExtractor._process_image_url(img.get('src', ''))
            
            return {
                'title': title,
                'link': link,
                'time': time_text,
                'chapter': chapter_text,
                'image_url': img_url
            }
        except Exception as e:
            logger.warning(f"提取更新卡片信息时出错: {str(e)}")
            return None
            
    @staticmethod
    def _extract_hot_update_item(item, index, tree):
        """提取单个热门更新项信息"""
        try:
            link_elements = item.xpath('.//a')
            if not MangaExtractor._check_element_exists(link_elements):
                return None
                
            link_element = link_elements[0]
            title = MangaExtractor._get_text_from_element(item.xpath('.//h3/text()'))
            
            img_xpath = f'/html/body/main/div/div[6]/div[1]/div[2]/div[{index}]/a/div/div/img'
            img_url = MangaExtractor._get_image_url(tree, img_xpath, item)
            
            link = urljoin(BASE_URL, link_element.get('href', ''))
            
            return {
                'title': title,
                'link': link,
                'image_url': img_url
            }
        except Exception as e:
            logger.warning(f"提取热门更新项信息时出错: {str(e)}")
            return None
            
    @staticmethod
    def _extract_ranked_manga(item, index, tree):
        """提取排行榜项目信息"""
        try:
            link_elements = item.xpath('.//a')
            if not MangaExtractor._check_element_exists(link_elements):
                return None
                
            link_element = link_elements[0]
            title = MangaExtractor._get_text_from_element(item.xpath('.//a/div/h3/text()'))
            
            img_xpath = f'/html/body/main/div/div[6]/div[2]/div[2]/div[{index}]/a/div/div/img'
            img_url = MangaExtractor._get_image_url(tree, img_xpath, item)
            
            link = urljoin(BASE_URL, link_element.get('href', ''))
            
            return {
                'title': title,
                'link': link,
                'image_url': img_url,
                'rank': index
            }
        except Exception as e:
            logger.warning(f"提取排行榜项目信息时出错: {str(e)}")
            return None
            
    @staticmethod
    def _extract_new_manga_item(item, index, tree):
        """提取最新上架项目信息"""
        try:
            title_xpath = f'/html/body/main/div/div[6]/div[3]/div[2]/div[{index}]/a/div/h3'
            title_elements = tree.xpath(title_xpath)
            if not MangaExtractor._check_element_exists(title_elements):
                return None
                
            title = title_elements[0].text.strip()
            
            link_xpath = f'/html/body/main/div/div[6]/div[3]/div[2]/div[{index}]/a'
            link_elements = tree.xpath(link_xpath)
            if not MangaExtractor._check_element_exists(link_elements):
                return None
                
            link = urljoin(BASE_URL, link_elements[0].get('href', ''))
            
            img_xpath = f'/html/body/main/div/div[6]/div[3]/div[2]/div[{index}]/a/div/div/img'
            img_url = MangaExtractor._get_image_url(tree, img_xpath, item)
            
            return {
                'title': title,
                'link': link,
                'image_url': img_url
            }
        except Exception as e:
            logger.warning(f"提取最新上架项目信息时出错: {str(e)}")
            return None
            
    @staticmethod
    def _get_image_url(tree, primary_xpath, item):
        """获取图片URL，包含多个备选方案"""
        img_url = ''
        try:
            # 尝试主要xpath
            img_elements = tree.xpath(primary_xpath)
            if img_elements:
                img_url = img_elements[0].get('src', '')
            
            # 如果失败，尝试item中的img标签
            if not img_url:
                img_elements = item.xpath('.//img')
                if img_elements:
                    img_url = img_elements[0].get('src', '')
            
            return MangaExtractor._process_image_url(img_url) if img_url else ''
        except Exception as e:
            logger.warning(f"获取图片URL时出错: {str(e)}")
            return ''
            
    @staticmethod
    def _process_image_url(img_url):
        """处理图片URL"""
        try:
            from urllib.parse import quote
            
            if 'pro-api.mgsearcher.com/_next/image' in img_url:
                return img_url
                
            if 'cncover.godamanga.online' in img_url:
                encoded_url = quote(img_url, safe='')
                return f'https://pro-api.mgsearcher.com/_next/image?url={encoded_url}&w=250&q=60'
                
            return img_url
        except Exception as e:
            logger.warning(f"处理图片URL时出错: {str(e)}")
            return img_url 