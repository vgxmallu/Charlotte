import asyncio
import json
import logging
from typing import Optional

from youtube_search import YoutubeSearch


async def search_music(artist: str, title: str) -> Optional[str]:
    try:
        search_query = f"{artist} - {title}"
        videos_search = YoutubeSearch(search_query, max_results=10)
        video_results_json = await asyncio.to_thread(lambda: videos_search.to_json())

        video_results = json.loads(video_results_json)

        if not video_results:
            return None

        # Filter videos by duration
        for video in video_results["videos"]:
            duration_str = video["duration"]
            try:
                duration = parse_duration(duration_str)
                if duration <= 600:  # 10 minutes or less
                    return f"https://youtube.com{video['url_suffix']}"
            except (ValueError, KeyError):
                continue

        return None

    except Exception as e:
        # Log the error here if you have a logging system
        logging.error(f"Error searching for music: {str(e)}")
        return None


def parse_duration(duration_str: str) -> int:
    """
    Parses a duration string in the format of HH:MM:SS, MM:SS, or SS and converts it into total seconds.

    Parameters:
    ----------
    duration_str : str
        The duration string to parse.

    Returns:
    -------
    int
        The total duration in seconds.
    """
    duration_parts = duration_str.split(":")
    if len(duration_parts) == 3:
        return int(duration_parts[0]) * 3600 + int(duration_parts[1]) * 60 + int(duration_parts[2])
    elif len(duration_parts) == 2:
        return int(duration_parts[0]) * 60 + int(duration_parts[1])
    return int(duration_parts[0])
