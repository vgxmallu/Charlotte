import asyncio
import logging
import os
import re
import urllib.request

import aiohttp
import yt_dlp
from bs4 import BeautifulSoup

from .base_service import BaseService


class PinterestService(BaseService):
    name = "Pinterest"
    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)

    def is_supported(self, url: str) -> bool:
        return bool(re.match(r'https?://(?:www\.)?(?:pinterest\.com/[\w/-]+|pin\.it/[A-Za-z0-9]+)', url))

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> list:
        result = []

        async with aiohttp.ClientSession() as sesion:
            async with sesion.get(url) as link:
                url = str(link.url)

        try:
            parts = url.split("/")
            filename = parts[-3]
            options = {
                "outtmpl": f"{self.output_path}/{filename}.%(ext)s",
            }

            with yt_dlp.YoutubeDL(options) as ydl:
                info_dict = await asyncio.to_thread(ydl.extract_info, url, download=False)
                file_path = ydl.prepare_filename(info_dict)
                await asyncio.to_thread(ydl.download, [url])

                result.append({"type": "video", "path": file_path})

            return result

        except Exception:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    html = await response.text()
                    status_code = response.status

                if status_code == 200:
                    soup = BeautifulSoup(html, "html.parser")
                    link = soup.find("img")

                    if link:
                        content_url = link["src"]

                        parts = content_url.split("/")
                        filename = parts[-1]
                        file_path = os.path.join(self.output_path, filename)
                        content_url = re.sub(r'/\d+x', '/originals', content_url)

                        try:
                            urllib.request.urlretrieve(content_url, file_path)
                        except Exception:
                            content_url = re.sub(r'\.jpg$', '.png', content_url)
                            urllib.request.urlretrieve(content_url, file_path)

                        result.append({"type": "image", "path": file_path})

                        return result

                    else:
                        logging.error('Class "img" not found')
                        return result
                else:
                    logging.error(f"Error response status code {status_code}")
                    return result
