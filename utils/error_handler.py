import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from aiogram import types
from aiogram.enums import ParseMode
from aiogram.utils.i18n import gettext as _

from config.secrets import ADMIN_ID

logger = logging.getLogger(__name__)


class ErrorCode(Enum):
    INVALID_URL = "E001"
    LARGE_FILE = "E002"
    SIZE_CHECK_FAIL = "E003"
    DOWNLOAD_FAILED = "E004"
    DOWNLOAD_CANCELLED = "E005"
    PLAYLIST_INFO_ERROR = "E006"
    INTERNAL_ERROR = "E500"

@dataclass
class BotError(Exception):
    code: ErrorCode  # For example: "E001"
    url: Optional[str] = None # Media URL
    message: Optional[str] = None  # Message for Owner
    critical: bool = False # Send to owner?
    is_logged: bool = False # Need to be logged?


async def handle_download_error(message: types.Message, error: BotError) -> None:
    """Handle various download errors and send appropriate messages."""
    match error.code:
        case ErrorCode.INVALID_URL:
            await message.answer(_("I'm sorry. You may have provided a corrupted link, private content or 18+ content 🤯"))
        case ErrorCode.LARGE_FILE:
            await message.answer(_("Critical error #022 - media file is too large"))
        case ErrorCode.SIZE_CHECK_FAIL:
            await message.answer(_("Wow, you tried to download too heavy media. Don't do this, pleeease 😭"))
        case ErrorCode.DOWNLOAD_FAILED:
            await message.answer(_("Sorry, I couldn't download the media."))
        case ErrorCode.DOWNLOAD_CANCELLED:
            await message.answer(_("Download canceled."))
        case ErrorCode.PLAYLIST_INFO_ERROR:
            await message.answer(_("Get playlist items error"))
        case ErrorCode.INTERNAL_ERROR:
            await message.answer(_("Sorry, there was an error. Try again later 🧡"))
    if error.critical:
        bot = message.bot
        if bot is None:
            return
        await bot.send_message(ADMIN_ID, f"Sorry, there was an error:\n {error.url}\n\n<pre>{error.message}</pre>", parse_mode=ParseMode.HTML)

    if error.is_logged:
        logger.error(f"Error downloading media: {error.message}")
