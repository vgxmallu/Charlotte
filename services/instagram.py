import asyncio
import logging
import os
import re
from functools import partial

import aiofiles
import aiohttp

from utils import login_user, truncate_string

from .base_service import BaseService

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
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
        logger.debug(f"Checking if URL is supported: {url}")
        return bool(
            re.match(
                r"https://www\.instagram\.com/(?:p|reel|tv|stories)/([A-Za-z0-9_-]+)/",
                url,
            )
        )

    def is_playlist(self, url: str) -> bool:
        logger.debug(f"Checking if URL is a playlist: {url}")
        return False

    async def download(self, url: str) -> list:
        logger.info(f"Starting download for URL: {url}")
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

            logger.info(f"Starting download of {len(media_urls)} media files")
            downloaded = await download_all_media(media_urls, filenames)

            for path in downloaded:
                if not isinstance(path, Exception):
                    result.append({
                        "type": "video" if path.endswith(".mp4") else "image",
                        "path": path,
                        "title": truncate_string(getattr(media, "caption_text", ""))
                    })
                else:
                    logger.error(f"Failed to download media: {path}")

            return result

        except Exception as e:
            logger.error(f"Error downloading Instagram media: {str(e)}", exc_info=True)
            return [{
                "type": "error",
                "message": str(e)
            }]


async def run_in_thread(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args))


async def download_media(session, url, filename):
    logger.debug(f"Downloading media from URL: {url} to {filename}")
    try:
        async with session.get(url) as response:
            if response.status == 200:
                async with aiofiles.open(filename, "wb") as f:
                    await f.write(await response.read())
                logger.debug(f"Downloaded: {filename}")
                return filename
            else:
                error_msg = f"Failed to download {url}: HTTP {response.status}"
                logger.error(error_msg)
                return Exception(error_msg)
    except Exception as e:
        error_msg = f"Error downloading {url}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return Exception(error_msg)


async def download_all_media(media_urls, filenames):
    logger.info(f"Starting parallel download for {len(media_urls)} files")
    async with aiohttp.ClientSession() as session:
        tasks = [download_media(session, url, name)
            for url, name in zip(media_urls, filenames)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Parallel download completed")
        return results
