from .base_service import BaseService
import re
import aiohttp
import os

class TikTokService(BaseService):
    name = "Tiktok"
    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path

    def is_supported(self, url: str) -> bool:
        return bool(re.match(r'https?://vm\.tiktok\.com/', url))

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> list:
        tiktok_info = await self._get_tiktok_info(url=url)

        result = []

        for file in tiktok_info["files"]:
            file_url = file["url"]

            # Генерируем имя файла из ссылки
            filename = os.path.join(self.output_path, os.path.basename(file_url))

            # Загружаем файл по ссылке
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://45.11.229.38:4347{file_url}") as response:
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

    async def _get_tiktok_info(self, url: str) -> dict:
        post_url = "http://45.11.229.38:4347/download"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    response_url = str(response.url).split('?')[0]
                    data = {"url": f"{response_url}"}
                else:
                    return {"error": f"HTTP status {response.status}"}

        async with aiohttp.ClientSession() as session:
            async with session.post(post_url, json=data) as response:
                if response.status == 200:
                    response_json = await response.json()
                    return response_json
                else:
                    return {"error": f"HTTP status {response.status}"}
