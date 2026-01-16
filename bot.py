import os
import sqlite3
import time
import random
import threading
from datetime import date
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes,
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "think2EarnBot" 
ADMIN_ID = 775857744 
REFERRAL_REWARD = 48.88 
MIN_WITHDRAW = 1000
WITHDRAW_FEE = 15.00
INVITE_LOCK_COUNT = 15  
DAILY_LIMIT = 5

ADMIN_GCASH = "09939775174"
ADMIN_PAYMAYA = "09939775174"

REWARDS = {"easy": 20, "medium": 40, "hard": 88, "logic": 88}

# ================== RENDER PORT FIX ==================
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

def init_db():
    conn = sqlite3.connect("think2earn.db")
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        referrals_after_fee INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        last_puzzle_date TEXT DEFAULT '',
        puzzles_done_today INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active'
    )
    """)
    c.execute("CREATE TABLE IF NOT EXISTS referrals (referrer INTEGER, referred INTEGER UNIQUE)")
    conn.commit()
    conn.close()

init_db()
pending = {} 

# ================== QUESTIONS ==================
LOGIC_QUESTIONS = [
    ("What has keys but no locks?", "keyboard"),
    ("What gets wetter as it dries?", "towel"),
    ("What belongs to you, but others use it more?", "name"),
    ("What has a neck but no head?", "bottle"),
    ("What has an eye but cannot see?", "needle")
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

def cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)

def admin_approval_keyboard(user_id, amount):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve Fee", callback_data=f"app_{user_id}_{amount}")],
        [InlineKeyboardButton("❌ Reject Fee", callback_data=f"rej_{user_id}")]
    ])

# ================== HELPERS ==================
def get_user(uid):
    conn = sqlite3.connect("think2earn.db")
    c = conn.cursor()
    c.execute("SELECT balance, streak, last_puzzle_date, puzzles_done_today FROM users WHERE user_id=?", (uid,))
    res = c.fetchone()
    conn.close()
    if res:
        return res
    return (0, 0, "", 0)

def can_do_puzzle(uid):
    today = date.today().isoformat()
    user = get_user(uid)
    last_date = user[2]
    done_today = user[3]
    
    if last_date != today:
        conn = sqlite3.connect("think2earn.db")
        c = conn.cursor()
        c.execute("UPDATE users SET puzzles_done_today = 0, last_puzzle_date = ? WHERE user_id = ?", (today, uid))
        conn.commit()
        conn.close()
        return True, 0
    
    return done_today < DAILY_LIMIT, done_today

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.first_name
    
    conn = sqlite3.connect("think2earn.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
    is_new = c.fetchone() is None

    if is_new:
        args = context.args
        if args and args[0].isdigit() and int(args[0]) != uid:
            referrer_id = int(args[0])
            try:
                # Ensure referrer is in DB before updating
                c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (referrer_id, "User"))
                c.execute("INSERT INTO referrals (referrer, referred) VALUES (?, ?)", (referrer_id, uid))
                c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (REFERRAL_REWARD, referrer_id))
                conn.commit()
                try: await context.bot.send_message(chat_id=referrer_id, text=f"👥 <b>New Referral!</b>\nYou earned ₱{REFERRAL_REWARD} from {uname}!", parse_mode="HTML")
                except: pass
            except sqlite3.IntegrityError: pass 

        c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, uname))
        conn.commit()
    conn.close()
    
    welcome = (
        f"👋 <b>Welcome to Think2Earn, {uname}!</b>\n\n"
        "Earn real money by solving puzzles and inviting friends.\n"
        "• <b>Math & Logic:</b> Daily brain exercises.\n"
        "• <b>Daily Limit:</b> 5 Puzzles per day.\n"
        "• <b>Referrals:</b> ₱48.88 per friend!\n\n"
        "<i>Click a button below to begin.</i>"
    )
    await update.message.reply_text(welcome, reply_markup=main_menu_keyboard(), parse_mode="HTML")

# ================== MESSAGE HANDLER ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    # Safety: Ensure user exists in DB before processing
    conn = sqlite3.connect("think2earn.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, update.effective_user.first_name))
    conn.commit()

    menu_options = ["🧮 Math", "🧠 Logic", "💰 Balance", "👥 Referrals", "📜 Rules", "💸 Withdraw", "🏆 Leaderboard"]
    
    if text in menu_options or text == "❌ Cancel":
        if uid in pending: pending.pop(uid)
        
        if text == "❌ Cancel":
            await update.message.reply_text("Process cancelled.", reply_markup=main_menu_keyboard())
            conn.close()
            return
        
        if text == "🧠 Logic":
            allowed, count = can_do_puzzle(uid)
            if not allowed:
                await update.message.reply_text("⏳ <b>Daily Limit Reached!</b>\nYou've done 5/5 puzzles. Come back tomorrow!", parse_mode="HTML")
            else:
                q, a = random.choice(LOGIC_QUESTIONS)
                pending[uid] = {"answer": a.lower(), "level": "logic"}
                await update.message.reply_text(f"<b>Riddle:</b>\n{q}", reply_markup=cancel_keyboard(), parse_mode="HTML")
        elif text == "🧮 Math":
            allowed, _ = can_do_puzzle(uid)
            if not allowed:
                await update.message.reply_text("⏳ <b>Daily Limit Reached!</b>", parse_mode="HTML")
            else:
                keyboard = [[InlineKeyboardButton("Easy ₱20", callback_data="math_easy"), InlineKeyboardButton("Med ₱40", callback_data="math_medium"), InlineKeyboardButton("Hard ₱88", callback_data="math_hard")]]
                await update.message.reply_text("Select Difficulty:", reply_markup=InlineKeyboardMarkup(keyboard))
        elif text == "💰 Balance":
            user = get_user(uid)
            await update.message.reply_text(f"💳 <b>Wallet Balance:</b> ₱{user[0]:.2f}\n🔥 <b>Current Streak:</b> {user[1]}", parse_mode="HTML")
        elif text == "👥 Referrals":
            link = f"https://t.me/{BOT_USERNAME}?start={uid}"
            c.execute("SELECT COUNT(*) FROM referrals WHERE referrer=?", (uid,))
            total_refs = c.fetchone()[0]
            ad_msg = f"🚀 <b>Join Think2Earn!</b>\nSolve puzzles and earn ₱1,000+ GCash easily. 👉 {link}"
            await update.message.reply_text(f"👥 <b>Your Referral Link:</b>\n<code>{link}</code>\n\n🎁 Earn ₱{REFERRAL_REWARD} per friend!\n📈 Total Referrals: {total_refs}\n\n📢 <b>Advertising Message:</b>\n<pre>{ad_msg}</pre>", parse_mode="HTML")
        elif text == "🏆 Leaderboard":
            c.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10")
            rows = c.fetchall()
            lb = "🏆 <b>TOP 10 EARNERS</b>\n\n"
            for i, r in enumerate(rows, 1): lb += f"{i}. {r[0] or 'User'} — ₱{r[1]:.2f}\n"
            await update.message.reply_text(lb, parse_mode="HTML")
        elif text == "📜 Rules":
            await update.message.reply_text("📜 <b>Terms & Conditions:</b>\n1. Max 5 puzzles/day.\n2. Streak bonus for 3+ wins.\n3. Payouts in 24-48h.", parse_mode="HTML")
        elif text == "💸 Withdraw":
            await update.message.reply_text("Choose Withdrawal Method:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("GCash", callback_data="wd_gcash"), InlineKeyboardButton("PayMaya", callback_data="wd_paymaya")]]))
        
        conn.close()
        return

    # Process Pending
    if uid in pending:
        data = pending[uid]
        if "answer" in data:
            pending.pop(uid)
            if text.strip().lower() == str(data["answer"]).lower():
                reward = REWARDS[data["level"]]
                c.execute("UPDATE users SET balance = balance + ?, streak = streak + 1, puzzles_done_today = puzzles_done_today + 1 WHERE user_id = ?", (reward, uid))
                conn.commit()
                user = get_user(uid)
                await update.message.reply_text(f"✨ <b>Correct!</b>\nReward: +₱{reward}\n💰 Balance: ₱{user[0]:.2f}\n🔥 Streak: {user[1]}", parse_mode="HTML", reply_markup=main_menu_keyboard())
            else:
                c.execute("UPDATE users SET streak = 0, puzzles_done_today = puzzles_done_today + 1 WHERE user_id = ?", (uid,))
                conn.commit()
                await update.message.reply_text(f"❌ <b>Incorrect.</b>\nAnswer: {data['answer']}\nStreak broken!", reply_markup=main_menu_keyboard())
        elif "step" in data:
            if data["step"] == "GET_NAME":
                data["acc_name"], data["step"] = text, "GET_NUMBER"
                await update.message.reply_text(f"📱 Enter {data['wd_method']} Number:", reply_markup=cancel_keyboard())
            elif data["step"] == "GET_NUMBER":
                data["acc_num"], data["step"] = text, "GET_AMOUNT"
                await update.message.reply_text("💰 Enter Amount (Min ₱1000):", reply_markup=cancel_keyboard())
            elif data["step"] == "GET_AMOUNT":
                try:
                    amt = float(text)
                    user = get_user(uid)
                    if amt < MIN_WITHDRAW or user[0] < amt:
                        await update.message.reply_text("❌ Insufficient balance or amount too low.")
                    else:
                        data["amt"], data["step"] = amt, "CONFIRM"
                        confirm_txt = f"⚠️ <b>Confirm Details</b>\nMethod: {data['wd_method']}\nName: {data['acc_name']}\nNumber: {data['acc_num']}\nAmount: ₱{amt}\n\nIs this correct?"
                        await update.message.reply_text(confirm_txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Confirm", callback_data="confirm_wd"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_wd")]]), parse_mode="HTML")
                except: await update.message.reply_text("❌ Enter a valid number.")
    
    conn.close()

# ================== CALLBACK HANDLER ==================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()

    if data.startswith("math_"):
        diff = data.split("_")[1]
        if diff == "easy": a, b, op = random.randint(1,20), random.randint(1,20), "+"
        elif diff == "medium": a, b, op = random.randint(20,100), random.randint(1,50), "-"
        else: a, b, op = random.randint(10,50), random.randint(2,10), "*"
        ans = eval(f"{a}{op}{b}")
        pending[uid] = {"answer": ans, "level": diff}
        await query.message.reply_text(f"🔢 <b>Math ({diff.upper()}):</b>\nWhat is {a} {op} {b}?", reply_markup=cancel_keyboard(), parse_mode="HTML")

    elif data.startswith("wd_"):
        pending[uid] = {"wd_method": "GCash" if "gcash" in data else "PayMaya", "step": "GET_NAME"}
        await query.message.reply_text(f"👤 Enter {pending[uid]['wd_method']} Account Name:", reply_markup=cancel_keyboard())

    elif data == "confirm_wd" and uid in pending:
        pending[uid]["step"] = "AWAIT_PROOF"
        num = ADMIN_GCASH if pending[uid]["wd_method"] == "GCash" else ADMIN_PAYMAYA
        await query.message.reply_text(f"🛡 <b>Verification Fee Required</b>\nPay ₱{WITHDRAW_FEE} to {num} and send screenshot.", parse_mode="HTML")

    elif data == "cancel_wd":
        if uid in pending: pending.pop(uid)
        await query.message.edit_text("Withdrawal cancelled.")

    elif data.startswith("app_"): 
        _, target_id, amount = data.split("_")
        await context.bot.send_message(chat_id=target_id, text=f"✅ <b>Approved!</b>\n₱{amount} is being sent to your account.")

# ================== PHOTO HANDLER ==================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in pending and pending[uid].get("step") == "AWAIT_PROOF":
        data = pending.pop(uid)
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, caption=f"💰 WD Request: {uid}\nAmt: {data['amt']}\n{data['wd_method']}: {data['acc_num']}", reply_markup=admin_approval_keyboard(uid, data['amt']))
        await update.message.reply_text("🕒 <b>Proof Sent!</b> Admin will verify shortly.")

if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.run_polling()
