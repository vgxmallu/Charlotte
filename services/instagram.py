import asyncio
import logging
import os
import re
from functools import partial
from pathlib import Path
import urllib.parse
from typing import List, Tuple
import json
import aiofiles
import aiohttp
import secrets

from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils.error_handler import BotError, ErrorCode
from fake_useragent import UserAgent

ua = UserAgent(platforms=["desktop"])

logger = logging.getLogger(__name__)


class InstagramService(BaseService):
    name = "Instagram"

    def __init__(self, output_path: str = "other/downloadsTemp"):
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        self.user_agent = ua.random

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
            media_urls, filenames = await self._get_instagram_post(url)

            downloaded = await download_all_media(media_urls, filenames)

            for path in downloaded:
                if isinstance(path, str):
                    result.append(
                        MediaContent(
                            type=MediaType.PHOTO if path.endswith(".jpg") else MediaType.VIDEO,
                            path=Path(path)
                        )
                    )

            return result
        except BotError as e:
            raise e
        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"Instagram: {e}",
                url=url,
                critical=True,
                is_logged=True,
            )

    async def _get_instagram_post(self, url: str) -> Tuple[List[str], List[str]]:
        # Source: https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/instagram.py
        pattern = r'https://www\.instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)'
        match = re.match(pattern, url)
        if match:
            short_code = match.group(1)
        else:
            raise ValueError("Invalid Instagram URL")

        variables = {
            'shortcode': short_code,
            'child_comment_count': 3,
            'fetch_comment_count': 40,
            'parent_comment_count': 24,
            'has_threaded_comments': True,
        }

        query_params = {
            'doc_id': '8845758582119845',
            'variables': json.dumps(variables, separators=(',', ':')),
        }
        full_url = f'https://www.instagram.com/graphql/query/?{urllib.parse.urlencode(query_params)}'

        headers = {
            'X-IG-App-ID': '936619743392459',
            'X-ASBD-ID': '198387',
            'X-IG-WWW-Claim': '0',
            'Host': 'www.instagram.com',
            'User-Agent': self.user_agent,
            'Accept': '*/*',
            # 'X-CSRFToken': '',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': url,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=headers) as response:
                    raw_data = await response.text()

            with open("instagram_response.json", "w") as f:
                f.write(raw_data)

            data_json = json.loads(raw_data)

            post_info = data_json['data']['xdt_shortcode_media']

            images = []
            filenames = []

            if post_info["__typename"] == "XDTGraphSidecar":
                for edge in post_info["edge_sidecar_to_children"]["edges"]:
                    images.append(edge["node"]["display_url"])
                    filenames.append(f"{edge['node']['shortcode']}.jpg")
            elif post_info["__typename"] == "XDTGraphImage":
                images.append(post_info["display_url"])
                filenames.append(f"{short_code}.jpg")
            elif post_info["__typename"] == "XDTGraphVideo":
                images.append(post_info["video_url"])
                filenames.append(f"{short_code}.mp4")

            return images, filenames
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
