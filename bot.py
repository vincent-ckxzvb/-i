import os
import sqlite3
import time
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes, # Updated for v20+
)

# ================== CONFIG (RETAINED) ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "think2EarnBot"

ADMIN_ID = 775857744
REFERRAL_REWARD = 100
MIN_WITHDRAW = 1000
DAILY_LIMIT = 10
WITHDRAW_FEE = 15

REWARDS = {"easy": 20, "medium": 40, "hard": 70}
TIME_LIMIT = {"easy": 20, "medium": 15, "hard": 10}

GCASH_NUMBER = "09939775174"
PAYMAYA_NUMBER = "09939775174"

# ================== DATABASE (RETAINED) ==================
db = sqlite3.connect("think2earn.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    all_time_balance INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    daily_count INTEGER DEFAULT 0,
    last_day INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS referrals (
    referrer INTEGER,
    referred INTEGER UNIQUE
)
""")
db.commit()

pending = {} 

# ================== QUESTIONS (RETAINED) ==================
LOGIC_QUESTIONS = [
    ("What has keys but no locks?", "keyboard"),
    ("What gets wetter as it dries?", "towel"),
    ("What has hands but can't clap?", "clock"),
    ("What runs but never walks?", "water"),
    ("What has an eye but cannot see?", "needle"),
    ("What has a face and two hands but no arms?", "clock"),
    ("What comes once in a minute, twice in a moment?", "m"),
    ("What has legs but doesn’t walk?", "table"),
    ("What has many teeth but can’t bite?", "comb"),
    ("What goes up but never comes down?", "age"),
    ("What can travel around the world staying in one place?", "stamp"),
    ("What has a neck but no head?", "bottle"),
    ("What can you catch but not throw?", "cold"),
    ("What has words but never speaks?", "book"),
    ("What breaks when you say it?", "silence"),
    ("What has a head and tail but no body?", "coin"),
    ("What is always in front of you but can’t be seen?", "future"),
    ("What has one eye but can’t see?", "needle"),
    ("What has a ring but no finger?", "phone"),
    ("What has a heart but no organs?", "artichoke"),
]

def math_question(level):
    if level == "easy":
        a, b = random.randint(1, 10), random.randint(1, 10)
        return f"{a} + {b} = ?", str(a + b)
    elif level == "medium":
        a, b = random.randint(10, 50), random.randint(5, 30)
        return f"{a} - {b} = ?", str(a - b)
    else: 
        a, b = random.randint(5, 20), random.randint(5, 15)
        return f"{a} × {b} = ?", str(a * b)

# ================== HELPERS ==================
def today():
    return int(time.time() // 86400)

def ensure_user(uid):
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    db.commit()

def reset_daily(uid):
    cur.execute("SELECT last_day FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if row and row[0] != today():
        cur.execute("UPDATE users SET daily_count=0, last_day=? WHERE user_id=?", (today(), uid))
        db.commit()

# ================== UI ==================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧮 Math", callback_data="math"),
         InlineKeyboardButton("🧠 Logic", callback_data="logic")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("👥 Referrals", callback_data="referrals")],
        [InlineKeyboardButton("📜 Rules", callback_data="rules"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]
    ])

def difficulty_menu(mode):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Easy", callback_data=f"{mode}_easy")],
        [InlineKeyboardButton("🟡 Medium", callback_data=f"{mode}_medium")],
        [InlineKeyboardButton("🔴 Hard", callback_data=f"{mode}_hard")],
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])

def withdrawal_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("GCash", callback_data="withdraw_gcash")],
        [InlineKeyboardButton("PayMaya", callback_data="withdraw_paymaya")],
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    reset_daily(uid)

    if context.args:
        try:
            ref = int(context.args[0])
            if ref != uid:
                cur.execute("SELECT 1 FROM referrals WHERE referred=?", (uid,))
                if not cur.fetchone():
                    cur.execute("INSERT INTO referrals VALUES (?,?)", (ref, uid))
                    cur.execute(
                        "UPDATE users SET balance=balance+?, all_time_balance=all_time_balance+? WHERE user_id=?",
                        (REFERRAL_REWARD, REFERRAL_REWARD, ref)
                    )
                    db.commit()
        except:
            pass

    await update.message.reply_text(
        "🧠 Think2Earn Bot\nAnswer questions • Earn points",
        reply_markup=main_menu()
    )

# ================== BUTTON HANDLER ==================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    reset_daily(uid)

    if query.data in ["math", "logic"]:
        cur.execute("SELECT daily_count FROM users WHERE user_id=?", (uid,))
        daily_count = cur.fetchone()[0]
        if daily_count >= DAILY_LIMIT:
            await query.message.reply_text("❌ Daily limit reached.")
            return
        await query.message.reply_text("🎯 Select difficulty", reply_markup=difficulty_menu(query.data))

    elif "_" in query.data and not query.data.startswith("withdraw_"):
        mode, level = query.data.split("_")
        question, answer = math_question(level) if mode == "math" else random.choice(LOGIC_QUESTIONS)
        pending[uid] = {"answer": answer.lower(), "time": time.time(), "level": level}
        await query.message.reply_text(f"⏱ {TIME_LIMIT[level]} seconds\n\n❓ {question}")

    elif query.data == "balance":
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        balance = cur.fetchone()[0]
        await query.message.reply_text(f"💰 Balance: ₱{balance}")

    elif query.data == "withdraw":
        await query.message.reply_text("💸 Choose withdrawal method:", reply_markup=withdrawal_menu())

    elif query.data.startswith("withdraw_"):
        method = query.data.split("_")[1]
        pending[uid] = {"withdraw_method": method, "step": "amount"}
        await query.message.reply_text(f"Enter amount to withdraw via {method.upper()}:")

    elif query.data == "confirm_withdraw":
        data = pending.pop(uid, None)
        if not data:
            await query.message.reply_text("❌ No pending withdrawal.")
            return
        amount = data["amount"]
        total = amount + WITHDRAW_FEE
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        current_balance = cur.fetchone()[0]
        if current_balance < total:
            await query.message.reply_text("❌ Insufficient balance.")
            return
        
        cur.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=?",
            (total, uid)
        )
        db.commit()
        number = GCASH_NUMBER if data["withdraw_method"] == "gcash" else PAYMAYA_NUMBER
        await query.message.reply_text(f"✅ Send ₱{amount} + ₱{WITHDRAW_FEE} to {number}")

    elif query.data == "back":
        await query.message.reply_text("🏠 Main Menu", reply_markup=main_menu())

# ================== MESSAGE HANDLER ==================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text.lower()

    if uid in pending and "answer" in pending[uid]:
        data = pending.pop(uid)
        if time.time() - data["time"] > TIME_LIMIT[data["level"]]:
            await update.message.reply_text("⏰ Time’s up!")
            return
        if txt == data["answer"]:
            reward = REWARDS[data["level"]]
            cur.execute(
                "UPDATE users SET balance=balance+?, all_time_balance=all_time_balance+?, daily_count=daily_count+1 WHERE user_id=?",
                (reward, reward, uid)
            )
            db.commit()
            await update.message.reply_text(f"✅ Correct! +₱{reward}")
        else:
            await update.message.reply_text("❌ Wrong answer")
        return

    if uid in pending and pending[uid].get("step") == "amount":
        try:
            amt = int(txt)
        except:
            await update.message.reply_text("❌ Invalid amount.")
            return
        pending[uid]["amount"] = amt
        await update.message.reply_text(
            f"Confirm ₱{amt} + ₱{WITHDRAW_FEE} fee?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirm", callback_data="confirm_withdraw")],
                [InlineKeyboardButton("⬅ Back", callback_data="back")]
            ])
        )

# ================== MAIN (FIXED) ==================
if __name__ == "__main__":
    import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# 1. This part creates a fake web server to satisfy Render
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_dummy_server():
    # Render provides a PORT environment variable automatically
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"Dummy server listening on port {port}")
    server.serve_forever()

# 2. Your existing main block
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    
    # Start the dummy server in the background
    threading.Thread(target=run_dummy_server, daemon=True).start()

    # Start the Telegram Bot
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(buttons))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Think2EarnBot running...")
    application.run_polling()
