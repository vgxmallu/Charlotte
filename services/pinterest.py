import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

import aiofiles
import aiohttp
import yt_dlp
from fake_useragent import UserAgent

from .base_service import BaseService

ua = UserAgent()


class PinterestService(BaseService):
    name = "Pinterest"
    _download_executor = ThreadPoolExecutor(max_workers=10)

    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)

    def is_supported(self, url: str) -> bool:
        return bool(
            re.match(
                r"https?://(?:www\.)?(?:pinterest\.com/[\w/-]+|pin\.it/[A-Za-z0-9]+)",
                url,
            )
        )

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> list:
        result = []

        async with aiohttp.ClientSession() as sesion:
            async with sesion.get(url) as link:
                url = str(link.url)

        try:
            match = re.search(r"/pin/(\d+)", url)
            if match:
                post_id = match.group(1)
            else:
                logging.error(f"Не удалось извлечь post_id из URL: {url}")
                return result

            post_dict = await self._get_pin_info(int(post_id))
            image_signature = post_dict["image_signature"]

            if post_dict["ext"] == "mp4":
                video_url = post_dict["video"]
                if video_url.endswith(".m3u8"):
                    filename = os.path.join(self.output_path, f"{image_signature}.mp4")
                    await self._download_m3u8_video(video_url, filename)
                else:
                    filename = os.path.join(self.output_path, f"{image_signature}.mp4")
                    await self._download_video(video_url, filename)

                result.append({"type": "video", "path": filename})
            elif post_dict["ext"] == "carousel":
                carousel_data = post_dict["carousel_data"]
                for i, image_url in enumerate(carousel_data):
                    filename = os.path.join(
                        self.output_path, f"{image_signature}_{i}.jpg"
                    )
                    await self._download_photo(image_url, filename)
                    result.append({"type": "image", "path": filename})
            elif post_dict["ext"] == "jpg":
                image_url = post_dict["image"]
                if image_url.endswith(".gif"):
                    filename = os.path.join(self.output_path, f"{image_signature}.gif")
                    await self._download_video(image_url, filename)
                    result.append({"type": "gif", "path": filename})
                else:
                    filename = os.path.join(self.output_path, f"{image_signature}.jpg")
                    await self._download_photo(image_url, filename)
                    result.append({"type": "image", "path": filename})
            else:
                logging.error(f"No media: {post_dict}")
                return result

            result.append({"type": "title", "title": post_dict["title"]})

            return result

        except Exception as e:
            logging.error(f"Failed to download Pinterest: {e}")
            return result

    async def _get_pin_info(self, pin_id: int) -> Dict[str, Any]:
        url = "https://www.pinterest.com/resource/PinResource/get/"
        headers = {
            "accept": "application/json, text/javascript, */*, q=0.01",
            "user-agent": ua.random,
            "x-pinterest-pws-handler": "www/pin/[id]/feedback.js",
        }
        params = {
            "source_url": f"/pin/{pin_id}",
            "data": f'{{"options":{{"id":"{pin_id}","field_set_key":"auth_web_main_pin","noCache":true,"fetch_visual_search_objects":true}},"context":{{}}}}',
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    response_json = await response.json()
                else:
                    raise Exception(
                        f"Failed to retrieve image. Status code: {response.status}"
                    )

        root = response_json["resource_response"]["data"]

        title = root["title"]
        image_signature = root["image_signature"]
        ext = ""
        carousel_data = None
        video = None
        image = None

        if root.get("carousel_data"):
            carousel = root["carousel_data"]["carousel_slots"]
            carousel_data = []
            for carousel_element in carousel:
                image_url = carousel_element["images"]["736x"]["url"]
                carousel_data.append(image_url)
            ext = "carousel"

        elif (
            isinstance(root.get("story_pin_data"), dict)
            and isinstance(root["story_pin_data"].get("pages"), list)
            and len(root["story_pin_data"]["pages"]) > 0
            and isinstance(root["story_pin_data"]["pages"][0].get("blocks"), list)
            and len(root["story_pin_data"]["pages"][0]["blocks"]) > 0
            and isinstance(root["story_pin_data"]["pages"][0]["blocks"][0], dict)
            and isinstance(
                root["story_pin_data"]["pages"][0]["blocks"][0].get("video"), dict
            )
            and isinstance(
                root["story_pin_data"]["pages"][0]["blocks"][0]["video"].get(
                    "video_list"
                ),
                dict,
            )
        ):
            video_list = root["story_pin_data"]["pages"][0]["blocks"][0]["video"][
                "video_list"
            ]
            video = self._get_best_video(video_list)

            if video:
                ext = "mp4"

        elif isinstance(root.get("videos"), dict) and isinstance(
            root["videos"].get("video_list"), dict
        ):
            video_list = root["videos"]["video_list"]
            video = self._get_best_video(video_list)

            if video:
                ext = "mp4"

        elif isinstance(root.get("videos"), dict) and isinstance(
            root["videos"].get("video_list"), dict
        ):
            video_list = root["videos"]["video_list"]
            video = self._get_best_video(video_list)

            if video:
                ext = "mp4"

        elif (
            isinstance(root.get("images"), dict)
            and isinstance(root["images"].get("orig"), dict)
            and "url" in root["images"]["orig"]
        ):
            image = root["images"]["orig"]["url"]
            ext = "jpg"

        else:
            logging.error(f"Unknown Pinterest type. Pin id{pin_id}")

        data = {
            "title": title,
            "image_signature": image_signature,
            "ext": ext,
            "carousel_data": carousel_data,
            "video": video,
            "image": image,
        }

        return data

    async def _download_photo(self, url: str, filename: str) -> None:
        try:
            content_url = re.sub(r"/\d+x", "/originals", url)
            async with aiohttp.ClientSession() as session:
                async with session.get(content_url) as response:
                    response_status = response.status
                    if response_status == 200:
                        async with aiofiles.open(filename, "wb") as f:
                            await f.write(await response.read())
                        return

            if response_status == 403:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            async with aiofiles.open(filename, "wb") as f:
                                await f.write(await response.read())
                            return
                        else:
                            raise Exception(
                                f"Failed to retrieve image. Status code: {response.status}"
                            )
        except Exception as e:
            logging.error(f"Failed to retrieve image: {url}. {e}")

    async def _download_video(self, url: str, filename: str) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > 50 * 1024 * 1024:
                        logging.warning(f"Файл {filename} слишком большой (>50MB).")
                        return

                    async with aiofiles.open(filename, "wb") as f:
                        async for chunk in response.content.iter_chunked(1024):
                            await f.write(chunk)
        except Exception as e:
            logging.error(f"Ошибка загрузки видео: {e}")

    def _get_best_video(self, video_list):
        video_qualities = ["V_EXP7", "V_720P", "V_480P", "V_360P", "V_HLSV3_MOBILE"]
        for quality in video_qualities:
            if quality in video_list:
                return video_list[quality]["url"]
        return None

    async def _download_m3u8_video(self, url: str, filename: str) -> None:
        try:
            ydl_opts = {'outtmpl': filename}
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await loop.run_in_executor(
                        self._download_executor,
                        lambda: ydl.download([url])
                )
        except Exception as e:
            logging.error(f"Ошибка при скачивании видео из m3u8: {e}")
