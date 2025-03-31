import asyncio
from pathlib import Path
from typing import Dict, List

from aiogram import types
from aiogram.enums import InputMediaType
from aiogram.utils.media_group import MediaGroupBuilder

from utils import delete_files, handle_download_error, truncate_string

MediaContent = Dict[str, str]
MediaList = List[MediaContent]
user_tasks: Dict[int, asyncio.Task] = {}


class TaskManager:
    def add_task(self, user_id: int, task: asyncio.Task) -> None:
        """Add a download task for a user."""
        user_tasks[user_id] = task

    def remove_task(self, user_id: int) -> None:
        """Remove a download task for a user."""
        if user_id in user_tasks:
            user_tasks.pop(user_id)

    def cancel_task(self, user_id: int) -> bool:
        """Cancel a download task for a user."""
        if user_id not in user_tasks:
            return False

        task = user_tasks[user_id]

        if task and not task.done():
            task.cancel()
            self.remove_task(user_id)
            return True
        else:
            return False


class MediaHandler:
    @staticmethod
    async def send_media_content(message: types.Message, content: MediaList) -> None:
        """Handle sending different types of media content."""
        temp_medias = []
        audio = None
        gifs = []
        media_items = []
        caption = None

        try:
            for item in content:
                if item["type"] == "error":
                    raise ValueError(item["message"])
                if item["type"] == "title":
                    caption = truncate_string(item["title"])
                    continue

                media_path = Path(item["path"])
                absolute_path = media_path.resolve()
                temp_medias.append(absolute_path)

                if item["type"] == "image":
                    media_items.append({"type": "photo", "path": absolute_path})
                elif item["type"] == "video":
                    media_items.append({"type": "video", "path": absolute_path, "width": item.get("width", None), "height": item.get("height", None), "duration": item.get("duration", None)})
                elif item["type"] == "audio":
                    audio = item
                    continue
                elif item["type"] == "gif":
                    gifs.append(media_path)
                    continue
        except Exception as e:
            await delete_files(temp_medias)
            await handle_download_error(message, e, None)
        try:
            bot = message.bot
            if bot is None:
                return

            # Split media items into groups of 10
            for i in range(0, len(media_items), 10):
                media_group = MediaGroupBuilder()
                if caption and i == 0:
                    media_group.caption = caption

                group_items = media_items[i : i + 10]
                for item in group_items:
                    if item["type"] == "photo":
                        media_group.add_photo(
                            media=types.FSInputFile(item["path"]),
                            type=InputMediaType.PHOTO,
                        )
                    elif item["type"] == "video":
                        media_group.add_video(
                            media=types.FSInputFile(item["path"]),
                            type=InputMediaType.VIDEO,
                            supports_streaming=True,
                            width=item["width"],
                            height=item["height"],
                            duration=item["duration"]
                        )

                if group_items:
                    await bot.send_chat_action(message.chat.id, "upload_video")
                    await message.answer_media_group(
                        media=media_group.build(), disable_notification=True
                    )
                    await asyncio.sleep(1)

            if audio:
                await bot.send_chat_action(message.chat.id, "upload_voice")
                await MediaHandler.send_audio(message, audio)

            for gif in gifs:
                await bot.send_chat_action(message.chat.id, "upload_video")
                await message.answer_animation(
                    animation=types.FSInputFile(gif), disable_notification=True
                )
        except Exception as e:
            await handle_download_error(message, e, None)
        finally:
            await delete_files(temp_medias)

    @staticmethod
    async def send_audio(message: types.Message, audio: Dict) -> None:
        """Send audio file with or without cover."""
        cover_path = audio.get("cover", None)
        try:
            if cover_path:
                cover_path = Path(cover_path)
                absolute_cover_path = cover_path.resolve()

                await message.answer_audio(
                    audio=types.FSInputFile(audio["path"]),
                    disable_notification=True,
                    thumbnail=types.FSInputFile(cover_path),
                )

                await delete_files([audio["path"], absolute_cover_path])
            else:
                await message.answer_audio(
                    audio=types.FSInputFile(audio["path"]), disable_notification=True
                )
                await delete_files([audio["path"]])
        except Exception as e:
            await handle_download_error(message, e, None)
