import asyncio
import random
import time
from aiogram import Bot, Router, types, html
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters.callback_data import CallbackData
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from .database import add_ticker, remove_ticker, get_tickers
from .crypto_api import get_current_price, get_crypto_price, subscribe_ticker, unsubscribe_ticker, websocket_manager
from .utils import send_message_with_fallback, edit_message_with_fallback

router = Router()

EXEMPT_MESSAGES = [
    "💎 Bot's already running. Wanna /stop it?",
    "💰 Kickin' off crypto tracking...",
    "📋 Commands:\n\n/start - Kick off tracking\n/stop - Shut it down\n/add ticker - Track a coin\n/remove ticker - Remove a coin\n/chart ticker time - Get a price chart\n/convert value ticker to coin - Swap coins\n/help - This list\n\n📉 - Price dipped\n📈 - Price popped\n\n⚠️ Only Binance coins work!",
    "🔥 Yo, I'm here! Hit /help to check my vibe."
]

class DeleteMessagesMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Message) and event.text:
            try:
                await event.delete()
            except Exception:
                pass
        return await handler(event, data)

class PinCallbackData(CallbackData, prefix="pin"):
    action: str

active_tasks = {}

def normalize_ticker(ticker: str) -> str:
    return 'USDC' if ticker.upper() == 'USDT' else ticker.upper()

async def is_valid_binance_ticker(ticker: str, currency: str = 'USDC') -> tuple[bool, str]:
    prices, error = await get_current_price([ticker], currency)
    if error or prices.get(ticker) is None:
        return False, f"Yo, {ticker} ain't on Binance. Try BTC or ETH."
    return True, ""

async def is_user_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception:
        return False

async def update_prices(bot: Bot, chat_id: int, message_id: int = None, previous_prices: dict = None, retries=5, delay=5):
    for attempt in range(retries):
        try:
            tickers = get_tickers(chat_id)
            if not tickers:
                emojis = ['💸', '🚀', '💰', '🌙', '⭐', '🖖',  '🔥', '💎']
                message = f"{random.choice(emojis)} No coins tracked. Hit {html.code('/add ticker')} to start."
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📌 Pin", callback_data=PinCallbackData(action="pin_message").pack())]
                ])
                if message_id:
                    await edit_message_with_fallback(bot, chat_id, message_id, message, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                else:
                    sent_message = await send_message_with_fallback(bot, chat_id, message, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                    message_id = sent_message.message_id
                return message_id, previous_prices or {}
            prices, error = await get_current_price(tickers, 'USDC', force_refresh=True)
            if error:
                raise Exception(error)
            previous_prices = previous_prices or {}
            message_text = []
            new_prices = {}
            invalid_tickers = []
            emojis = ['💸', '🚀', '💰', '🌙', '⭐', '🖖',  '🔥', '💎']
            for ticker in tickers:
                price = prices.get(ticker)
                if price is None:
                    invalid_tickers.append(ticker)
                    continue
                prev_price = previous_prices.get(ticker)
                change_emoji = ""
                if prev_price is not None:
                    change_percent = ((price - prev_price) / prev_price * 100) if prev_price != 0 else 0
                    if abs(change_percent) == 0:
                        change_emoji = "➡️"
                    elif change_percent > 0:
                        change_emoji = "📈"
                    elif change_percent < 0:
                        change_emoji = "📉"
                new_prices[ticker] = price
                price_str = f"${price:.2f}"
                message_text.append(f"{random.choice(emojis)} {html.bold(ticker.upper())}: {price_str} {change_emoji}")
            if not message_text:
                message_text.append(f"{random.choice(emojis)} No valid coins to show.")
            for ticker in invalid_tickers:
                remove_ticker(chat_id, ticker)
                await unsubscribe_ticker(ticker)
            message = "\n".join(message_text)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📌 Pin", callback_data=PinCallbackData(action="pin_message").pack())]
            ])
            if message_id:
                await edit_message_with_fallback(bot, chat_id, message_id, message, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            else:
                sent_message = await send_message_with_fallback(bot, chat_id, message, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                message_id = sent_message.message_id
            return message_id, new_prices
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(delay * (2 ** attempt))
            else:
                sent_message = await send_message_with_fallback(
                    bot, chat_id,
                    f"⚠️ Price update failed after {retries} tries: {str(e)}. Try later.",
                    parse_mode=ParseMode.HTML
                )
                return message_id, previous_prices or {}
    return message_id, previous_prices

async def price_update_task(bot: Bot, chat_id: int, initial_message_id: int = None):
    if chat_id in active_tasks:
        active_tasks[chat_id]['task'].cancel()
        try:
            await active_tasks[chat_id]['task']
        except asyncio.CancelledError:
            pass
    task = asyncio.current_task()
    active_tasks[chat_id] = {'task': task, 'message_id': initial_message_id}
    message_id = initial_message_id
    previous_prices = {}
    try:
        while True:
            start_time = time.time()
            result = await update_prices(bot, chat_id, message_id, previous_prices)
            if result is not None:
                message_id, previous_prices = result
                active_tasks[chat_id]['message_id'] = message_id
            elapsed = time.time() - start_time
            await asyncio.sleep(max(10 - elapsed, 0))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        await send_message_with_fallback(
            bot, chat_id,
            f"⚠️ Price tracking crashed: {str(e)}. Use /start to restart.",
            parse_mode=ParseMode.HTML
        )
    finally:
        active_tasks.pop(chat_id, None)

@router.callback_query(PinCallbackData.filter())
async def button_callback(callback: types.CallbackQuery, callback_data: PinCallbackData):
    if callback_data.action == "pin_message":
        chat_id = callback.message.chat.id
        user_id = callback.from_user.id
        if callback.message.chat.type in ['group', 'supergroup'] and not await is_user_admin(callback.bot, chat_id, user_id):
            await callback.answer("Only admins can pin, fam.", show_alert=True)
            return
        try:
            await callback.bot.pin_chat_message(
                chat_id=chat_id,
                message_id=callback.message.message_id,
                disable_notification=True
            )
            await callback.answer("Pinned it!")
        except Exception as e:
            await callback.answer(f"Can't pin: {str(e)}. Check my perms.", show_alert=True)

async def initialize_tickers(bot: Bot, chat_id: int):
    default_tickers = ['SOL', 'ETH', 'BTC']
    added = []
    for ticker in default_tickers:
        is_valid, _ = await is_valid_binance_ticker(ticker, 'USDC')
        if is_valid:
            add_ticker(chat_id, ticker)
            await subscribe_ticker(ticker)
            added.append(ticker)
    if added:
        prices, _ = await get_current_price(added, 'USDC', force_refresh=True)
        if prices and any(price for price in prices.values()):
            message_text = []
            emojis = ['💸', '🚀', '💰', '🌙', '⭐', '🖖',  '🔥', '💎']
            for ticker in added:
                price = prices.get(ticker)
                if price:
                    message_text.append(f"{random.choice(emojis)} {html.bold(ticker.upper())}: ${price:.2f}")
            message = "\n".join(message_text)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📌 Pin", callback_data=PinCallbackData(action="pin_message").pack())]
            ])
            price_message = await send_message_with_fallback(bot, chat_id, message, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            return price_message.message_id
    return None

@router.message(CommandStart())
async def start(message: types.Message, bot: Bot):
    chat_id = message.chat.id
    emojis = ['💸', '🚀', '💰', '🌙', '⭐', '🖖', '🔥', '💎']
    if chat_id in active_tasks and not active_tasks[chat_id]['task'].done():
        await send_message_with_fallback(
            bot, chat_id,
            f"💎 Bot's already running. Wanna /stop it?",
            parse_mode=ParseMode.HTML
        )
        return
    await send_message_with_fallback(
        bot, chat_id,
        f"💰 Kickin' off crypto tracking...",
        parse_mode=ParseMode.HTML
    )
    try:
        chat = await bot.get_chat(chat_id)
        bot_info = await bot.get_me()
        if chat.pinned_message and chat.pinned_message.from_user and chat.pinned_message.from_user.id == bot_info.id:
            try:
                await bot.unpin_chat_message(chat_id=chat_id, message_id=chat.pinned_message.message_id)
            except Exception as e:
                await send_message_with_fallback(
                    bot, chat_id,
                    f"⚠️ Can't unpin old message: {str(e)}. Unpin it yourself or check permissions.",
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        await send_message_with_fallback(
            bot, chat_id,
            f"⚠️ Pinned message check failed: {str(e)}.",
            parse_mode=ParseMode.HTML
        )
    initial_message_id = await initialize_tickers(bot, chat_id)
    asyncio.create_task(price_update_task(bot, chat_id, initial_message_id))

@router.message(Command('stop'))
async def stop(message: types.Message, bot: Bot):
    chat_id = message.chat.id
    emojis = ['💸', '🚀', '💰', '🌙', '⭐', '🖖', '🔥', '💎']
    if chat_id not in active_tasks:
        await send_message_with_fallback(
            bot, chat_id,
            f"{random.choice(emojis)} Ain't trackin' nothin'. Hit /start.",
            parse_mode=ParseMode.HTML
        )
        return
    active_tasks[chat_id]['task'].cancel()
    try:
        await active_tasks[chat_id]['task']
    except asyncio.CancelledError:
        pass
    active_tasks.pop(chat_id, None)
    await send_message_with_fallback(
        bot, chat_id,
        f"🌙 Tracking stopped.",
        parse_mode=ParseMode.HTML
    )

@router.message(lambda message: message.message_id in [active_tasks.get(message.chat.id, {}).get('message_id')])
async def handle_price_message_delete(message: types.Message, bot: Bot):
    chat_id = message.chat.id
    emojis = ['💸', '🚀', '💰', '🌙', '⭐', '🖖', '🔥', '💎']
    if chat_id in active_tasks:
        active_tasks[chat_id]['task'].cancel()
        try:
            await active_tasks[chat_id]['task']
        except asyncio.CancelledError:
            pass
        active_tasks.pop(chat_id, None)
        await send_message_with_fallback(
            bot, chat_id,
            f"{random.choice(emojis)} Tracking stopped 'cause you deleted the prices.",
            parse_mode=ParseMode.HTML
        )

@router.message(Command('add'))
async def add(message: types.Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    emojis = ['💸', '🔥', '💎']
    if message.chat.type in ['group', 'supergroup'] and not await is_user_admin(bot, chat_id, user_id):
        await send_message_with_fallback(
            bot, chat_id,
            f"{random.choice(emojis)} Only admins can add coins here.",
            parse_mode=ParseMode.HTML
        )
        return
    args = message.text.split()
    if len(args) != 2:
        await send_message_with_fallback(
            bot, chat_id,
            f"📈 Use: {html.code('/add ticker')} (e.g., {html.code('/add BTC')})",
            parse_mode=ParseMode.HTML
        )
        return
    ticker = normalize_ticker(args[1])
    is_valid, error = await is_valid_binance_ticker(ticker, 'USDC')
    if not is_valid:
        await send_message_with_fallback(
            bot, chat_id,
            f"{random.choice(emojis)} {error}",
            parse_mode=ParseMode.HTML
        )
        return
    if ticker in get_tickers(chat_id):
        await send_message_with_fallback(
            bot, chat_id,
            f"{random.choice(emojis)} {html.bold(ticker)} already in the list.",
            parse_mode=ParseMode.HTML
        )
        return
    add_ticker(chat_id, ticker)
    await subscribe_ticker(ticker)
    await send_message_with_fallback(
        bot, chat_id,
        f"✅ Added {html.bold(ticker)}",
        parse_mode=ParseMode.HTML
    )
    if chat_id in active_tasks and not active_tasks[chat_id]['task'].done():
        await update_prices(bot, chat_id, message_id=active_tasks[chat_id]['message_id'], previous_prices={})

@router.message(Command('remove'))
async def remove(message: types.Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    emojis = ['💸', '🚀', '💰', '🌙', '⭐', '🖖',  '🔥', '💎']
    if message.chat.type in ['group', 'supergroup'] and not await is_user_admin(bot, chat_id, user_id):
        await send_message_with_fallback(
            bot, chat_id,
            f"{random.choice(emojis)} Only admins can remove coins here.",
            parse_mode=ParseMode.HTML
        )
        return
    args = message.text.split()
    if len(args) != 2:
        await send_message_with_fallback(
            bot, chat_id,
            f"📉 Use: {html.code('/remove ticker')} (e.g., {html.code('/remove BTC')})",
            parse_mode=ParseMode.HTML
        )
        return
    ticker = normalize_ticker(args[1])
    rows_affected = remove_ticker(chat_id, ticker)
    if rows_affected > 0:
        await unsubscribe_ticker(ticker)
        await send_message_with_fallback(
            bot, chat_id,
            f"🗑 Removed {html.bold(ticker)}",
            parse_mode=ParseMode.HTML
        )
    else:
        await send_message_with_fallback(
            bot, chat_id,
            f"💥 {html.bold(ticker)} ain't tracked.",
            parse_mode=ParseMode.HTML
        )

@router.message(Command('chart'))
async def chart(message: types.Message, bot: Bot):
    emojis = ['💸', '🚀', '💰', '🌙', '⭐', '🖖',  '🔥', '💎']
    args = message.text.split()
    if len(args) != 3:
        await send_message_with_fallback(
            bot, message.chat.id,
            f"📊 Use: {html.code('/chart ticker time')}\n(e.g., {html.code('/chart BTC 7d')})",
            parse_mode=ParseMode.HTML
        )
        return
    ticker = normalize_ticker(args[1])
    time_period = args[2]
    is_valid, error = await is_valid_binance_ticker(ticker, 'USDC')
    if not is_valid:
        await send_message_with_fallback(
            bot, message.chat.id,
            f"{random.choice(emojis)} {error}",
            parse_mode=ParseMode.HTML
        )
        return
    img_buffer, error = await get_crypto_price(ticker, time_period, 'USDC')
    if error:
        await send_message_with_fallback(
            bot, message.chat.id,
            f"💥 {error}",
            parse_mode=ParseMode.HTML
        )
        return
    try:
        photo = BufferedInputFile(img_buffer.read(), filename=f"{ticker}_chart.png")
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo,
            caption=f"{random.choice(emojis)} {html.bold(ticker.upper())} chart for {time_period}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        if "can't parse entities" in str(e).lower():
            photo = BufferedInputFile(img_buffer.read(), filename=f"{ticker}_chart.png")
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=photo,
                caption=f"{random.choice(emojis)} {ticker.upper()} chart for {time_period}",
                parse_mode=None
            )
        else:
            raise

@router.message(Command('convert'))
async def convert(message: types.Message, bot: Bot):
    emojis = ['💸', '🚀', '💰', '🌙', '⭐', '🖖',  '🔥', '💎']
    args = message.text.split()
    if len(args) != 5 or args[3].lower() != 'to':
        await send_message_with_fallback(
            bot, message.chat.id,
            f"💱 Use: {html.code('/convert value ticker to coin')}\n(e.g., {html.code('/convert 0.1 BTC to USDC')})",
            parse_mode=ParseMode.HTML
        )
        return
    try:
        value = float(args[1])
        source_ticker = normalize_ticker(args[2])
        target_ticker = normalize_ticker(args[4])
    except ValueError:
        await send_message_with_fallback(
            bot, message.chat.id,
            f"💥 Yo, use a number for the value.",
            parse_mode=ParseMode.HTML
        )
        return
    is_valid, error = await is_valid_binance_ticker(source_ticker)
    if not is_valid:
        await send_message_with_fallback(
            bot, message.chat.id,
            f"{random.choice(emojis)} {error}",
            parse_mode=ParseMode.HTML
        )
        return
    is_valid, error = await is_valid_binance_ticker(target_ticker)
    if not is_valid:
        await send_message_with_fallback(
            bot, message.chat.id,
            f"{random.choice(emojis)} {error}",
            parse_mode=ParseMode.HTML
        )
        return
    prices, error = await get_current_price([source_ticker, target_ticker], 'USDC')
    if error:
        return
    source_price = prices.get(source_ticker)
    target_price = prices.get(target_ticker)
    if source_price is None or target_price is None:
        await send_message_with_fallback(
            bot, message.chat.id,
            f"💥 No price data for {html.bold(source_ticker)} or {html.bold(target_ticker)}",
            parse_mode=ParseMode.HTML
        )
        return
    if target_price == 0:
        await send_message_with_fallback(
            bot, message.chat.id,
            f"💥 Can't convert to {html.bold(target_ticker)}: price is zero.",
            parse_mode=ParseMode.HTML
        )
        return
    converted_value = (value * source_price) / target_price
    await send_message_with_fallback(
        bot, message.chat.id,
        f"{random.choice(emojis)} {html.bold(f'{value} {source_ticker}')} = {html.bold(f'{converted_value:.6f} {target_ticker}')}",
        parse_mode=ParseMode.HTML
    )

@router.message(Command('help'))
async def help_command(message: types.Message, bot: Bot):
    emojis = ['😄', '😄', '😄', '😄', '😄', '😄', '😄', '😄']
    help_text = (
        f"{random.choice(emojis)} Commands:\n\n"
        f"{html.code('/start')} - Kick off tracking\n"
        f"{html.code('/stop')} - Shut it down\n"
        f"{html.code('/add ticker')} - Track a coin\n"
        f"{html.code('/remove ticker')} - Remove a coin\n"
        f"{html.code('/chart ticker time')} - Get a chart\n"
        f"{html.code('/convert value ticker to coin')} - Swap coins\n"
        f"{html.code('/help')} - This list\n\n"
        f"📉 - Price dipped\n"
        f"📈 - Price popped\n\n"
        f"⚠️ Only Binance coins work!\n"
    )
    await send_message_with_fallback(
        bot, message.chat.id,
        help_text,
        parse_mode=ParseMode.HTML
    )

@router.message(lambda message: message.new_chat_members)
async def handle_new_chat_members(message: types.Message, bot: Bot):
    bot_info = await bot.get_me()
    if any(member.id == bot_info.id for member in message.new_chat_members):
        await send_message_with_fallback(
            bot, message.chat.id,
            f"🔥 Yo, I'm here! Hit /help to check my vibe.",
            parse_mode=None
        )
    try:
        await message.delete()
    except Exception:
        pass

@router.message(lambda message: message.text and not message.text.startswith('/') and message.chat.type == 'private')
async def unknown_message(message: types.Message, bot: Bot):
    emojis = ['😕', '🤔', '🔥']
    await send_message_with_fallback(
        bot, message.chat.id,
        f"{random.choice(emojis)} Yo, I only get commands. Check /help.",
        parse_mode=ParseMode.HTML
    )

@router.message(lambda message: message.text and message.text.startswith('/') and message.chat.type == 'private')
async def unknown_command(message: types.Message, bot: Bot):
    emojis = ['😕', '🤔', '🔥']
    await send_message_with_fallback(
        bot, message.chat.id,
        f"{random.choice(emojis)} Bad command. Use /help for the list.",
        parse_mode=ParseMode.HTML
    )

@router.message(lambda message: any([
    message.pinned_message,
    message.left_chat_member,
    message.new_chat_title,
    message.new_chat_photo,
    message.delete_chat_photo,
    message.group_chat_created,
    message.supergroup_chat_created,
    message.channel_chat_created,
    message.migrate_to_chat_id,
    message.migrate_from_chat_id,
    message.video_chat_scheduled,
    message.video_chat_started,
    message.video_chat_ended,
    message.video_chat_participants_invited
]))
async def handle_service_message(message: types.Message):
    try:
        await message.delete()
    except Exception:
        pass

async def start_bot(bot: Bot):
    asyncio.create_task(websocket_manager())

async def send_message_with_fallback(bot: Bot, chat_id: int, text: str, parse_mode: ParseMode = None, reply_markup=None) -> types.Message:
    try:
        sent_message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
        return sent_message
    except Exception as e:
        if "can't parse" in str(e).lower():
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=None,
                reply_markup=reply_markup
            )
            return sent_message
        raise

async def edit_message_with_fallback(bot: Bot, chat_id: int, message_id: int, text: str, parse_mode: ParseMode = None, reply_markup=None):
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except Exception as e:
        if "can't parse" in str(e).lower():
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=None,
                reply_markup=reply_markup
            )
        elif "message is not modified" in str(e).lower():
            pass
        else:
            raise