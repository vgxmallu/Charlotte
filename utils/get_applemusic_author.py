import logging
import re

import aiohttp
from bs4 import BeautifulSoup

from config.secrets import APPLEMUSIC_DEV_TOKEN

logger = logging.getLogger(__name__)


async def get_applemusic_author(url: str):
    """Gets artist name, track title and track cover from Apple Music.

    This function first attempts to fetch track information using the Apple Music API
    if an APPLEMUSIC_DEV_TOKEN is available. If the API request fails, or if the
    token is not present, it falls back to parsing the HTML content of the page.

    Args:
        url (str): Track URL Apple Music.

    Returns:
        tuple: (artist_name, track_title, best_image_url) or (None, None, None)
               Returns None for all elements if information cannot be extracted.
    """
    artist_name, track_title, best_image_url = None, None, None

    # --- Попытка получить данные через API, если токен доступен ---
    if APPLEMUSIC_DEV_TOKEN:
        logger.info(f"Attempting to fetch data for {url} using Apple Music API.")
        try:
            headers = {
                'accept': '*/*',
                'authorization': f'Bearer {APPLEMUSIC_DEV_TOKEN}',
                'origin': 'https://music.apple.com',
                'referer': 'https://music.apple.com/',
            }

            # Извлекаем album_id и track_id из URL
            match = re.search(r'/album/[^/]+/(\d+)\?i=(\d+)', url)

            if match:
                album_id = match.group(1)
                track_id = match.group(2)

                async with aiohttp.ClientSession() as session:
                    api_url = f'https://amp-api.music.apple.com/v1/catalog/tr/albums/{album_id}'
                    async with session.get(api_url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            # Проверяем, что структура ответа соответствует ожидаемой
                            if data and 'data' in data and len(data['data']) > 0 and \
                                    'relationships' in data['data'][0] and \
                                    'tracks' in data['data'][0]['relationships'] and \
                                    'data' in data['data'][0]['relationships']['tracks']:

                                tracks = data['data'][0]['relationships']['tracks']['data']
                                track_info = next((item for item in tracks if item["id"] == str(track_id)), None)

                                if track_info and 'attributes' in track_info:
                                    # Извлекаем данные, если все найдено
                                    track_title = track_info['attributes'].get('name')
                                    artist_name = track_info['attributes'].get('artistName')
                                    cover_url = track_info['attributes'].get('artwork', {}).get('url')

                                    if cover_url:
                                        cover_url = cover_url.replace('{w}x{h}', '800x800')
                                        if '{f}' in cover_url:
                                            cover_url = cover_url.replace('{f}', '.jpg')

                                    # Если все необходимые данные получены, возвращаем их
                                    if artist_name and track_title and cover_url:
                                        logger.info("Successfully fetched data using Apple Music API.")
                                        return artist_name, track_title, cover_url
                                    else:
                                        logger.warning("Missing track/artist/cover attributes from API response. Falling back to HTML parsing.")
                                else:
                                    logger.warning("Track ID not found or missing attributes in API response. Falling back to HTML parsing.")
                            else:
                                logger.warning("Unexpected API response structure. Falling back to HTML parsing.")
                        else:
                            logger.error(f"API request failed with status {response.status} for {api_url}. Falling back to HTML parsing.")
            else:
                logger.warning(f"URL pattern did not match for API extraction for {url}. Falling back to HTML parsing.")

        except aiohttp.ClientError as e:
            logger.error(f"Apple Music API request error: {e}. Falling back to HTML parsing.")
        except KeyError as e:
            logger.error(f"KeyError encountered during Apple Music API response parsing: {e}. Falling back to HTML parsing.")
        except Exception as e:
            logger.error(f"An unexpected error occurred during Apple Music API attempt: {e}. Falling back to HTML parsing.")

    # --- Fallback к обычному парсингу HTML страницы ---
    logger.info(f"Falling back to HTML parsing for {url}.")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Error HTTP {response.status} when fetching {url} for HTML parsing.")
                    return None, None, None

                html_content = await response.text(encoding="utf-8")
                soup = BeautifulSoup(html_content, "html.parser")

                # Извлечение заголовка (title)
                title_tag = soup.find("title")
                title = title_tag.text.strip() if title_tag else ""

                # Парсинг заголовка для получения названия трека и исполнителя
                parts = re.split(r" - | – ", title, maxsplit=2)
                track_title = parts[0].strip() if len(parts) > 0 else None
                artist_name = (
                    parts[1].replace("Song by ", "").strip() if len(parts) > 1 else None
                )

                if not track_title or not artist_name:
                    logger.warning(
                        f"Could not identify the track or artist from the header during HTML parsing: '{title}'"
                    )
                    return None, None, None

                # Извлечение URL обложки
                picture_tag = soup.find("picture")
                best_image_url = None

                if picture_tag:
                    source_tag = picture_tag.find("source", {"type": "image/webp"})
                    if source_tag and "srcset" in source_tag.attrs:
                        srcset = " ".join(source_tag["srcset"].split()).strip()
                        matches = re.findall(r"(\S+)\s+(\d+)w", srcset)

                        if matches:
                            images = [
                                (url.lstrip(", "), int(size)) for url, size in matches
                            ]
                            images.sort(key=lambda x: x[1], reverse=True) # Сортируем по размеру, чтобы получить наибольшее
                            best_image_url = images[0][0]

                logger.info("Successfully parsed data from HTML.")
                return artist_name, track_title, best_image_url

    except Exception as e:
        logger.error(f"Apple Music HTML parsing error: {str(e)}. Could not extract data.")
        return None, None, None

