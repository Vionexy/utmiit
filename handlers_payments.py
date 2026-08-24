from __future__ import annotations

import logging

from telebot.types import LabeledPrice

from app_context import app, bot
from config import STARS_MAX, STARS_MIN

logger = logging.getLogger(__name__)


@bot.message_handler(func=lambda m: app.state.get(m.chat.id).get("type") == "stars")
async def stars_amount(msg):
    try:
        amount = int(msg.text)
    except ValueError:
        await bot.send_message(msg.chat.id, f"Введите число от {STARS_MIN} до {STARS_MAX}.")
        return
    if amount < STARS_MIN or amount > STARS_MAX:
        await bot.send_message(msg.chat.id, f"Введите число от {STARS_MIN} до {STARS_MAX}.")
        return
    app.state.pop(msg.chat.id)
    await bot.send_invoice(
        msg.chat.id,
        title="Поддержать автора",
        description="Буду благодарен за поддержку",
        invoice_payload="donate_stars",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("Звёзды", amount)],
        start_parameter="donate",
    )


@bot.pre_checkout_query_handler(func=lambda q: True)
async def checkout(query):
    if query.invoice_payload != "donate_stars":
        await bot.answer_pre_checkout_query(query.id, ok=False, error_message="Неизвестный платёж")
        return
    await bot.answer_pre_checkout_query(query.id, ok=True)


@bot.message_handler(content_types=["successful_payment"])
async def got_payment(msg):
    payment = msg.successful_payment
    await bot.send_message(
        msg.chat.id, f"Спасибо за поддержку ({payment.total_amount}⭐)!", parse_mode="HTML"
    )
    logger.info("донат от %s: %s звёзд", msg.from_user.username, payment.total_amount)
