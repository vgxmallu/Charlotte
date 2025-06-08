import asyncio
import os
import re
from pathlib import Path
from typing import List

import aiofiles
import aiohttp
from fake_useragent import UserAgent

from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils.error_handler import BotError, ErrorCode

ua = UserAgent(platforms="desktop")


class PixivService(BaseService):
    name = "Pixiv"

    def __init__(self, output_path: str = "other/downloadsTemp/"):
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        self.user_agent = ua.random
        self.headers = {
            'accept': 'application/json',
            "Referer": "https://www.pixiv.net/",
            "User-Agent": self.user_agent,
        }

    def is_supported(self, url: str) -> bool:
        return bool(
            re.match(r"https:\/\/www\.pixiv\.net\/(?:[a-z]{2}\/)?artworks\/\d+", url)
        )

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> List[MediaContent]:
        result = []
        match = re.search(r'pixiv\.net/.*/artworks/(\d+)$', url)

        if match:
            pixiv_id = match.group(1)
        else:
            raise BotError(
                code=ErrorCode.INVALID_URL,
                message="Invalid Pixiv URL",
                url=url,
                critical=False,
                is_logged=True,
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://www.pixiv.net/ajax/illust/{pixiv_id}/pages", headers=self.headers) as response:
                    if response.status == 200:
                        page_response_json = await response.json()
                    else:
                        raise BotError(
                            code=ErrorCode.INVALID_URL,
                            message="Failed to retrieve Pixiv pages info",
                            url=url,
                            critical=False,
                            is_logged=True,
                        )
            for img in page_response_json["body"]:
                img_url=img["urls"]["original"]

                filename = self.output_path + img_url.split("/")[-1]
                await self._download_photo(img_url, filename)

                result.append(
                    MediaContent(
                        type=MediaType.PHOTO,
                        path=Path(filename),
                        original_size=True,
                    )
                )

        except BotError as e:
            raise e
        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"Pixiv: {e}",
                url=url,
                critical=False,
                is_logged=True,
            )

        return result

    async def _download_photo(self, url: str, filename: str) -> None:
        retries = 3
        connector = aiohttp.TCPConnector(force_close=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            for attempt in range(retries):
                try:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            async with aiofiles.open(filename, "wb") as f:
                                async for chunk in response.content.iter_chunked(1024):
                                    await f.write(chunk)
                            break
                        else:
                            raise BotError(
                                code=ErrorCode.DOWNLOAD_FAILED,
                                message=f"Failed to download Pixiv image: {response.status}",
                                url=url,
                                critical=False,
                                is_logged=True,
                            )
                except Exception:
                    if attempt < retries - 1:
                        await asyncio.sleep(0.5)
                    else:
                        raise
