import os
import json
import threading
import asyncio
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
RESERVATION_LIMIT_MINUTES = 60  # Auto-release after 1 hour

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
            {"status": "available", "user_id": None, "name": None, "reserved_at": None}
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

# ================== REFRESH KEYBOARD ==================
async def refresh_chunk_keyboard(bot, start_chunk, end_chunk):
    data = load_data()
    keyboard, row = [], []
    for n in range(start_chunk, end_chunk + 1):
        n_info = data["numbers"][str(n)]
        if n_info["status"] == "approved":
            text = f"🔴 {n}"
            cb = "taken"
        elif n_info["status"] == "reserved":
            text = f"🟡 {n}"
            cb = "taken"
        else:
            text = f"🟢 {n}"
            cb = f"pick_{n}"
        row.append(InlineKeyboardButton(text, callback_data=cb))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

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

    # Reserve the number
    data["numbers"][number] = {
        "status": "reserved",
        "user_id": user.id,
        "name": user.full_name,
        "reserved_at": datetime.utcnow().isoformat(),
    }
    save_data(data)

    # Auto-refresh buttons for this chunk
    num_int = int(number)
    start_chunk = ((num_int - 1) // CHUNK_SIZE) * CHUNK_SIZE + 1
    end_chunk = min(start_chunk + CHUNK_SIZE - 1, TOTAL_NUMBERS)
    keyboard_markup = await refresh_chunk_keyboard(context.bot, start_chunk, end_chunk)

    await query.message.edit_text(
        f"📄 *Numbers {start_chunk} – {end_chunk}*",
        reply_markup=keyboard_markup,
        parse_mode="Markdown"
    )

    # Inform user of reservation and payment
    await query.message.reply_text(
        f"✅ *Number Reserved*\n\n"
        f"🎯 Number: *{number}*\n"
        f"👤 Reserved by: *{user.full_name}*\n\n"
        f"{PRICE_TEXT}",
        parse_mode="Markdown"
    )

# ================== RECEIPT ==================
async def receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return

    user = update.message.from_user
    data = load_data()

    # Find all reserved numbers for this user
    reserved_numbers = [
        n for n, v in data["numbers"].items()
        if v["user_id"] == user.id and v["status"] == "reserved"
    ]

    if not reserved_numbers:
        await update.message.reply_text("⚠️ You have no reserved numbers.")
        return

    photo = update.message.photo[-1]

    for number in reserved_numbers:
        data["pending_receipts"][number] = {
            "user_id": user.id,
            "name": user.full_name,
            "file_id": photo.file_id,
            "submitted_at": datetime.utcnow().isoformat(),
        }

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

    save_data(data)
    await update.message.reply_text("📸 Receipt received. Waiting for admin approval.")

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

    # Notify admin
    await update.message.reply_text(f"✅ Number {number} approved.")

    # Notify user
    await context.bot.send_message(
        chat_id=receipt["user_id"],
        text=f"🎉 *Payment approved!*\nYour number *{number}* is confirmed.",
        parse_mode="Markdown",
    )

# Refresh keyboard chunk after approval
    num_int = int(number)
    start_chunk = ((num_int - 1) // CHUNK_SIZE) * CHUNK_SIZE + 1
    end_chunk = min(start_chunk + CHUNK_SIZE - 1, TOTAL_NUMBERS)
    # Here we assume the user sees the keyboard via /numbers, can optionally edit messages if tracked

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
        "reserved_at": None
    }
    save_data(data)

    # Notify user
    if receipt:
        await context.bot.send_message(
            chat_id=receipt["user_id"],
            text=f"❌ Payment rejected or number released. Number *{number}* is now available.",
            parse_mode="Markdown",
        )

# ================== AUTO-RELEASE TASK ==================
async def auto_release_reserved_numbers():
    while True:
        data = load_data()
        changed = False
        now = datetime.utcnow()
        for number, info in data["numbers"].items():
            if info["status"] == "reserved" and info.get("reserved_at"):
                reserved_at = datetime.fromisoformat(info["reserved_at"])
                if now - reserved_at > timedelta(minutes=RESERVATION_LIMIT_MINUTES):
                    # Notify user if exists
                    if info["user_id"]:
                        try:
                            asyncio.create_task(
                                app.bot.send_message(
                                    chat_id=info["user_id"],
                                    text=f"⏳ Your reserved number *{number}* was auto-released due to non-payment.",
                                    parse_mode="Markdown",
                                )
                            )
                        except Exception:
                            pass
                    # Release the number
                    data["numbers"][number] = {
                        "status": "available",
                        "user_id": None,
                        "name": None,
                        "reserved_at": None
                    }
                    changed = True
        if changed:
            save_data(data)
        await asyncio.sleep(60)  # check every minute

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

    # Start auto-release background task
    asyncio.create_task(auto_release_reserved_numbers())

    app.run_polling(drop_pending_updates=True)
