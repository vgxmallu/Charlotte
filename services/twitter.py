import logging
import os
import re
from typing import Any, Dict

import aiofiles
import aiohttp
from fake_useragent import UserAgent

from .base_service import BaseService

ua = UserAgent()

class TwitterService(BaseService):
    name = "Twitter"

    def __init__(self, output_path: str = "other/downloadsTemp"):
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        self.auth = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
        self.user_agent = ua.random
        self.yt_dlp_video_options = {
            "outtmpl": f"{output_path}/%(title)s.%(ext)s",
        }

    def is_supported(self, url: str) -> bool:
        return bool(re.match(r'https://(?:twitter|x)\.com/\w+/status/\d+', url))

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> list:
        result = []
        try:
            match = re.search(r"status/(\d+)", url)
            tweet_id = int(match.group(1))

            tweet_dict = await self._get_tweet_info(tweet_id)

            medias = tweet_dict["data"]["tweetResult"]["result"]["legacy"]["extended_entities"]["media"]

            for media in medias:
                if media["type"] == "photo":
                    photo_url = media["media_url_https"]
                    match = re.search(r"([^/]+\.jpg)", photo_url)
                    filename = self.output_path + "/" + match.group(1)

                    await self._download_photo(photo_url, filename)
                    result.append({"type": "image", "path": filename})

                elif media["type"] == "video":
                    variants = media["video_info"]["variants"]

                    video_with_highest_bitrate = max(
                        (variant for variant in variants if 'bitrate' in variant),
                        key=lambda x: x['bitrate']
                    )

                    video_url = video_with_highest_bitrate["url"]

                    match = re.search(r"([^/]+\.mp4)", video_url)
                    filename = self.output_path + "/" + match.group(1)

                    await self._download_video(video_url, filename)
                    result.append({"type": "video", "path": filename})

                elif media["type"] == "animated_gif":
                    variant = media["video_info"]["variants"][0]

                    video_url = variant["url"]

                    match = re.search(r"([^/]+\.mp4)", video_url)
                    filename = self.output_path + "/" + match.group(1)

                    await self._download_video(video_url, filename)
                    result.append({"type": "gif", "path": filename})


            author = tweet_dict["data"]["tweetResult"]["result"]["core"]["user_results"]["result"]["legacy"]["name"]
            title = tweet_dict["data"]["tweetResult"]["result"]["legacy"]["full_text"]

            result.append({"type": "title", "title": f"{author} - {title}"})

        except Exception as e:
            logging.error(f"Error downloading Twitter video: {str(e)}")

        return result

    async def _get_guest_token(self) -> int:
        guest_token_url = "https://api.twitter.com/1.1/guest/activate.json"

        headers = {
            "Authorization": self.auth
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(guest_token_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('guest_token')
                else:
                    raise Exception(f"Failed to get guest token: response status {response.status}")

    async def _get_tweet_info(self, tweet_id: int) -> Dict[str, Any]:
        headers = {
            'Authorization': self.auth,
            'Content-Type': 'application/json',
            'User-Agent': self.user_agent,
            'X-Guest-Token': await self._get_guest_token(),
        }

        params = {
            'variables': f'{{"tweetId":"{tweet_id}","withCommunity":false,"includePromotedContent":false,"withVoice":false}}',
            'features': '{"creator_subscriptions_tweet_preview_api_enabled":true,"premium_content_api_read_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"responsive_web_grok_analyze_button_fetch_trends_enabled":false,"responsive_web_grok_analyze_post_followups_enabled":false,"responsive_web_jetfuel_frame":false,"responsive_web_grok_share_attachment_enabled":true,"articles_preview_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"rweb_video_timestamps_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"profile_label_improvements_pcf_label_in_post_enabled":true,"rweb_tipjar_consumption_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"responsive_web_grok_image_annotation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_enhance_cards_enabled":false}',
        }

        tweet_info_url = 'https://api.x.com/graphql/nYHwgVXy3Hse2O5okbpFiQ/TweetResultByRestId'
        async with aiohttp.ClientSession() as session:
            async with session.get(tweet_info_url, headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Failed to get guest token: response status {response.status}")

    async def _download_photo(self, url: str, filename: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    async with aiofiles.open(filename, 'wb') as f:
                        await f.write(await response.read())
                else:
                    raise Exception(f"Failed to retrieve image. Status code: {response.status}")

    async def _download_video(self, url: str, filename: str) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > 50 * 1024 * 1024:
                        logging.warning(f"Файл {filename} слишком большой (>50MB).")
                        return

                    async with aiofiles.open(filename, 'wb') as f:
                        async for chunk in response.content.iter_chunked(1024):
                            await f.write(chunk)
        except Exception as e:
            logging.error(f"Ошибка загрузки видео: {e}")

    def _sanitize_filename(self, filename: str) -> str:
        # Удаляем символы, не подходящие для имени файла
        return re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', filename)
