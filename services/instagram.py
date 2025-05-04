import asyncio
import logging
import os
import re
from functools import partial
from pathlib import Path
from typing import List

import aiofiles
import aiohttp

from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils import login_user, truncate_string
from utils.error_handler import BotError, ErrorCode

logger = logging.getLogger(__name__)


class InstagramService(BaseService):
    name = "Instagram"

    def __init__(self, output_path: str = "other/downloadsTemp"):
        logger.info("Initializing InstagramService")
        self.cl = login_user()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        logger.info(f"Output path set to: {self.output_path}")

    def is_supported(self, url: str) -> bool:
        return bool(
            re.match(
                r"https://www\.instagram\.com/(?:p|reel|tv|stories)/([A-Za-z0-9_-]+)/",
                url,
            )
        )

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> List[MediaContent]:
        result = []

        try:
            media_pk = await run_in_thread(self.cl.media_pk_from_url, url)
            media = await run_in_thread(self.cl.media_info, media_pk)

            media_items = []
            if media.media_type == 8:
                for i, res in enumerate(media.resources):
                    media_items.append((res, f"{media_pk}_{i}"))
            else:
                media_items.append((media, str(media_pk)))

            media_urls, filenames = [], []
            for item, name in media_items:
                if item.media_type == 1:
                    media_url = str(getattr(item, "thumbnail_url", "")) or str(getattr(item, "url", ""))
                    ext = "jpg"
                elif item.media_type == 2:
                    media_url = str(getattr(item, "video_url", ""))
                    ext = "mp4"
                else:
                    logger.warning(f"Unsupported media type: {item.media_type}")
                    continue

                if not media_url:
                    logger.warning(f"No media URL found for {name}")
                    continue

                filename = f"{self.output_path}/{name}.{ext}"
                media_urls.append(media_url)
                filenames.append(filename)

            downloaded = await download_all_media(media_urls, filenames)

            for path in downloaded:
                if isinstance(path, str):
                    result.append(
                        MediaContent(
                            type=MediaType.PHOTO if path.endswith(".jpg") else MediaType.VIDEO,
                            path=Path(path),
                            title=truncate_string(getattr(media, "caption_text", ""))
                        )
                    )

            return result

        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"Instagram: {e}",
                url=url,
                critical=True,
                is_logged=True,
            )


async def run_in_thread(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args))


async def download_media(session, url, filename) -> str:
    try:
        async with session.get(url) as response:
            if response.status == 200:
                async with aiofiles.open(filename, "wb") as f:
                    await f.write(await response.read())
                return filename
            else:
                raise BotError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to download Instagram media: {response.status}",
                    url=url,
                    critical=False,
                    is_logged=True,
                )
    except Exception as e:
        raise BotError(
            code=ErrorCode.DOWNLOAD_FAILED,
            message=f"Instagram download: {e}",
            url=url,
            critical=True,
            is_logged=True,
        )


async def download_all_media(media_urls, filenames):
    async with aiohttp.ClientSession() as session:
        tasks = [download_media(session, url, name)
            for url, name in zip(media_urls, filenames)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
