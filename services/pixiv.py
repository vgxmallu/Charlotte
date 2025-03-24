import logging
import os
import re
import asyncio

import aiofiles
import aiohttp
from fake_useragent import UserAgent

from .base_service import BaseService

ua = UserAgent(platforms="desktop")


class PixivService(BaseService):
    name = "Pixiv"

    def __init__(self, output_path: str = "other/downloadsTemp"):
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        self.user_agent = ua.random
        self.headers = {
            "Referer": "https://www.pixiv.net/",
            "User-Agent": self.user_agent,
        }

    def is_supported(self, url: str) -> bool:
        return bool(
            re.match(r"https:\/\/www\.pixiv\.net\/(?:[a-z]{2}\/)?artworks\/\d+", url)
        )

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> list:
        result = []

        image_url_pattern = re.compile(
            r"https://i\.pximg\.net/img-original/img/\d{4}/\d{2}/\d{2}/\d{2}/\d{2}/\d{2}/\d{9}_p0\.png"
        )

        try:
            match = re.search(r"artworks/(\d+)", url)
            if match is None:
                raise ValueError("No image id found")

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=self.headers, allow_redirects=True
                ) as response:
                    if response.status == 200:
                        page_content = await response.text()
                        image_urls = image_url_pattern.findall(page_content)
                    else:
                        raise Exception(
                            f"Failed to retrieve post. Status code: {response.status}"
                        )

            for img_url in image_urls:
                filename = self.output_path + img_url.split("/")[-1]
                await self._download_photo(img_url, filename)

                result.append({"type": "image", "path": filename})

        except Exception as e:
            logging.error(f"Error downloading Pixiv image: {str(e)}")

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
                            raise Exception(
                                f"Failed to retrieve image. Status code: {response.status}"
                            )
            except Exception:
                if attempt < retries - 1:
                    await asyncio.sleep(0.5)
                else:
                    raise
