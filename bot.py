import os
import sqlite3
import time
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ================== CONFIG ==================
BOT_TOKEN = "YOUR_BOT_TOKEN" # Replace with your token
BOT_USERNAME = "think2EarnBot"
ADMIN_ID = 775857744 
REFERRAL_REWARD = 48.88 
MIN_WITHDRAW = 1000
WITHDRAW_FEE = 15.00

ADMIN_GCASH = "09939775174"
ADMIN_PAYMAYA = "09939775174"

# Rewards & Time Limits
REWARDS = {"easy": 25, "medium": 50, "hard": 100}
TIME_LIMITS = {"easy": 20, "medium": 15, "hard": 10}

# ================== DATABASE ==================
db = sqlite3.connect("think2earn.db", check_same_thread=False)
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0)")
db.commit()

pending = {} 

# ================== QUESTIONS DATABASE ==================
LOGIC_QUESTIONS = {
    "easy": [
        ("What is full of holes but still holds water?", "sponge"),
        ("What has keys but no locks?", "keyboard"),
        ("What gets wetter as it dries?", "towel"),
        ("What belongs to you, but others use it more?", "name"),
        ("The more of this there is, the less you see. What is it?", "darkness"),
        ("What building has the most stories?", "library"),
        ("What starts with T, ends with T, and has T in it?", "teapot"),
        ("What has a neck but no head?", "bottle")
    ],
    "medium": [
        ("I’m light as a feather, yet the strongest man can’t hold me for long. What am I?", "breath"),
        ("What can travel around the world while staying in a corner?", "stamp"),
        ("What has one eye but can't see?", "needle"),
        ("What has legs but doesn't walk?", "table"),
        ("If you drop me I’m sure to crack, but give me a smile and I’ll always smile back. What am I?", "mirror"),
        ("What can you catch, but not throw?", "cold"),
        ("The person who makes it has no need of it; the person who buys it has no use for it. What is it?", "coffin")
    ],
    "hard": [
        ("If I have it, I don’t share it. If I share it, I don’t have it. What is it?", "secret"),
        ("What is always in front of you but can’t be seen?", "future"),
        ("A man is looking at a photograph. A friend asks who it is. The man replies, 'Brothers and sisters I have none, but that man's father is my father's son.' Who is in the photo?", "son"),
        ("Forward I am heavy, but backward I am not. What am I?", "ton"),
        ("What word is pronounced the same if you take away four of its five letters?", "queue"),
        ("What has many teeth but cannot bite?", "comb"),
        ("What occurs once in a minute, twice in a moment, and never in a thousand years?", "m")
    ]
}

def get_math_question(level):
    if level == "easy": a, b = random.randint(1, 15), random.randint(1, 15); return f"{a} + {b} = ?", str(a + b)
    elif level == "medium": a, b = random.randint(20, 80), random.randint(10, 50); return f"{a} - {b} = ?", str(a - b)
    else: a, b = random.randint(5, 25), random.randint(5, 15); return f"{a} × {b} = ?", str(a * b)

# ================== UI DESIGN ==================
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("🧮 Solve Math"), KeyboardButton("🧠 Logic Riddle")],
        [KeyboardButton("💳 Balance"), KeyboardButton("🎁 Referrals")],
        [KeyboardButton("🏅 Leaderboard"), KeyboardButton("📜 Rules")],
        [KeyboardButton("💸 Withdraw Funds")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def difficulty_keyboard(mode):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Beginner (₱25)", callback_data=f"{mode}_easy")],
        [InlineKeyboardButton("🟡 Intermediate (₱50)", callback_data=f"{mode}_medium")],
        [InlineKeyboardButton("🔴 Expert (₱100)", callback_data=f"{mode}_hard")]
    ])

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.first_name
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, uname))
    db.commit()
    
    msg = (
        f"<b>💎 Welcome, {uname}! 💎</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Unlock rewards by sharpening your brain!\n"
        "Choose a category below to start earning."
    )
    await update.message.reply_text(msg, reply_markup=main_menu_keyboard(), parse_mode="HTML")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    # Handle Pending Quiz Answer
    if uid in pending and "ans" in pending[uid]:
        data = pending.pop(uid)
        if text.lower().strip() == data["ans"].lower():
            reward = REWARDS[data["lvl"]]
            cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, uid))
            db.commit()
            await update.message.reply_text(f"✅ <b>CORRECT!</b>\nYou earned <b>₱{reward:.2f}</b>", parse_mode="HTML")
        else:
            await update.message.reply_text(f"❌ <b>WRONG!</b>\nThe answer was: <code>{data['ans']}</code>", parse_mode="HTML")
        return

    # Withdrawal Logic Steps
    if uid in pending and "step" in pending[uid]:
        if pending[uid]["step"] == "num":
            pending[uid].update({"wallet": text, "step": "amt"})
            await update.message.reply_text("💰 Enter the amount to withdraw:")
            return
        elif pending[uid]["step"] == "amt":
            try:
                amt = float(text)
                cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
                bal = cur.fetchone()[0]
                if amt < MIN_WITHDRAW or bal < amt:
                    await update.message.reply_text(f"⚠️ Insufficient funds or below min (₱{MIN_WITHDRAW}).")
                    return
                pending[uid].update({"amt": amt, "step": "proof"})
                method = pending[uid]["method"]
                num = ADMIN_GCASH if method == "GCash" else ADMIN_PAYMAYA
                await update.message.reply_text(f"🚀 Send <b>₱{WITHDRAW_FEE}</b> fee to {method}:\n<code>{num}</code>\n\nThen send the screenshot.", parse_mode="HTML")
            except: await update.message.reply_text("Please enter a valid amount.")
            return

    # Menu Routing
    if text == "🧮 Solve Math":
        await update.message.reply_text("<b>🔢 Choose Math Difficulty:</b>", reply_markup=difficulty_keyboard("math"), parse_mode="HTML")
    elif text == "🧠 Logic Riddle":
        await update.message.reply_text("<b>🧩 Choose Logic Difficulty:</b>", reply_markup=difficulty_keyboard("logic"), parse_mode="HTML")
    elif text == "💳 Balance":
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = cur.fetchone()[0]
        await update.message.reply_text(f"🏦 <b>ACCOUNT OVERVIEW</b>\n━━━━━━━━━━━━━━━━━━\n💰 Current: <b>₱{bal:.2f}</b>", parse_mode="HTML")
    elif text == "🏅 Leaderboard":
        cur.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 5")
        top = cur.fetchall()
        lb = "🏆 <b>WORLD TOP EARNERS</b>\n━━━━━━━━━━━━━━━━━━\n"
        icons = ["🥇", "🥈", "🥉", "👤", "👤"]
        for i, user in enumerate(top):
            lb += f"{icons[i]} {user[0]}: <b>₱{user[1]:.2f}</b>\n"
        await update.message.reply_text(lb, parse_mode="HTML")
    elif text == "📜 Rules":
        rules = "⚠️ <b>PLATFORM RULES</b>\n1. No spamming.\n2. One account per person.\n3. Verified fee is required for first-time withdrawal."
        await update.message.reply_text(rules, parse_mode="HTML")
    elif text == "💸 Withdraw Funds":
        await update.message.reply_text("<b>Withdrawal Gateway:</b>", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("GCash", callback_data="wd_gcash"), InlineKeyboardButton("PayMaya", callback_data="wd_paymaya")]
        ]), parse_mode="HTML")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data.startswith("math_"):
        lvl = query.data.split("_")[1]
        q, a = get_math_question(lvl)
        pending[uid] = {"ans": a, "lvl": lvl}
        await query.message.reply_text(f"⏳ <i>Time: {TIME_LIMITS[lvl]}s</i>\n\n🔢 <b>Question:</b> <code>{q}</code>", parse_mode="HTML")
    
    elif query.data.startswith("logic_"):
        lvl = query.data.split("_")[1]
        q, a = random.choice(LOGIC_QUESTIONS[lvl])
        pending[uid] = {"ans": a, "lvl": lvl}
        await query.message.reply_text(f"⏳ <i>Time: {TIME_LIMITS[lvl]}s</i>\n\n🧩 <b>Riddle:</b>\n<i>{q}</i>", parse_mode="HTML")

    elif query.data.startswith("wd_"):
        method = "GCash" if "gcash" in query.data else "PayMaya"
        pending[uid] = {"method": method, "step": "num"}
        await query.message.reply_text(f"📲 Enter your {method} Number:")

# ================== BOOTSTRAP ==================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot online with improved UI!")
    app.run_polling()
```[[2](https://www.google.com/url?sa=E&q=https%3A%2F%2Fvertexaisearch.cloud.google.com%2Fgrounding-api-redirect%2FAUZIYQGLa78Xgr3uvRm2tEDClNry6iGJAH7h6JijXZPRTomzqFaeDa_WSDBVSE6IWRwCSCiwC5Dsh4I6q8FqZd5-xuloeH51nIzs6VzreN8ZrrsVidPVhyoIB3EnZrUXUMRHs2VUrFQnPSJZwaYEuvP3nbilr-C3t7_yGB2xWc6zUtdp2DdKyMSe52PDK6Jy3iEG)][[5](https://www.google.com/url?sa=E&q=https%3A%2F%2Fvertexaisearch.cloud.google.com%2Fgrounding-api-redirect%2FAUZIYQH7W4qiWForLFW5-1WFVcyWk-z12Qy4nLdtjkUvnmlGllzDqZnC5x6Y3n66RYogi5LErryozUiswbijwZlBxIDnHi7xx8NPSSQDry2AlE4X4i0P7XV4e25SUsQkcTdgGh79LH1X7H8%3D)]
