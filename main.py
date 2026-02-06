import os
import json
import threading
from datetime import datetime
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================== CONFIG ==================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6826565670
DATA_FILE = "data.json"

TOTAL_NUMBERS = 1000
CHUNK_SIZE = 100

PRICE_TEXT = (
    "💰 *Payment Instructions*\n\n"
    "🏦 Bank: *CBE*\n"
    "👤 Name: *YOUR NAME*\n"
    "💳 Account: *1000XXXXXX*\n\n"
    "📸 After payment, send the receipt photo here."
)

# ================== DATA HELPERS ==================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"numbers": {}, "pending_receipts": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def init_numbers(data):
    for i in range(1, TOTAL_NUMBERS + 1):
        data["numbers"].setdefault(
            str(i),
            {"status": "available", "user_id": None, "name": None}
        )

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎰 *WELCOME TO THE PREMIUM BETTING GAME*\n\n"
        "🔢 Numbers: *1 – 1000*\n"
        "🟢 Available | 🟡 Reserved | 🔴 Taken\n\n"
        "📌 Use /numbers to choose your number",
        parse_mode="Markdown"
    )

# ================== SHOW NUMBERS ==================
async def numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    init_numbers(data)
    save_data(data)

    all_numbers = list(range(1, TOTAL_NUMBERS + 1))
    chunks = [
        all_numbers[i:i + CHUNK_SIZE]
        for i in range(0, TOTAL_NUMBERS, CHUNK_SIZE)
    ]

    for idx, chunk in enumerate(chunks, start=1):
        keyboard, row = [], []

        for num in chunk:
            info = data["numbers"][str(num)]

            if info["status"] == "approved":
                text = f"🔴 {num}"
                cb = "taken"
            elif info["status"] == "reserved":
                text = f"🟡 {num}"
                cb = "taken"
            else:
                text = f"🟢 {num}"
                cb = f"pick_{num}"

            row.append(InlineKeyboardButton(text, callback_data=cb))

            if len(row) == 5:
                keyboard.append(row)
                row = []

        if row:
            keyboard.append(row)

        start_n = (idx - 1) * CHUNK_SIZE + 1
        end_n = min(idx * CHUNK_SIZE, TOTAL_NUMBERS)

        await update.message.reply_text(
            f"📄 *Numbers {start_n} – {end_n}*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

# ================== HANDLE NUMBER TAP ==================
async def pick_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("pick_"):
        return

    number = query.data.split("_")[1]
    user = query.from_user

    data = load_data()
    info = data["numbers"].get(number)

    if info["status"] != "available":
        await query.message.reply_text("⛔ This number is not available.")
        return

    # Reserve number
    data["numbers"][number] = {
        "status": "reserved",
        "user_id": user.id,
        "name": user.full_name,
        "reserved_at": datetime.utcnow().isoformat(),
    }

    save_data(data)

    await query.message.reply_text(
        f"✅ *Number Reserved*\n\n"
        f"🎯 Number: *{number}*\n"
        f"👤 Name: *{user.full_name}*\n\n"
        f"{PRICE_TEXT}",
        parse_mode="Markdown"
    )

# ================== RECEIPT ==================
async def receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return

    user = update.message.from_user
    data = load_data()

    number = next(
        (
            n for n, v in data["numbers"].items()
            if v["user_id"] == user.id and v["status"] == "reserved"
        ),
        None
    )

    if not number:
        await update.message.reply_text("⚠️ You have no reserved number.")
        return

    photo = update.message.photo[-1]

    data["pending_receipts"][number] = {
        "user_id": user.id,
        "name": user.full_name,
        "file_id": photo.file_id,
        "submitted_at": datetime.utcnow().isoformat(),
    }

    save_data(data)

    await update.message.reply_text("📸 Receipt received. Waiting for admin approval.")

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=(
            f"🧾 *Payment Pending*\n\n"
            f"👤 {user.full_name}\n"
            f"🎯 Number: {number}\n\n"
            f"/approve {number}\n"
            f"/reject {number}"
        ),
        parse_mode="Markdown",
    )

# ================== ADMIN ==================
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return

    number = context.args[0]
    data = load_data()

    if number not in data["pending_receipts"]:
        await update.message.reply_text("❌ No pending receipt.")
        return

    receipt = data["pending_receipts"].pop(number)
    data["numbers"][number]["status"] = "approved"
    save_data(data)

    await update.message.reply_text(f"✅ Number {number} approved.")

    await context.bot.send_message(
        chat_id=receipt["user_id"],
        text=f"🎉 *Payment approved!*\nYour number *{number}* is confirmed.",
        parse_mode="Markdown",
    )

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return

    number = context.args[0]
    data = load_data()

    receipt = data["pending_receipts"].pop(number, None)
    data["numbers"][number] = {
        "status": "available",
        "user_id": None,
        "name": None,
    }

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
        use_reloader=False,
    )

threading.Thread(target=run_flask, daemon=True).start()

# ================== START BOT ==================
if __name__ == "__main__":
    print("🎰 Betting bot starting...")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("numbers", numbers))
    app.add_handler(CallbackQueryHandler(pick_number))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(MessageHandler(filters.PHOTO, receipt))

    app.run_polling(drop_pending_updates=True)
