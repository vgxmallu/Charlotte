import asyncio
from typing import Dict, List, Optional, Tuple

from aiogram import types
from aiogram.enums import InputMediaType
from aiogram.utils.media_group import MediaGroupBuilder

from utils import delete_files, handle_download_error, truncate_string
from models.media_models import MediaContent, MediaType
from utils.error_handler import BotError, ErrorCode

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
    async def send_media_content(message: types.Message, content: List[MediaContent]) -> None:
        """Handle sending different types of media content."""
        try:
            media_items, audio_items, gif_items, caption = MediaHandler.parse_media(content=content)

            await MediaHandler.send_media_groups(message, media_items, caption)

            bot = message.bot
            if bot is None:
                return

            if audio_items:
                for audio in audio_items:
                    await bot.send_chat_action(message.chat.id, "upload_voice")
                    await MediaHandler.send_audio(message, audio)

            for gif in gif_items:
                await bot.send_chat_action(message.chat.id, "upload_video")
                await message.answer_animation(
                    animation=types.FSInputFile(gif.path), disable_notification=True
                )

                await delete_files([gif.path])
        except Exception as e:
            if not isinstance(e, BotError):
                e = BotError(
                    code=ErrorCode.DOWNLOAD_FAILED,
                    message=f"Media Handler: {str(e)}",
                    critical=True,
                    is_logged=True
                )
            await handle_download_error(message, e)

    @staticmethod
    async def send_media_groups(message: types.Message, content: List[MediaContent], caption: Optional[str]):
        """Send media groups with or without caption."""
        temp_media_path = []
        bot = message.bot
        if bot is None:
            return

        try:
            media_to_send_as_document: List[MediaContent] = []

            # Split media items into groups of 10
            for i in range(0, len(content), 10):
                media_group = MediaGroupBuilder()
                if caption and i == 0:
                    media_group.caption = caption

                group_items = content[i : i + 10]
                for item in group_items:
                    if item.type == MediaType.PHOTO:
                        media_group.add_photo(
                            media=types.FSInputFile(item.path),
                            type=InputMediaType.PHOTO,
                        )
                    elif item.type == MediaType.VIDEO:
                        media_group.add_video(
                            media=types.FSInputFile(item.path),
                            type=InputMediaType.VIDEO,
                            supports_streaming=True,
                            width=int(item.width) if item.width else None,
                            height=int(item.height) if item.height else None,
                            duration=int(item.duration) if item.duration else None
                        )
                    temp_media_path.append(item.path)

                    if item.original_size:
                        media_to_send_as_document.append(item)

                if group_items:
                    await bot.send_chat_action(message.chat.id, "upload_video")
                    await message.answer_media_group(
                        media=media_group.build(), disable_notification=True
                    )
                    await asyncio.sleep(1)

            for item in media_to_send_as_document:
                await bot.send_chat_action(message.chat.id, "upload_document")
                await message.answer_document(
                    document=types.FSInputFile(item.path),
                    disable_notification=True
                )
                await asyncio.sleep(0.5)

        except Exception as e:
            if not isinstance(e, BotError):
                e = BotError(
                    code=ErrorCode.DOWNLOAD_FAILED,
                    message=f"Media Handler: {str(e)}",
                    critical=True,
                    is_logged=True
                )
            await handle_download_error(message, e)
        finally:
            await delete_files(temp_media_path)


    @staticmethod
    async def send_audio(message: types.Message, audio: MediaContent) -> None:
        """Send audio file with or without cover."""
        try:
            await message.answer_audio(
                audio=types.FSInputFile(audio.path),
                disable_notification=True,
                thumbnail=types.FSInputFile(audio.cover) if audio.cover else None,
                title=audio.title,
                duration=int(audio.duration) if audio.duration else None,
                performer=audio.performer,
            )

            await delete_files([audio.path, audio.cover])
        except Exception as e:
            if not isinstance(e, BotError):
                e = BotError(
                    code=ErrorCode.DOWNLOAD_FAILED,
                    message=f"Media Handler: {str(e)}",
                    critical=True,
                    is_logged=True
                )
            await handle_download_error(message, e)


    @staticmethod
    def parse_media(content: List[MediaContent]) -> Tuple[List[MediaContent], List[MediaContent], List[MediaContent], Optional[str]]:
        """Parse media content to separate media, audio, gif items and extract caption."""

        audio_items = []
        gif_items = []
        media_items = []
        caption = None

        for item in content:
            if item.title:
                caption = truncate_string(item.title or "")

            if item.type in (MediaType.PHOTO, MediaType.VIDEO):
                media_items.append(item)
            elif item.type == MediaType.AUDIO:
                audio_items.append(item)
            elif item.type == MediaType.GIF:
                gif_items.append(item)

        return media_items, audio_items, gif_items, caption
