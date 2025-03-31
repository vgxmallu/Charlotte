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
            # Выносим синхронные вызовы в отдельные потоки
            logger.debug("Fetching media PK from URL")
            media_pk = await run_in_thread(self.cl.media_pk_from_url, url)
            logger.debug(f"Retrieved media PK: {media_pk}")

            logger.debug("Fetching media info")
            media = await run_in_thread(self.cl.media_info, media_pk)
            logger.debug(f"Retrieved media info: {media}")

            # Генерируем URL и имена файлов
            media_urls, filenames = [], []
            if media.media_type == 8:
                logger.debug("Processing GraphSidecar (multiple media)")
                for i, res in enumerate(media.resources):
                    # Исправление: явное преобразование URL к строке и проверка типа
                    media_url = ""
                    if res.media_type == 1:  # Photo
                        media_url = getattr(res, 'thumbnail_url', '') or getattr(res, 'url', '')
                    else:  # Video
                        media_url = getattr(res, 'video_url', '')

                    if not isinstance(media_url, str) or not media_url:
                        logger.error(f"Invalid URL for resource {i}: {media_url}")
                        continue

                    ext = "jpg" if res.media_type == 1 else "mp4"
                    media_urls.append(media_url)
                    filename = f"{self.output_path}/{media_pk}_{i}.{ext}"
                    filenames.append(filename)
                    logger.debug(f"Added media {i} URL: {media_url}, filename: {filename}")

            else:
                logger.debug("Processing single media")
                # Исправление: универсальная обработка URL
                media_url = ""
                if media.media_type == 1:  # Photo
                    media_url = getattr(media, 'thumbnail_url', '') or getattr(media, 'url', '')
                elif media.media_type == 2:  # Video
                    media_url = getattr(media, 'video_url', '')

                if not media_url:
                    logger.error(f"Invalid media URL: {media_url}")
                    return []

                media_url = str(media_url)  # Явное преобразование
                ext = "jpg" if media.media_type == 1 else "mp4"
                media_urls.append(media_url)
                filename = f"{self.output_path}/{media_pk}.{ext}"
                filenames.append(filename)
                logger.debug(f"Added media URL: {media_url}, filename: {filename}")

                # Параллельная загрузка
                logger.info(f"Starting download of {len(media_urls)} media files")
                downloaded = await download_all_media(media_urls, filenames)

                # Формируем результат
                for path in downloaded:
                    if not isinstance(path, Exception):
                        logger.info(f"Successfully downloaded: {path}")
                        result.append({
                            "type": "video" if path.endswith(".mp4") else "image",
                            "path": path,
                            "title": truncate_string(media.caption_text)
                        })
                    else:
                        logger.error(f"Failed to download media: {path}")

                logger.info(f"Download completed for URL: {url}")
                return result

        except Exception as e:
            logger.error(f"Error downloading Instagram media: {str(e)}", exc_info=True)
            return [{
                "type": "error",
                "message": e
            }]


async def run_in_thread(func, *args):
    logger.debug(f"Running synchronous function in thread: {func.__name__}")
    loop = asyncio.get_event_loop()
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
