from aiogram import types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.i18n import gettext as _

from loader import dp


@dp.message(Command("support"))
async def support_handler(message: types.Message, state: FSMContext):
    answer_message = _(
        "After some thought, I dare to leave a link to support the project. If you have a desire to improve the work of Charlotte, please follow this link. Every dollar helps keep Charlotte on a quality server just for you. You are not obligated to pay. Only if you have the desire!!!!\n https://buymeacoffee.com/jellytyan \n https://ko-fi.com/jellytyan"
    )

    await message.answer(answer_message, parse_mode=ParseMode.HTML)
