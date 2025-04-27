import asyncio
import logging

from aiogram import exceptions, types
from aiogram.utils.i18n import gettext as _

from config.secrets import ADMIN_ID

logger = logging.getLogger(__name__)


async def handle_download_error(message: types.Message, error: Exception, url: str | None) -> None:
    """Handle various download errors and send appropriate messages."""
    if isinstance(error, asyncio.CancelledError):
        await message.answer(_("Download canceled."))
    elif isinstance(error, exceptions.TelegramEntityTooLarge):
        await message.answer(_("Critical error #022 - media file is too large"))
    elif isinstance(error, ValueError) and str(error) == "Downloaded content is empty.":
        await message.answer(
            _("Sorry, the download returned empty content. Please check the link and try again.")
        )
    elif isinstance(error, ValueError) and str(error) == "Youtube Video size is too large":
        await message.answer(
            _("Wow, you tried to download too heavy video. Don't do this, pleeease 😭")
        )
        return
    else:
        logger.error(f"Download error: {error}")
        await message.answer(_("Sorry, there was an error. Try again later 🧡"))
    bot = message.bot
    if bot is None:
        return
    await bot.send_message(ADMIN_ID, f"Sorry, there was an error:\n {url}\n\n{error}")
