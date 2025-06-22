import asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import Message

async def send_message_with_fallback(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: str = None,
    reply_markup: any = None,
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> Message:
    for attempt in range(max_retries):
        try:
            message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return message
        except TelegramAPIError as e:
            if "Too Many Requests" in str(e):
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
            raise
    raise TelegramAPIError("Max retries exceeded for sending message")

async def edit_message_with_fallback(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: str = None,
    reply_markup: any = None,
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> Message:
    for attempt in range(max_retries):
        try:
            message = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return message
        except TelegramBadRequest as e:
            if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
                return await send_message_with_fallback(
                    bot, chat_id, text, parse_mode, reply_markup, max_retries, retry_delay
                )
        except TelegramAPIError as e:
            if "Too Many Requests" in str(e):
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
            raise
    raise TelegramAPIError("Max retries exceeded for editing message")