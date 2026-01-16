import os
import sqlite3
import time
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "think2EarnBot"

ADMIN_ID = 775857744
# Updated to match the screenshot rewards
REFERRAL_REWARD = 48.88 
MIN_WITHDRAW = 1000
DAILY_LIMIT = 10
WITHDRAW_FEE = 15

REWARDS = {"easy": 20, "medium": 40, "hard": 88} # Hard set to 88 to match "Earn 88"
TIME_LIMIT = {"easy": 20, "medium": 15, "hard": 10}

GCASH_NUMBER = "09939775174"
PAYMAYA_NUMBER = "09939775174"

# ================== DATABASE ==================
db = sqlite3.connect("think2earn.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0,
    all_time_balance REAL DEFAULT 0,
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
    ("What has hands but can't clap?", "clock")
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

# ================== UI (MODIFIED TO MATCH IMAGE) ==================
def main_menu():
    # Buttons are now stacked vertically as per the screenshot
    keyboard = [
        [InlineKeyboardButton("GUESS THE LOGO EARN 88 💸", callback_data="math")],
        [InlineKeyboardButton("Account Balance 💰", callback_data="balance")],
        [InlineKeyboardButton(f"Invite Friends Earn {REFERRAL_REWARD} PHP 💸", callback_data="referrals")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]
    ]
    return InlineKeyboardMarkup(keyboard)

def difficulty_menu(mode):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Easy (₱20)", callback_data=f"{mode}_easy")],
        [InlineKeyboardButton("🟡 Medium (₱40)", callback_data=f"{mode}_medium")],
        [InlineKeyboardButton("🔴 Hard (₱88)", callback_data=f"{mode}_hard")],
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

    # Text style matched to the screenshot promotional tone
    promo_text = (
        "<b>GRABE FREE 2,500 PESOS NA BIGAYAN NGAYON!</b>\n\n"
        "NEW UPDATE TO SOBRANG LAKI NA BIGAYAN INSTANT 2,500 PESOS "
        "AFTER VERIFYING LANG. PARA KA LANG NAG VERIFY NG GCASH.\n\n"
        "KAIBAHAN DITO AFTER VERIFY NYO MAY MARERECEIVE KAYO AGAD "
        "NG 2500 PESOS KAHIT ANONG VALID ID PWEDE SAFE TO DAMI NA NAKAWITHDRAW!\n\n"
        "👇 <b>CLICK BUTTONS BELOW TO START EARNING</b> 👇"
    )
    
    await update.message.reply_text(
        promo_text,
        reply_markup=main_menu(),
        parse_mode="HTML"
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
            await query.edit_message_text("❌ Daily limit reached. Come back tomorrow!", reply_markup=main_menu())
            return
        await query.edit_message_text("🎯 Select Game Difficulty:", reply_markup=difficulty_menu(query.data))

    elif "_" in query.data and not query.data.startswith("withdraw_"):
        mode, level = query.data.split("_")
        question, answer = math_question(level) if mode == "math" else random.choice(LOGIC_QUESTIONS)
        pending[uid] = {"answer": answer.lower(), "time": time.time(), "level": level}
        await query.message.reply_text(f"⏱ You have {TIME_LIMIT[level]} seconds!\n\n❓ <b>{question}</b>", parse_mode="HTML")

    elif query.data == "balance":
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        balance = cur.fetchone()[0]
        await query.edit_message_text(f"💰 <b>Your Current Balance:</b> ₱{balance:.2f}", reply_markup=main_menu(), parse_mode="HTML")

    elif query.data == "referrals":
        ref_link = f"https://t.me/{BOT_USERNAME}?start={uid}"
        await query.edit_message_text(
            f"👥 <b>Referral Program</b>\n\nShare your link and earn ₱{REFERRAL_REWARD} for every user!\n\n🔗 <code>{ref_link}</code>",
            reply_markup=main_menu(),
            parse_mode="HTML"
        )

    elif query.data == "withdraw":
        await query.edit_message_text("💸 Choose withdrawal method:", reply_markup=withdrawal_menu())

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
        
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (total, uid))
        db.commit()
        number = GCASH_NUMBER if data["withdraw_method"] == "gcash" else PAYMAYA_NUMBER
        await query.message.reply_text(f"✅ Withdrawal Requested!\nSend ₱{amount} + ₱{WITHDRAW_FEE} fee to {number}")

    elif query.data == "back":
        await query.edit_message_text("🏠 Main Menu", reply_markup=main_menu())

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
            await update.message.reply_text(f"✅ Correct! +₱{reward}", reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Wrong answer!", reply_markup=main_menu())
        return

    if uid in pending and pending[uid].get("step") == "amount":
        try:
            amt = float(txt)
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

# ================== RENDER HEALTH CHECK SERVER ==================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

# ================== MAIN STARTUP ==================
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    
    threading.Thread(target=run_dummy_server, daemon=True).start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(buttons))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("LOGO88 Bot is starting...")
    application.run_polling()
