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

# ================== START BOT ==================
print("🎰 Betting bot starting...")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("numbers", numbers))
app.add_handler(CommandHandler("pick", pick))

app.run_polling()
