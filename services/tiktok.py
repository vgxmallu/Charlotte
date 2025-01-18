from spotipy.util import logging
from .base_service import BaseService
import re
import aiohttp
import os

class TikTokService(BaseService):
    name = "Tiktok"
    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        self.output_path = output_path
        self.BASE_URL = "http://45.13.225.104:4347/api/v2"

    def is_supported(self, url: str) -> bool:
        return bool(re.match(r'https?://(?:www\.)?(?:tiktok\.com/.*|(vm|vt)\.tiktok\.com/.+)', url))

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> list:
        result = []
        try:
            tiktok_info = await self._get_tiktok_info(url)

            if tiktok_info.get("message") and tiktok_info.get("detail"):
                raise Exception(tiktok_info)

            for file in tiktok_info["files"]:
                stream_url = file["url"]

                # Генерируем имя файла из ссылки
                filename = os.path.join(self.output_path, os.path.basename(stream_url))

                # Загружаем файл по ссылке
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.BASE_URL}{stream_url}") as response:
                        if response.status == 200:
                            with open(filename, "wb") as f:
                                while chunk := await response.content.read(8192):
                                    f.write(chunk)
                if filename.endswith(".mp4"):
                    result.append({"type": "video", "path": filename})
                elif filename.endswith(".jpg") or filename.endswith(".png"):
                    result.append({"type": "image", "path": filename})
                elif filename.endswith(".mp3"):
                    result.append({"type": "audio", "path": filename, "cover":  None})

            return result

        except Exception as e:
            logging.error(f"Error downloading TikTok: {str(e)}")
            return result


    async def _get_tiktok_info(self, tiktok_url: str) -> dict:
        url = f"{self.BASE_URL}/download"

        payload = {
            "url": tiktok_url,
            "download_content_type": "ORIGINAL"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                return await response.json()
