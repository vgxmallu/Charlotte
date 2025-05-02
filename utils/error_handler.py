import logging
from typing import Optional

from aiogram import types
from aiogram.utils.i18n import gettext as _

from config.secrets import ADMIN_ID

logger = logging.getLogger(__name__)


class BotError(Exception):
    def __init__(self, code: str, message: Optional[str] = None, url: Optional[str] = None, critical: bool = False, is_logged: bool = False):
        self.code = code  # For example: "E001"
        self.url = url or "None" # Media URL
        self.message = message  # Message for Owner
        self.critical = critical  # Send to owner?
        self.is_logged = is_logged # Need to be logged?
        super().__init__(message)

class ErrorCode:
    INVALID_URL = "E001"
    LARGE_FILE = "E002"
    SIZE_CHECK_FAIL = "E003"
    DOWNLOAD_FAILED = "E004"
    DOWNLOAD_CANCELLED = "E005"
    PLAYLIST_INFO_ERROR = "E006"
    INTERNAL_ERROR = "E500"


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
        await bot.send_message(ADMIN_ID, f"Sorry, there was an error:\n {error.url}\n\n```{error.message}```")

    if error.is_logged:
        logger.error(f"Error downloading media: {error.message}")
