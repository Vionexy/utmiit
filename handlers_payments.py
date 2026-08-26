from __future__ import annotations

import logging

from telebot.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from app_context import app, bot
from config import STARS_MAX, STARS_MIN
from keyboards import ASK_STARS

logger = logging.getLogger(__name__)

PAYLOAD = "donate_stars"
AMOUNT_HINT = f"Введите целое число от {STARS_MIN} до {STARS_MAX}, либо /cancel."


@bot.callback_query_handler(func=lambda call: call.data == ASK_STARS)
async def ask_stars(call: CallbackQuery):
    app.state.set(call.message.chat.id, {"type": "stars"})
    await bot.answer_callback_query(call.id)
    await bot.send_message(call.message.chat.id, f"Сколько ⭐️ отправить?\n\n{AMOUNT_HINT}")


@bot.message_handler(
    content_types=["text"],
    func=lambda msg: app.state.get(msg.chat.id).get("type") == "stars",
)
async def stars_amount(msg: Message):
    raw = (msg.text or "").strip()
    if not raw.isdigit():
        await bot.send_message(msg.chat.id, AMOUNT_HINT)
        return

    amount = int(raw)
    if not STARS_MIN <= amount <= STARS_MAX:
        await bot.send_message(msg.chat.id, AMOUNT_HINT)
        return

    app.state.pop(msg.chat.id)
    await bot.send_invoice(
        msg.chat.id,
        title="Поддержать автора",
        description="Спасибо, что помогаете боту жить",
        invoice_payload=PAYLOAD,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("Звёзды", amount)],
        start_parameter="donate",
    )


@bot.pre_checkout_query_handler(func=lambda query: True)
async def checkout(query: PreCheckoutQuery):
    if query.invoice_payload != PAYLOAD:
        await bot.answer_pre_checkout_query(query.id, ok=False, error_message="Неизвестный платёж")
        return
    await bot.answer_pre_checkout_query(query.id, ok=True)


@bot.message_handler(content_types=["successful_payment"])
async def got_payment(msg: Message):
    payment = msg.successful_payment
    await bot.send_message(msg.chat.id, f"Спасибо за поддержку ({payment.total_amount} ⭐)!")
    logger.info(
        "донат: user_id=%s, %s звёзд, charge_id=%s",
        msg.from_user.id,
        payment.total_amount,
        payment.telegram_payment_charge_id,
    )

