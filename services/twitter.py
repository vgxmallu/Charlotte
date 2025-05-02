import asyncio
import logging
import os
import re
from typing import Any, Dict

import aiofiles
import aiohttp
from fake_useragent import UserAgent

from services.base_service import BaseService
from utils.error_handler import BotError, ErrorCode

ua = UserAgent()

logger = logging.getLogger(__name__)


class TwitterService(BaseService):
    name = "Twitter"

    def __init__(self, output_path: str = "other/downloadsTemp"):
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        self.auth = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
        self.user_agent = ua.random
        self.guest_token = None

    def is_supported(self, url: str) -> bool:
        return bool(re.match(r"https://(?:twitter|x)\.com/\w+/status/\d+", url))

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> list:
        result = []
        try:
            match = re.search(r"status/(\d+)", url)
            if match is None:
                raise BotError(ErrorCode.INVALID_URL)
            tweet_id = int(match.group(1))

            tweet_dict = await self._get_tweet_info(tweet_id)

            medias = tweet_dict["data"]["tweetResult"]["result"]["legacy"]["extended_entities"]["media"]

            tasks = []
            for media in medias:
                if media["type"] == "photo":
                    photo_url = media["media_url_https"]
                    match = re.search(r"([^/]+\.(?:jpg|jpeg|png))", photo_url, re.IGNORECASE)
                    if match is None:
                        continue
                    filename = os.path.join(
                        self.output_path,
                        self._sanitize_filename(os.path.basename(photo_url))
                    )
                    tasks.append(self._download_file(photo_url, filename))
                    result.append({"type": "image", "path": filename})

                elif media["type"] == "video":
                    variants = media["video_info"]["variants"]

                    video_with_highest_bitrate = max(
                        (variant for variant in variants if "bitrate" in variant),
                        key=lambda x: x["bitrate"],
                    )

                    video_url = video_with_highest_bitrate["url"]

                    match = re.search(r"([^/]+\.mp4)", video_url)
                    if match is None:
                        continue
                    filename = self.output_path + "/" + match.group(1)

                    tasks.append(self._download_file(video_url, filename))
                    result.append({"type": "video", "path": filename})

                elif media["type"] == "animated_gif":
                    variant = media["video_info"]["variants"][0]

                    video_url = variant["url"]

                    match = re.search(r"([^/]+\.mp4)", video_url)
                    if match is None:
                        continue
                    filename = self.output_path + "/" + match.group(1)

                    tasks.append(self._download_file(video_url, filename))
                    result.append({"type": "gif", "path": filename})

            await asyncio.gather(*tasks)

            author = tweet_dict["data"]["tweetResult"]["result"]["core"]["user_results"]["result"]["legacy"]["name"]
            title = tweet_dict["data"]["tweetResult"]["result"]["legacy"]["full_text"]

            result.append({"type": "title", "title": f"{author} - {title}"})
        except BotError as e:
            raise e
        except Exception as e:
            logger.error(f"Error downloading Twitter video: {str(e)}")
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=str(e),
                url=url,
                critical=True,
                is_logged=True
            )

        return result

    async def _get_guest_token(self) -> int:
        guest_token_url = "https://api.twitter.com/1.1/guest/activate.json"

        headers = {"Authorization": self.auth}

        async with aiohttp.ClientSession() as session:
            async with session.post(guest_token_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("guest_token")
                else:
                    raise BotError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message=f"Failed to get guest token. Status code: {response.status}",
                        critical=True,
                        is_logged=True
                    )

    async def _get_tweet_info(self, tweet_id: int) -> Dict[str, Any]:
        if not self.guest_token:
            self.guest_token = await self._get_guest_token()
        headers = {
            "Authorization": self.auth,
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "X-Guest-Token": await self._get_guest_token(),
        }

        params = {
            "variables": f'{{"tweetId":"{tweet_id}","withCommunity":false,"includePromotedContent":false,"withVoice":false}}',
            "features": '{"creator_subscriptions_tweet_preview_api_enabled":true,"premium_content_api_read_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"responsive_web_grok_analyze_button_fetch_trends_enabled":false,"responsive_web_grok_analyze_post_followups_enabled":false,"responsive_web_jetfuel_frame":false,"responsive_web_grok_share_attachment_enabled":true,"articles_preview_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"rweb_video_timestamps_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"profile_label_improvements_pcf_label_in_post_enabled":true,"rweb_tipjar_consumption_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"responsive_web_grok_image_annotation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_enhance_cards_enabled":false}',
        }

        tweet_info_url = (
            "https://api.x.com/graphql/nYHwgVXy3Hse2O5okbpFiQ/TweetResultByRestId"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(
                tweet_info_url, headers=headers, params=params
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message=f"Failed to get tweet info: response status {response.status}",
                        url=str(tweet_id),
                        critical=True,
                    )

    async def _download_file(self, url: str, filename: str, max_size: int = 0):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if max_size and "Content-Length" in response.headers:
                    if int(response.headers["Content-Length"]) > max_size:
                        return BotError(
                            code=ErrorCode.SIZE_CHECK_FAIL,
                            url=url,
                            critical=False,
                        )

                async with aiofiles.open(filename, "wb") as f:
                    async for chunk in response.content.iter_chunked(1024*8):
                        await f.write(chunk)

    def _sanitize_filename(self, filename: str) -> str:
        return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", filename)
