import os
import json
import threading
from datetime import datetime
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== CONFIG ==================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6826565670
DATA_FILE = "data.json"
TOTAL_NUMBERS = 1500
CHUNK_SIZE = 150   # 10 messages × 150 numbers

# ================== DATA HELPERS ==================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"picked_numbers": {}, "pending_receipts": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ================== BOT COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎰 *WELCOME TO THE PREMIUM BETTING GAME*\n\n"
        "🔢 Numbers: *1 – 1500*\n"
        "⚠️ One number per person\n\n"
        "Commands:\n"
        "📌 /numbers – View numbers\n"
        "🎯 /pick <number> – Pick your number",
        parse_mode="Markdown"
    )

async def numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    picked = set(map(int, data["picked_numbers"].keys()))

    all_numbers = list(range(1, TOTAL_NUMBERS + 1))
    chunks = [all_numbers[i:i + CHUNK_SIZE] for i in range(0, TOTAL_NUMBERS, CHUNK_SIZE)]

    for index, chunk in enumerate(chunks, start=1):
        keyboard = []
        row = []

        for num in chunk:
            if num in picked:
                text = f"🔴 {num}"
                callback = "taken"
            else:
                text = f"🟢 {num}"
                callback = f"pick_{num}"

            row.append(InlineKeyboardButton(text, callback_data=callback))

            if len(row) == 5:
                keyboard.append(row)
                row = []

        if row:
            keyboard.append(row)

        start_n = (index - 1) * CHUNK_SIZE + 1
        end_n = min(index * CHUNK_SIZE, TOTAL_NUMBERS)

        await update.message.reply_text(
            f"📄 *Numbers {start_n} – {end_n}*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /pick <number>")
        return

    try:
        number = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid number.")
        return

    if number < 1 or number > TOTAL_NUMBERS:
        await update.message.reply_text("❌ Number must be between 1–1500.")
        return

    data = load_data()

    if str(number) in data["picked_numbers"]:
        await update.message.reply_text("⛔ Number already taken.")
        return

    user = update.message.from_user

    data["picked_numbers"][str(number)] = {
        "user_id": user.id,
        "name": user.full_name,
        "picked_at": datetime.utcnow().isoformat()
    }

    save_data(data)

    await update.message.reply_text(
        f"✅ *Number Reserved*\n\n"
        f"🎯 Number: *{number}*\n"
        f"👤 Name: *{user.full_name}*\n\n"
        f"📸 Please send payment receipt.",
        parse_mode="Markdown"
    )

# ================== RECEIPT ==================
async def receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return

    user = update.message.from_user
    data = load_data()

    picked_number = next(
        (n for n, v in data["picked_numbers"].items() if v["user_id"] == user.id),
        None
    )

    if not picked_number:
        await update.message.reply_text("⚠️ Pick a number first.")
        return

    photo = update.message.photo[-1]

    data["pending_receipts"][picked_number] = {
        "user_id": user.id,
        "name": user.full_name,
        "file_id": photo.file_id,
        "submitted_at": datetime.utcnow().isoformat()
    }

    save_data(data)

    await update.message.reply_text("📸 Receipt received. Waiting for admin approval.")

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=(
            f"🧾 *Payment Pending*\n\n"
            f"👤 {user.full_name}\n"
            f"🎯 Number: {picked_number}\n\n"
            f"/approve {picked_number}\n"
            f"/reject {picked_number}"
        ),
        parse_mode="Markdown"
    )

# ================== ADMIN ==================
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    if not context.args:
        return

    number = context.args[0]
    data = load_data()

    if number not in data["pending_receipts"]:
        await update.message.reply_text("❌ No pending receipt.")
        return

    receipt = data["pending_receipts"].pop(number)
    save_data(data)

    await update.message.reply_text(f"✅ Number {number} approved.")

    await context.bot.send_message(
        chat_id=receipt["user_id"],
        text=f"🎉 *Payment approved!*\nYour number *{number}* is confirmed.",
        parse_mode="Markdown"
    )

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    if not context.args:
        return

    number = context.args[0]
    data = load_data()

    receipt = data["pending_receipts"].pop(number, None)
    data["picked_numbers"].pop(number, None)
    save_data(data)

    if receipt:
        await context.bot.send_message(
            chat_id=receipt["user_id"],
            text="❌ Payment rejected. Your number has been released."
        )

# ================== FLASK ==================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Betting bot running"

def run_flask():
    flask_app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        use_reloader=False
    )

threading.Thread(target=run_flask, daemon=True).start()

# ================== START ==================
if __name__ == "__main__":
    print("🎰 Betting bot starting...")
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("numbers", numbers))
    application.add_handler(CommandHandler("pick", pick))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("reject", reject))
    application.add_handler(MessageHandler(filters.PHOTO, receipt))

    application.run_polling(drop_pending_updates=True)
