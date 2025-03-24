import asyncio
from aiogram import types, exceptions
import logging
from aiogram.utils.i18n import gettext as _
from config.secrets import ADMIN_ID


async def handle_download_error(message: types.Message, error: Exception) -> None:
    """Handle various download errors and send appropriate messages."""
    if isinstance(error, asyncio.CancelledError):
        await message.answer(_("Download canceled."))
    elif isinstance(error, exceptions.TelegramEntityTooLarge):
        await message.answer(_("Critical error #022 - media file is too large"))
    elif isinstance(error, ValueError) and str(error) == "Downloaded content is empty.":
        await message.answer(
            _(
                "Sorry, the download returned empty content. Please check the link and try again."
            )
        )
    else:
        logging.error(f"Download error: {error}")
        await message.answer(_("Sorry, there was an error. Try again later 🧡"))
        bot = message.bot
        if bot is None:
            return
        await bot.send_message(
            ADMIN_ID, f"Sorry, there was an error:\n {message.text}\n\n{error}"
        )
