import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

from database import get_available_numbers, pick_number, get_all_bets

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 123456789  # replace with YOUR Telegram ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎲 *Welcome to the Premium Number Game*\n\n"
        "Commands:\n"
        "/numbers – View available numbers\n"
        "/pick <number> – Pick a number\n",
        parse_mode="Markdown"
    )


async def numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    available = get_available_numbers()

    if not available:
        await update.message.reply_text("❌ All numbers are taken.")
        return

    text = "🟢 *Available Numbers:*\n\n"
    text += ", ".join(map(str, available))
    await update.message.reply_text(text, parse_mode="Markdown")


async def pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /pick <number>")
        return

    try:
        number = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid number.")
        return

    user = update.message.from_user
    success = pick_number(number, user.id, user.username or user.first_name)

    if success:
        await update.message.reply_text(
            f"✅ *Number {number} reserved successfully!*",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ Number {number} is already taken."
        )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    bets = get_all_bets()
    if not bets:
        await update.message.reply_text("No bets yet.")
        return

    text = "📋 *All Picks:*\n\n"
    for number, username in bets:
        text += f"{number} → {username}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


print("Bot is starting...")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("numbers", numbers))
app.add_handler(CommandHandler("pick", pick))
app.add_handler(CommandHandler("admin", admin))

app.run_polling()
