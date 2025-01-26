import asyncio
import logging
import os
import re
import urllib.request
import json

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
                    if response.status == 200:
                        html = await response.text()

                        soup = BeautifulSoup(html, "html.parser")
                        link = soup.find("img")

                        script_tag = soup.find_all("script", {"data-relay-response": "true", "type": "application/json"})
                        if script_tag:
                            json_data = json.loads(script_tag[1].string)  # Преобразуем строку в JSON
                            pin_data = json_data["response"]["data"]["v3GetPinQuery"]["data"]
                            if pin_data["carouselData"] and pin_data["carouselData"] is not None:
                                for carosel in pin_data["carouselData"]["carouselSlots"]:
                                    content_url = carosel["image736x"]["url"]

                                    parts = content_url.split("/")
                                    filename = parts[-1]
                                    file_path = os.path.join(self.output_path, filename)
                                    content_url = re.sub(r'/\d+x', '/originals', content_url)

                                    await self._download_photo(content_url, file_path)

                                    result.append({"type": "image", "path": file_path})
                            else:
                                image_url = pin_data["image736x"]["url"]
                                parts = image_url.split("/")

                                filename = parts[-1]
                                file_path = os.path.join(self.output_path, filename)
                                image_url = re.sub(r'/\d+x', '/originals', image_url)

                                await self._download_photo(image_url, file_path)

                                result.append({"type": "image", "path": file_path})

                            return result

                        else:
                            logging.error('Class "img" not found')
                            return result
                    else:
                        logging.error(f"Error response status code {status_code}")
                        return result


    async def _download_photo(self, url: str, filename: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(filename, 'wb') as f:
                        f.write(await response.read())
                else:
                    raise Exception(f"Failed to retrieve image. Status code: {response.status}")
