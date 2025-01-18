import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Optional

from aiogram import types, exceptions
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import InputMediaType
from aiogram.utils.i18n import gettext as _

from config.secrets import ADMIN_ID
from filters.url_filter import UrlFilter
from loader import dp
from utils import delete_files, get_service_handler

# Type aliases for better readability
MediaContent = Dict[str, str]
MediaList = List[MediaContent]
user_tasks: Dict[int, asyncio.Task] = {}

class DownloadManager:
    async def is_user_downloading(self, user_id: int, message: types.Message) -> bool:
        """Check if user already has an active download."""
        if user_id in user_tasks:
            await message.reply(_("You already have an active download. Cancel it with /cancel."))
            return True
        return False

    def add_task(self, user_id: int, task: asyncio.Task) -> None:
        """Add a download task for a user."""
        user_tasks[user_id] = task

    def remove_task(self, user_id: int) -> None:
        """Remove a download task for a user."""
        if user_id in user_tasks:
            user_tasks.pop(user_id)

    def cancel_task(self, user_id: int) -> bool:
        """Cancel a download task for a user."""
        print(user_tasks)
        if user_id not in user_tasks:
            return False  # No task to cancel

        task = user_tasks[user_id]

        if task and not task.done():
            task.cancel()
            self.remove_task(user_id)
            return True
        else:
            return False

download_manager = DownloadManager()

class MediaHandler:
    @staticmethod
    async def send_media_content(message: types.Message, content: MediaList) -> None:
        """Handle sending different types of media content."""
        media_group = MediaGroupBuilder()
        temp_medias = []
        audio = None
        has_video = False

        for item in content:
            media_path = Path(item["path"])
            absolute_path = media_path.resolve()
            temp_medias.append(absolute_path)

            if item["type"] == "image":
                media_group.add_photo(media=types.FSInputFile(absolute_path), type=InputMediaType.PHOTO)
                has_video = True
            elif item["type"] == "video":
                media_group.add_video(media=types.FSInputFile(absolute_path), type=InputMediaType.VIDEO)
                has_video = True
            elif item["type"] == "audio":
                audio = item

        try:
            if has_video:
                await message.bot.send_chat_action(message.chat.id, "upload_video")
                await message.answer_media_group(media=media_group.build(), disable_notification=True)

            if audio:
                await message.bot.send_chat_action(message.chat.id, "upload_voice")
                await MediaHandler.send_audio(message, audio)
        finally:
            await delete_files(temp_medias)

    @staticmethod
    async def send_audio(message: types.Message, audio: Dict) -> None:
        """Send audio file with or without cover."""
        cover_path = audio.get("cover")
        if cover_path:
            cover_path = Path(cover_path)
            absolute_cover_path = cover_path.resolve()

            await message.answer_audio(
                audio=types.FSInputFile(audio["path"]),
                disable_notification=True,
                thumbnail=types.FSInputFile(cover_path)
            )

            await delete_files([absolute_cover_path])
        else:
            await message.answer_audio(
                audio=types.FSInputFile(audio["path"]),
                disable_notification=True
            )

async def handle_download_error(message: types.Message, error: Exception) -> None:
    """Handle various download errors and send appropriate messages."""
    if isinstance(error, asyncio.CancelledError):
        await message.answer(_("Download canceled."))
    elif isinstance(error, exceptions.TelegramEntityTooLarge):
        await message.answer(_("Critical error #022 - media file is too large"))
    elif isinstance(error, ValueError) and str(error) == "Downloaded content is empty.":
        await message.answer(_("Sorry, the download returned empty content. Please check the link and try again."))
    else:
        logging.error(f"Download error: {error}")
        await message.answer(_("Sorry, there was an error. Try again later 🧡"))
        await message.bot.send_message(ADMIN_ID, f"Sorry, there was an error:\n {message.text}\n\n{error}")

@dp.message(UrlFilter())
async def url_handler(message: types.Message) -> None:
    """Handle incoming URL messages and manage downloads."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    if await download_manager.is_user_downloading(user_id, message):
        return

    url = message.text
    service = get_service_handler(url)

    if service.name == "Youtube":
        markup = InlineKeyboardBuilder()
        markup.add(types.InlineKeyboardButton(text=_("Video"), callback_data="video"))
        markup.add(types.InlineKeyboardButton(text=_("Audio"), callback_data="audio"))

        await message.reply(_("Choose a format to download:"), reply_markup=markup.as_markup())
    else:
        if service.is_playlist(url):
            task = asyncio.create_task(handle_playlist_download(service, url, message))
        else:
            task = asyncio.create_task(handle_single_download(service, url, message))

        download_manager.add_task(user_id, task)

@dp.callback_query()
async def format_choice_handler(callback_query: types.CallbackQuery):
    choice = callback_query.data
    user_id = callback_query.from_user.id

    url = callback_query.message.reply_to_message.text
    service = get_service_handler(url)

    if service.name != "Youtube":
        await callback_query.message.edit_text(_("The selection format is only available for YouTube."))
        return

    if choice == "video":
        task = asyncio.create_task(handle_single_download(service, url, callback_query.message, format_choice=f"video:{user_id}"))
    elif choice == "audio":
        task = asyncio.create_task(handle_single_download(service, url, callback_query.message, format_choice=f"audio:{user_id}"))

    download_manager.add_task(user_id, task)
    await callback_query.message.delete()


async def handle_single_download(service, url: str, message: types.Message, format_choice: Optional[str] = None) -> None:
    """Handle download of a single media item."""
    user_id = 0

    try:
        if service.name == "Youtube" and format_choice:
            format, user_id = format_choice.split(":")
            content = await service.download(url, format)
        else:
            await message.bot.send_chat_action(message.chat.id, "record_video")
            user_id = message.from_user.id
            content = await service.download(url)

        if not content:
            raise ValueError("Downloaded content is empty.")

        await MediaHandler.send_media_content(message, content)

    except Exception as e:
        await handle_download_error(message, e)

    finally:
        download_manager.remove_task(int(user_id))

async def handle_playlist_download(service, url: str, message: types.Message) -> None:
    """Handle download of a playlist."""
    try:
        tracks = service.get_playlist_tracks(url)
        for track in tracks:
            if message.from_user.id not in user_tasks:
                break

            try:
                await message.bot.send_chat_action(message.chat.id, "record_voice")
                file = await service.download(track)
                await MediaHandler.send_audio(message, file[0])
                await delete_files([file[0]["path"], file[0]["cover"]])
            except Exception:
                continue

        await message.reply(_("Download completed."))
    except Exception as e:
        await handle_download_error(message, e)
    finally:
        download_manager.remove_task(message.from_user.id)
