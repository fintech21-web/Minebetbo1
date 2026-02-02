import os
import json
import threading
from datetime import datetime
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)
ADMIN_ID = 6826565670  # ← replace with YOUR Telegram user ID
# ================== CONFIG ==================
TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "data.json"
TOTAL_NUMBERS = 1500

# ================== DATA HELPERS ==================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"picked_numbers": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ================== BOT COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎰 *WELCOME TO THE PREMIUM BETTING GAME*\n\n"
        "🔢 Numbers available: *1 – 1500*\n"
        "⚠️ One number per person\n\n"
        "Commands:\n"
        "📌 /numbers – View available numbers\n"
        "🎯 /pick <number> – Pick your number\n\n"
        "✨ Play smart. First come, first served.",
        parse_mode="Markdown"
    )

async def numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    picked = set(map(int, data["picked_numbers"].keys()))

    available = [str(i) for i in range(1, TOTAL_NUMBERS + 1) if i not in picked]

    if not available:
        await update.message.reply_text("❌ All numbers are taken.")
        return

    preview = ", ".join(available[:50])
    more = "..." if len(available) > 50 else ""

    await update.message.reply_text(
        f"🟢 *Available Numbers*\n\n"
        f"{preview}{more}\n\n"
        f"📊 Remaining: *{len(available)}*",
        parse_mode="Markdown"
    )

async def pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /pick <number>")
        return

    try:
        number = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return

    if number < 1 or number > TOTAL_NUMBERS:
        await update.message.reply_text("❌ Number must be between 1 and 1500.")
        return

    data = load_data()
    picked_numbers = data["picked_numbers"]

    if str(number) in picked_numbers:
        await update.message.reply_text("⛔ This number is already taken.")
        return

    user = update.message.from_user

    picked_numbers[str(number)] = {
        "user_id": user.id,
        "username": user.username,
        "name": user.full_name,
        "picked_at": datetime.utcnow().isoformat()
    }

    save_data(data)

    await update.message.reply_text(
        f"✅ *Number Reserved Successfully!*\n\n"
        f"🎯 Number: *{number}*\n"
        f"👤 Name: *{user.full_name}*\n\n"
        f"💳 Please proceed with payment.\n"
        f"📸 Send receipt after payment.\n\n"
        f"✨ Your number is temporarily locked.",
        parse_mode="Markdown"
    )

# ================== FLASK (Render Port Fix) ==================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Betting bot is running"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

async def receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    data = load_data()

    if not update.message.photo:
        await update.message.reply_text("❌ Please send a photo of the payment receipt.")
        return

    # find user's picked number
    picked_number = None
    for num, info in data["picked_numbers"].items():
        if info["user_id"] == user.id:
            picked_number = num
            break

    if not picked_number:
        await update.message.reply_text("⚠️ You have not picked any number yet.")
        return

    # save receipt
    photo = update.message.photo[-1]
    data["pending_receipts"][picked_number] = {
        "user_id": user.id,
        "username": user.username,
        "name": user.full_name,
        "file_id": photo.file_id,
        "submitted_at": datetime.utcnow().isoformat()
    }

    save_data(data)

    await update.message.reply_text(
        "📸 *Receipt received!*\n\n"
        "⏳ Awaiting admin approval.\n"
        "You will be notified once approved.",
        parse_mode="Markdown"
    )

    # notify admin
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=(
            f"🧾 *New Payment Receipt*\n\n"
            f"👤 {user.full_name}\n"
            f"🎯 Number: {picked_number}\n\n"
            f"Approve: /approve {picked_number}\n"
            f"Reject: /reject {picked_number}"
        ),
        parse_mode="Markdown"
    )
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: /approve <number>")
        return

    number = context.args[0]
    data = load_data()

    if number not in data["pending_receipts"]:
        await update.message.reply_text("❌ No pending receipt for this number.")
        return

    receipt = data["pending_receipts"].pop(number)
    save_data(data)

    await update.message.reply_text(f"✅ Number {number} approved.")

    await context.bot.send_message(
        chat_id=receipt["user_id"],
        text=(
            f"🎉 *Payment Approved!*\n\n"
            f"🎯 Your number *{number}* is now FINAL.\n"
            f"Good luck 🍀"
        ),
        parse_mode="Markdown"
    )

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: /reject <number>")
        return

    number = context.args[0]
    data = load_data()

    if number not in data["pending_receipts"]:
        await update.message.reply_text("❌ No pending receipt for this number.")
        return

    receipt = data["pending_receipts"].pop(number)
    data["picked_numbers"].pop(number, None)
    save_data(data)

    await update.message.reply_text(f"❌ Number {number} rejected and released.")

    await context.bot.send_message(
        chat_id=receipt["user_id"],
        text="❌ Payment rejected. Your number has been released

# ================== START BOT ==================
print("🎰 Betting bot starting...")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("numbers", numbers))
app.add_handler(CommandHandler("pick", pick))
app.add_handler(CommandHandler("approve", approve))
app.add_handler(CommandHandler("reject", reject))
app.run_polling()
