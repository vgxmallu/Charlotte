from .base_service import BaseService
import re
import asyncio
import logging
import os
import urllib.request
from fake_useragent import UserAgent
import yt_dlp
import aiohttp

class TwitterService(BaseService):
    name = "Twitter"

    def __init__(self, output_path: str = "other/downloadsTemp"):
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
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
            with yt_dlp.YoutubeDL(self.yt_dlp_video_options) as ydl:
                info_dict = await asyncio.to_thread(ydl.extract_info, url, download=False)
                title = info_dict.get("title", "video")
                filename = ydl.prepare_filename(info_dict)

                await asyncio.to_thread(ydl.download, [url])

                if os.path.exists(filename):
                    result.append({"type": "video", "path": filename, "title": title})

        except yt_dlp.DownloadError:
            try:
                ua = UserAgent()

                auth = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
                guest_token_url = "https://api.twitter.com/1.1/guest/activate.json"

                headers = {
                    "Authorization": auth
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(guest_token_url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            guest_token = data.get('guest_token')
                        else:
                            raise Exception(f"Failed to get guest token: response status {response.status}")

                match = re.search(r"status/(\d+)", url)
                tweet_id = match.group(1)

                headers = {
                    'Authorization': auth,
                    'Content-Type': 'application/json',
                    'User-Agent': ua.random,
                    'X-Guest-Token': guest_token,
                }

                params = {
                    'variables': f'{{"tweetId":"{tweet_id}","withCommunity":false,"includePromotedContent":false,"withVoice":false}}',
                    'features': '{"creator_subscriptions_tweet_preview_api_enabled":true,"premium_content_api_read_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"responsive_web_grok_analyze_button_fetch_trends_enabled":false,"responsive_web_grok_analyze_post_followups_enabled":false,"responsive_web_jetfuel_frame":false,"responsive_web_grok_share_attachment_enabled":true,"articles_preview_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"rweb_video_timestamps_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"profile_label_improvements_pcf_label_in_post_enabled":true,"rweb_tipjar_consumption_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"responsive_web_grok_image_annotation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_enhance_cards_enabled":false}',
                }

                tweet_info_url = 'https://api.x.com/graphql/nYHwgVXy3Hse2O5okbpFiQ/TweetResultByRestId'
                async with aiohttp.ClientSession() as session:
                    async with session.get(tweet_info_url, headers=headers, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            image_datas = data["data"]["tweetResult"]["result"]["legacy"]["entities"]["media"]
                        else:
                            raise Exception(f"Failed to get guest token: response status {response.status}")

                for image_data in image_datas:
                    image_url = image_data["media_url_https"]

                    match = re.search(r"([^/]+\.jpg)", image_url)
                    filename = self.output_path + "/" + match.group(1)

                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_url) as response:
                            if response.status == 200:
                                with open(filename, 'wb') as f:
                                    f.write(await response.read())
                            else:
                                raise Exception(f"Failed to retrieve image. Status code: {response.status}")

                    result.append({"type": "image", "path": filename, "title": ""})

            except Exception as e:
                logging.error(f"Error downloading Twitter video: {str(e)}")
        except Exception as e:
            logging.error(f"Error downloading Twitter video: {str(e)}")

        return result

    def _sanitize_filename(self, filename: str) -> str:
        # Удаляем символы, не подходящие для имени файла
        return re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', filename)
