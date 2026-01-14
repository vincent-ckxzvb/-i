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
BOT_TOKEN = os.getenv("8276060557:AAFgZ9lQ-AOrIwIFrnsBHYkSpYm0qCT6BpM")
BOT_USERNAME = "think2EarnBot"
ADMIN_ID = 7758577440  # <-- PUT YOUR TELEGRAM NUMERIC ID

REFERRAL_REWARD = 100
MIN_WITHDRAW = 1000
TX_FEE_NUMBER = "09939775174"

REWARDS = {"easy": 20, "medium": 40, "hard": 70}
TIME_LIMIT = {"easy": 20, "medium": 15, "hard": 10}

DAILY_LIMIT = 10
STREAK_BONUS_EVERY = 3
STREAK_BONUS_AMOUNT = 10

# ================== DATABASE ==================
db = sqlite3.connect("think2earn.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    daily_count INTEGER DEFAULT 0,
    last_day INTEGER DEFAULT 0,
    welcomed INTEGER DEFAULT 0
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
withdraw_waiting = {}

# ================== QUESTIONS ==================
LOGIC_QUESTIONS = [
    ("What has keys but no locks?", "keyboard"),
    ("What gets wetter as it dries?", "towel"),
    ("What has hands but can’t clap?", "clock"),
    ("What runs but never walks?", "water"),
    ("What has an eye but cannot see?", "needle"),
    ("What comes once in a minute, twice in a moment?", "m"),
    ("What breaks when you say it?", "silence"),
    ("What has legs but doesn’t walk?", "table"),
    ("What has many teeth but can’t bite?", "comb"),
    ("What goes up but never comes down?", "age"),
    ("What has a ring but no finger?", "phone"),
    ("What has a face and two hands but no arms?", "clock"),
    ("What can travel the world staying in one place?", "stamp"),
    ("What has a neck but no head?", "bottle"),
    ("What can you catch but not throw?", "cold"),
    ("What has words but never speaks?", "book"),
    ("What has a head and tail but no body?", "coin"),
    ("What is always in front of you but can’t be seen?", "future"),
]

def math_question(level):
    if level == "easy":
        a, b = random.randint(1, 10), random.randint(1, 10)
        return f"What is {a} + {b}?", str(a + b)
    if level == "medium":
        a, b = random.randint(10, 50), random.randint(5, 30)
        return f"What is {a} − {b}?", str(a - b)
    a, b = random.randint(5, 20), random.randint(5, 15)
    return f"What is {a} × {b}?", str(a * b)

# ================== HELPERS ==================
def ensure_user(uid):
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    db.commit()

def referral_count(uid):
    cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer=?", (uid,))
    return cur.fetchone()[0]

def reset_daily(uid):
    today = int(time.time() // 86400)
    cur.execute("SELECT last_day FROM users WHERE user_id=?", (uid,))
    last = cur.fetchone()[0]
    if last != today:
        cur.execute(
            "UPDATE users SET daily_count=0, last_day=? WHERE user_id=?",
            (today, uid)
        )
        db.commit()

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧮 Math", callback_data="math"),
         InlineKeyboardButton("🧠 Logic", callback_data="logic")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("🏦 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("🏆 Referrals", callback_data="leaderboard"),
         InlineKeyboardButton("📜 Rules", callback_data="rules")]
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

    # referral
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
                    await context.bot.send_message(
                        ref,
                        f"🎉 New referral joined!\n💰 +₱{REFERRAL_REWARD}\n👥 Total: {referral_count(ref)}"
                    )
        except:
            pass

    cur.execute("SELECT welcomed FROM users WHERE user_id=?", (uid,))
    if cur.fetchone()[0] == 0:
        await update.message.reply_text(
            "🧠 **Welcome to Think2EarnBot!**\n\n"
            "Think smart • Earn rewards\n\n"
            "🎯 Daily limit: 10 questions\n"
            "💰 Earn up to ₱70 per answer\n"
            "🔥 Streak bonuses available\n\n"
            "👇 Choose an option below",
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
        cur.execute("UPDATE users SET welcomed=1 WHERE user_id=?", (uid,))
        db.commit()
    else:
        await update.message.reply_text("🏠 Main Menu", reply_markup=main_menu())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ **Think2EarnBot Help**\n\n"
        "• Answer questions\n"
        "• Earn rewards\n"
        "• Invite friends\n"
        "• Daily limits apply\n\n"
        "🎯 Play fair. Have fun.",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

# ================== BUTTONS ==================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    reset_daily(uid)

    if q.data in ["math", "logic"]:
        cur.execute("SELECT daily_count FROM users WHERE user_id=?", (uid,))
        if cur.fetchone()[0] >= DAILY_LIMIT:
            await q.message.reply_text("❌ Daily limit reached. Come back tomorrow.")
            return
        await q.message.reply_text(
            "🎯 **Select Difficulty**",
            reply_markup=difficulty_menu(q.data),
            parse_mode="Markdown"
        )

    elif "_" in q.data:
        mode, level = q.data.split("_")
        cur.execute("SELECT daily_count FROM users WHERE user_id=?", (uid,))
        if cur.fetchone()[0] >= DAILY_LIMIT:
            await q.message.reply_text("❌ Daily limit reached.")
            return

        question, answer = (
            math_question(level) if mode == "math"
            else random.choice(LOGIC_QUESTIONS)
        )

        pending[uid] = {
            "answer": answer.lower(),
            "level": level,
            "mode": mode,
            "time": time.time()
        }

        await q.message.reply_text(
            f"🧠 **Think Fast!**\n\n"
            f"⏱ Time: {TIME_LIMIT[level]}s\n"
            f"🎯 Difficulty: {level.capitalize()}\n\n"
            f"❓ {question}",
            parse_mode="Markdown"
        )

    elif q.data == "balance":
        cur.execute(
            "SELECT balance, streak, daily_count FROM users WHERE user_id=?",
            (uid,)
        )
        bal, st, dc = cur.fetchone()
        await q.message.reply_text(
            f"💰 **Your Stats**\n\n"
            f"Balance: ₱{bal}\n"
            f"Streak: 🔥 {st}\n"
            f"Today: {dc}/{DAILY_LIMIT}\n"
            f"Referrals: 👥 {referral_count(uid)}\n\n"
            f"🔗 https://t.me/{BOT_USERNAME}?start={uid}",
            parse_mode="Markdown"
        )

    elif q.data == "withdraw":
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = cur.fetchone()[0]
        if bal < MIN_WITHDRAW:
            await q.message.reply_text(f"❌ Minimum withdrawal ₱{MIN_WITHDRAW}")
            return
        withdraw_waiting[uid] = True
        await q.message.reply_text(
            f"🏦 **Withdrawal Request**\n\n"
            f"Send ₱15 fee to:\n📱 {TX_FEE_NUMBER}\n\n"
            "Then send the reference number here.",
            parse_mode="Markdown"
        )

    elif q.data == "leaderboard":
        cur.execute("""
        SELECT referrer, COUNT(*) FROM referrals
        GROUP BY referrer
        ORDER BY COUNT(*) DESC LIMIT 5
        """)
        rows = cur.fetchall()
        msg = "🏆 **Top Referrers**\n\n"
        for i, r in enumerate(rows, 1):
            msg += f"{i}. User {r[0]} — {r[1]} invites\n"
        await q.message.reply_text(msg or "No referrals yet.", parse_mode="Markdown")

    elif q.data == "rules":
        await q.message.reply_text(
            "📜 **Rules**\n\n"
            "• One account per user\n"
            "• No cheating or bots\n"
            "• Daily limits apply\n"
            "• Admin decision is final",
            parse_mode="Markdown"
        )

    elif q.data == "back":
        await q.message.reply_text("🏠 Main Menu", reply_markup=main_menu())

# ================== TEXT ==================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text.lower()

    if uid in pending:
        data = pending.pop(uid)

        if time.time() - data["time"] > TIME_LIMIT[data["level"]]:
            cur.execute("UPDATE users SET streak=0 WHERE user_id=?", (uid,))
            db.commit()
            await update.message.reply_text("⏰ Time’s up!", reply_markup=main_menu())
            return

        if txt == data["answer"]:
            reward = REWARDS[data["level"]]
            cur.execute("""
            UPDATE users SET
            balance = balance + ?,
            streak = streak + 1,
            daily_count = daily_count + 1
            WHERE user_id=?
            """, (reward, uid))
            db.commit()

            cur.execute("SELECT streak FROM users WHERE user_id=?", (uid,))
            streak = cur.fetchone()[0]

            bonus = ""
            if streak % STREAK_BONUS_EVERY == 0:
                cur.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id=?",
                    (STREAK_BONUS_AMOUNT, uid)
                )
                db.commit()
                bonus = f"\n🎁 Bonus: +₱{STREAK_BONUS_AMOUNT}"

            await update.message.reply_text(
                f"✅ **Correct!**\n\n"
                f"💰 Reward: +₱{reward}{bonus}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "➡ Proceed to Next Question",
                        callback_data=f"{data['mode']}_{data['level']}"
                    )],
                    [InlineKeyboardButton("⬅ Back to Menu", callback_data="back")]
                ]),
                parse_mode="Markdown"
            )
        else:
            cur.execute("UPDATE users SET streak=0 WHERE user_id=?", (uid,))
            db.commit()
            await update.message.reply_text("❌ Wrong answer", reply_markup=main_menu())
        return

    if uid in withdraw_waiting:
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = cur.fetchone()[0]
        cur.execute("UPDATE users SET balance=0 WHERE user_id=?", (uid,))
        db.commit()

        await context.bot.send_message(
            ADMIN_ID,
            f"💸 Withdrawal Request\nUser: {uid}\nAmount: ₱{bal}\nRef: {txt}"
        )
        withdraw_waiting.pop(uid)
        await update.message.reply_text("⏳ Sent to admin for approval.")

# ================== RUN ==================
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("🧠 Think2EarnBot is running...")
app.run_polling()
          
