from .base_service import BaseService
import re
import asyncio
import logging
import os
import urllib.request

import yt_dlp
from playwright.async_api import async_playwright

semaphore = asyncio.Semaphore(3)

browser_instance = None

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
            async with semaphore:
                try:
                    async with async_playwright() as p:
                        browser = await self._get_browser_instance(p)

                        page = await browser.new_page()

                        await page.route(
                            "**/*",
                            lambda route: route.abort() if route.request.resource_type in ["font", "stylesheet",
                                                                                           "media"] else route.continue_()
                        )

                        await page.goto(url)

                        await page.wait_for_selector('img[src*="/media/"]', timeout=5000)

                        images = await page.eval_on_selector_all("img[src*='/media/']",
                                                                 "imgs => imgs.map(img => img.src.split('&name')[0])")
                        tweet_texts = await page.eval_on_selector_all(
                            "div[data-testid='tweetText'] span",
                            "spans => spans.map(span => span.innerText)"
                        )
                        full_text = " ".join(tweet_texts) if tweet_texts else ""
                        title = f"{url.split('/')[3]} - {full_text}"

                        for image in images:
                            image = image.split("&name")[0]
                            filename = os.path.join(self.output_path, self._sanitize_filename(f"{image.split('/')[-1]}.jpg"))
                            try:
                                urllib.request.urlretrieve(image, filename)
                                result.append({"type": "image", "path": filename, "title": title})
                            except Exception as e:
                                print(f"Failed to download image {image}: {e}")
                                continue

                except Exception as e:
                    print(f"Error downloading Twitter post: {str(e)}")

                finally:
                    await self._close_browser()

        except Exception as e:
            logging.error(f"Error downloading Twitter video: {str(e)}")

        return result

    def _sanitize_filename(self, filename: str) -> str:
        # Удаляем символы, не подходящие для имени файла
        return re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', filename)


    async def _get_browser_instance(self, playwright):
        global browser_instance
        if not browser_instance:
            browser_instance = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--ignore-certificate-errors",
                    "--disable-gpu",
                    "--log-level=3",
                    "--disable-notifications",
                    "--disable-popup-blocking",
                ]
            )
        return browser_instance


    async def _close_browser(self) -> None:
        global browser_instance
        if browser_instance:
            await browser_instance.close()
            browser_instance = None
