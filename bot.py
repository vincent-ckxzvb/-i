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
    ContextTypes,
    filters
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("8276060557:AAEloclb1WSAuH1q9z037YuB-j4N66HHuzI")
BOT_USERNAME = "think2EarnBot"
ADMIN_ID = 775857744  # REPLACE WITH YOUR REAL ID

REFERRAL_REWARD = 100
MIN_WITHDRAW = 1000
DAILY_LIMIT = 10

REWARDS = {"easy": 20, "medium": 40, "hard": 70}
TIME_LIMIT = {"easy": 20, "medium": 15, "hard": 10}

# ================== DATABASE ==================
db = sqlite3.connect("think2earn.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
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

# ================== QUESTIONS ==================
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
    if level == "medium":
        a, b = random.randint(10, 50), random.randint(5, 30)
        return f"{a} - {b} = ?", str(a - b)
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
    last = cur.fetchone()[0]
    if last != today():
        cur.execute(
            "UPDATE users SET daily_count=0, last_day=? WHERE user_id=?",
            (today(), uid)
        )
        db.commit()

def referral_count(uid):
    cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer=?", (uid,))
    return cur.fetchone()[0]

# ================== UI ==================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧮 Math", callback_data="math"),
         InlineKeyboardButton("🧠 Logic", callback_data="logic")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("👥 Referrals", callback_data="referrals")],
        [InlineKeyboardButton("📜 Rules", callback_data="rules")]
    ])

def difficulty_menu(mode):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Easy", callback_data=f"{mode}_easy")],
        [InlineKeyboardButton("🟡 Medium", callback_data=f"{mode}_medium")],
        [InlineKeyboardButton("🔴 Hard", callback_data=f"{mode}_hard")],
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    reset_daily(uid)

    # REFERRAL (SAFE)
    if context.args:
        try:
            ref = int(context.args[0])
            if ref != uid:
                cur.execute("SELECT 1 FROM referrals WHERE referred=?", (uid,))
                if not cur.fetchone():
                    cur.execute("INSERT INTO referrals VALUES (?,?)", (ref, uid))
                    cur.execute(
                        "UPDATE users SET balance = balance + ? WHERE user_id=?",
                        (REFERRAL_REWARD, ref)
                    )
                    db.commit()
        except:
            pass

    await update.message.reply_text(
        "🧠 *Think2Earn Bot*\n\n"
        "Answer questions • Earn points • Invite friends\n\n"
        f"🎯 Daily limit: {DAILY_LIMIT}",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

# ================== BUTTON HANDLER ==================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    reset_daily(uid)

    if q.data in ["math", "logic"]:
        cur.execute("SELECT daily_count FROM users WHERE user_id=?", (uid,))
        if cur.fetchone()[0] >= DAILY_LIMIT:
            await q.message.reply_text("❌ Daily limit reached.")
            return
        await q.message.reply_text(
            "🎯 Select difficulty",
            reply_markup=difficulty_menu(q.data)
        )

    elif "_" in q.data:
        mode, level = q.data.split("_")

        question, answer = (
            math_question(level)
            if mode == "math"
            else random.choice(LOGIC_QUESTIONS)
        )

        pending[uid] = {
            "answer": answer.lower(),
            "time": time.time(),
            "level": level
        }

        await q.message.reply_text(
            f"⏱ {TIME_LIMIT[level]} seconds\n\n❓ {question}"
        )

    elif q.data == "balance":
        cur.execute("SELECT balance, daily_count FROM users WHERE user_id=?", (uid,))
        bal, dc = cur.fetchone()
        await q.message.reply_text(
            f"💰 Balance: ₱{bal}\n"
            f"📊 Today: {dc}/{DAILY_LIMIT}"
        )

    elif q.data == "referrals":
        await q.message.reply_text(
            f"👥 Referrals: {referral_count(uid)}\n\n"
            f"🔗 https://t.me/{Think2EarnBot}?start={uid}"
        )

    elif q.data == "rules":
        await q.message.reply_text(
            "📜 Rules:\n"
            "• One account per user\n"
            "• No cheating\n"
            "• Daily limits apply\n"
            "• Admin decision is final"
        )

    elif q.data == "back":
        await q.message.reply_text("🏠 Main Menu", reply_markup=main_menu())

# ================== ANSWERS ==================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text.lower()

    if uid not in pending:
        return

    data = pending.pop(uid)

    if time.time() - data["time"] > TIME_LIMIT[data["level"]]:
        await update.message.reply_text("⏰ Time’s up!")
        return

    if txt == data["answer"]:
        reward = REWARDS[data["level"]]
        cur.execute("""
        UPDATE users SET
        balance = balance + ?,
        daily_count = daily_count + 1
        WHERE user_id=?
        """, (reward, uid))
        db.commit()
        await update.message.reply_text(f"✅ Correct! +₱{reward}")
    else:
        await update.message.reply_text("❌ Wrong answer")

# ================== RUN ==================
if not BOT_TOKEN:
    raise RuntimeError("8276060557:AAEloclb1WSAuH1q9z037YuB-j4N66HHuzI")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("Think2EarnBot running...")
app.run_polling()
