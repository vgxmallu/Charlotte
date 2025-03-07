import aiohttp
import logging
from bs4 import BeautifulSoup
import re


async def get_applemusic_author(url: str):
    """Gets artist name, track title and track cover from Apple Music.

    Args:
        url (str): Track URL Apple Music.

    Returns:
        tuple: (artist_name, track_title, best_image_url) or (None, None, None)
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Error HTTP {response.status} from request {url}")
                    return None, None, None

                html_content = await response.text(encoding="utf-8")
                soup = BeautifulSoup(html_content, 'html.parser')

                title_tag = soup.find('title')
                title = title_tag.text.strip() if title_tag else ""

                parts = re.split(r" - | – ", title, maxsplit=2)
                track_title = parts[0].strip() if len(parts) > 0 else None
                artist_name = parts[1].replace("Song by ", "").strip() if len(parts) > 1 else None

                if not track_title or not artist_name:
                    logging.warning(f"Could not identify the track or artist from the header: {title}")
                    return None, None, None

                picture_tag = soup.find('picture')
                best_image_url = None

                if picture_tag:
                    source_tag = picture_tag.find('source', {'type': 'image/webp'})
                    if source_tag and 'srcset' in source_tag.attrs:
                        srcset = " ".join(source_tag['srcset'].split()).strip()
                        matches = re.findall(r'(\S+)\s+(\d+)w', srcset)

                        if matches:
                            images = [(url.lstrip(", "), int(size)) for url, size in matches]
                            images.sort(key=lambda x: x[1], reverse=True)
                            best_image_url = images[0][0]

                return artist_name, track_title, best_image_url

    except Exception as e:
        logging.error(f"Apple Music parsing error: {str(e)}")
        return None, None, None
