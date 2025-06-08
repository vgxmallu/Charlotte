import asyncio
import os
import re
from pathlib import Path
from typing import List
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import yt_dlp

import aiofiles
import aiohttp
from fake_useragent import UserAgent

from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils.error_handler import BotError, ErrorCode

ua = UserAgent(platforms="desktop")


class RedditService(BaseService):
    name = "Reddit"
    _download_executor = ThreadPoolExecutor(max_workers=5)

    def __init__(self, output_path: str = "other/downloadsTemp"):
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        self.user_agent = ua.random
        self.headers = {
            "User-Agent": self.user_agent,
        }
        self.yt_dlp_opts = {
            "outtmpl": f"{self.output_path}/%(id)s_{yt_dlp.utils.sanitize_filename('%(title)s')}.%(ext)s",
            "quiet": True,
        }

    def is_supported(self, url: str) -> bool:
        return bool(
            re.match(r"https:\/\/www\.reddit\.com\/r\/[A-Za-z0-9_]+\/(?:comments\/[A-Za-z0-9]+(?:\/[^\/\s?]+)?|s\/[A-Za-z0-9]+)(?:\?[^\s]*)?", url)
        )

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> List[MediaContent]:
        result = []
        image_urls = []
        title = None
        media_type = None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, allow_redirects=True) as response:
                    if response.status == 200:
                        page_content = await response.text()
                    else:
                        raise BotError(
                            code=ErrorCode.DOWNLOAD_FAILED,
                            message="Failed to retrieve Reddit page",
                            url=url,
                            critical=False,
                            is_logged=True,
                        )

            soup = BeautifulSoup(page_content, 'html.parser')

            post_info = soup.find('shreddit-post')

            if post_info:
                author = post_info.get('author') or 'N/A'
                subreddit = post_info.get('subreddit-name') or 'N/A'
                post_title = post_info.get('post-title') or 'N/A'
                media_type = post_info.get('post-type') or None
                title = f"{author} on r/{subreddit} - {post_title}"

            if media_type == 'image':
                img_tag = soup.select_one('.zoomable-img-wrapper img')
                if img_tag:
                    src = img_tag.get('src') or img_tag.get('data-lazy-src')
                    if src:
                        image_urls.append(src)
                else:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message="No images found on the Reddit page",
                        url=url,
                        critical=False,
                        is_logged=True,
                    )
            elif media_type == 'video':
                with yt_dlp.YoutubeDL(self.yt_dlp_opts) as ydl:
                    loop = asyncio.get_event_loop()

                    info_dict = await loop.run_in_executor(
                        self._download_executor,
                        lambda: ydl.extract_info(url, download=False)
                    )

                    if not info_dict:
                        raise BotError(
                            code=ErrorCode.DOWNLOAD_FAILED,
                            message="Failed to get video info",
                            url=url,
                            critical=True,
                            is_logged=True
                        )

                    await loop.run_in_executor(
                        self._download_executor,
                        lambda: ydl.download([url])
                    )

                    return [
                        MediaContent(
                            type=MediaType.VIDEO,
                            path=Path(ydl.prepare_filename(info_dict)),
                            title=title,
                        )
                    ]
            elif media_type == 'gallery':
                carousel = soup.select_one('gallery-carousel')
                for li in carousel.select('li'):
                    img_tag = li.select_one('figure img')
                    if img_tag:
                        src = img_tag.get('src') or img_tag.get('data-lazy-src')
                        if src:
                            image_urls.append(src)
            else:
                raise BotError(
                    code=ErrorCode.INVALID_URL,
                    message="No media found on the Reddit page",
                    url=url,
                    critical=False,
                    is_logged=False,
                )

            for img_url in image_urls:
                filename = self.output_path + img_url.split("/")[-1]
                await self._download_photo(img_url, filename)

                result.append(
                    MediaContent(
                        type=MediaType.PHOTO,
                        path=Path(filename),
                        title = title,
                    )
                )

        except BotError as e:
            raise e
        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"Reddit: {e}",
                url=url,
                critical=False,
                is_logged=True,
            )

        return result

    async def _download_photo(self, url: str, filename: str) -> None:
        retries = 3
        for attempt in range(retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            async with aiofiles.open(filename, "wb") as f:
                                while True:
                                    chunk = await response.content.read(1024)
                                    if not chunk:
                                        break
                                    await f.write(chunk)
                            break
                        else:
                            raise BotError(
                                code=ErrorCode.DOWNLOAD_FAILED,
                                message=f"Failed to download Reddit image: {response.status}",
                                url=url,
                                critical=False,
                                is_logged=True,
                            )
            except Exception:
                if attempt < retries - 1:
                    await asyncio.sleep(0.5)
                else:
                    raise
