import os
import asyncio
import imaplib
import email
import random
import string
from datetime import datetime, timedelta
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
from threading import Thread
from db import get_settings, update_setting

# ================= CONFIGURATION =================
API_ID = int(os.environ.get("API_ID", 1234567))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 123456789))
# =================================================

# 1. Flask App (Render Port 8080 Binding)
app = Flask(__name__)

@app.route('/')
def home():
    return "KCXRY Payment Bot is live and running on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Pyrogram Bot Client Setup
bot = Client(
    "kcxry_payment_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user_data = {}
setup_states = {}

def generate_order_id():
    letters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(letters) for i in range(8))

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    user_data[user_id] = {"step": "awaiting_amount"}
    
    settings = get_settings()
    
    await message.reply(
        f"👋 **ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴀᴜᴛᴏᴍᴀᴛᴇᴅ ᴘᴀʏᴍᴇɴᴛ ʙᴏᴛ!**\n\n"
        f"💳 **ᴀᴄᴛɪᴠᴇ ɢᴀᴛᴇᴡᴀʏ:** {settings['gateway_name']}\n"
        f"💼 **ᴜᴘɪ ɪᴅ:** `{settings['upi_id']}`\n\n"
        "💰 **ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴛʜᴇ ᴀᴍᴏᴜɴᴛ (ɪɴ ɪɴʀ):**\n"
        "(ᴇxᴀᴍᴘʟᴇ: `49`, `99`, `500` ᴇᴛᴄ.)\n\n"
        "⚡ *ʙʏ: ᴋᴄxʀʏ*"
    )

# ================= STEP-BY-STEP SETUP WIZARD =================
@bot.on_message(filters.command("setup") & filters.user(ADMIN_ID))
async def start_setup_wizard(client, message):
    setup_states[message.from_user.id] = {"step": "waiting_for_gmail"}
    await message.reply("📧 **ᴘʟᴇᴀsᴇ sᴇɴᴅ ʏᴏᴜʀ ɢᴍᴀɪʟ ɪᴅ:**\n*(ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ғᴏʀ sᴇᴄᴜʀɪᴛʏ)*")

@bot.on_message(filters.command("setupi") & filters.user(ADMIN_ID))
async def set_upi_command(client, message):
    try:
        args = message.text.split(" ", 1)[1]
        upi, name = args.split("|")
        upi = upi.strip()
        name = name.strip()
        
        update_setting("upi_id", upi)
        update_setting("upi_name", name)
        
        await message.reply(f"✅ **ᴜᴘɪ ᴅᴇᴛᴀɪʟs ᴜᴘᴅᴀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!**\n\nᴜᴘɪ: `{upi}`\nɴᴀᴍᴇ: `{name}`\n\n⚡ *ʙʏ: ᴋᴄxʀʏ*")
    except Exception as e:
        await message.reply("❌ **ɪɴᴠᴀʟɪᴅ ғᴏʀᴍᴀᴛ!** ᴄᴏʀʀᴇᴄᴛ ᴜsᴀɢᴇ:\n`/setupi yourname@okaxis | Merchant Name`")

@bot.on_message(filters.command("settings") & filters.user(ADMIN_ID))
async def view_settings_command(client, message):
    s = get_settings()
    await message.reply(
        f"⚙️ **ᴄᴜʀʀᴇɴᴛ ʙᴏᴛ sᴇᴛᴛɪɴɢs (ғʀᴏᴍ ᴅʙ):**\n\n"
        f"📧 **ɢᴍᴀɪʟ:** `{s['gmail_user']}`\n"
        f"🔑 **ᴀᴘᴘ ᴘᴀssᴡᴏʀᴅ:** `********`\n"
        f"💼 **ᴜᴘɪ ɪᴅ:** `{s['upi_id']}`\n"
        f"👤 **ɴᴀᴍᴇ:** `{s['upi_name']}`\n\n"
        f"⚡ *ʙʏ: ᴋᴄxʀʏ*"
    )
# ==============================================================

@bot.on_message(filters.text & ~filters.command(["start", "setup", "setupi", "settings"]))
async def handle_text_inputs(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # 1. Setup Wizard Steps
    if user_id in setup_states:
        state = setup_states[user_id].get("step")
        
        if state == "waiting_for_gmail":
            setup_states[user_id]["temp_gmail"] = text
            setup_states[user_id]["step"] = "waiting_for_password"
            try:
                await message.delete()
            except:
                pass
            await message.reply("🔑 **ɢʀᴇᴀᴛ! ɴᴏᴡ sᴇɴᴅ ʏᴏᴜʀ ɢᴍᴀɪʟ ᴀᴘᴘ ᴘᴀssᴡᴏʀᴅ:**\n*(ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ᴀʟsᴏ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ)*")
            return
            
        elif state == "waiting_for_password":
            gmail_user = setup_states[user_id].get("temp_gmail")
            gmail_pass = text
            
            update_setting("gmail_user", gmail_user)
            update_setting("gmail_pass", gmail_pass)
            
            setup_states.pop(user_id, None)
            try:
                await message.delete()
            except:
                pass
                
            await message.reply(
                "✅ **ɢᴍᴀɪʟ sᴇᴛᴜᴘ ᴄᴏᴍᴘʟᴇᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!** 🎉\n"
                f"📧 ᴇᴍᴀɪʟ: `{gmail_user}`\n"
                f"🔑 ᴀᴘᴘ ᴘᴀssᴡᴏʀᴅ sᴀᴠᴇᴅ sᴇᴄᴜʀᴇʟʏ.\n\n"
                f"⚡ *ʙʏ: ᴋᴄxʀʏ*"
            )
            return

    # 2. General User / Payment Flow
    if user_id not in user_data:
        user_data[user_id] = {"step": "idle"}
    
    current_step = user_data[user_id].get("step")

    if current_step == "awaiting_amount":
        if not text.isdigit() or int(text) <= 0:
            await message.reply("❌ **ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ** (ᴇ.ɢ., `100`).")
            return
        
        amount = int(text)
        order_id = f"ORD-{generate_order_id()}"
        expires_at = datetime.now() + timedelta(minutes=10)
        
        settings = get_settings()
        
        user_data[user_id]["amount"] = amount
        user_data[user_id]["order_id"] = order_id
        user_data[user_id]["expires_at"] = expires_at
        user_data[user_id]["step"] = "awaiting_utr"
        
        upi_url = f"upi://pay?pa={settings['upi_id']}&pn={settings['upi_name']}&am={amount}&cu=INR&tn=Order_{order_id}"
        
        details_text = (
            f"🧾 **ᴏʀᴅᴇʀ ᴅᴇᴛᴀɪʟs & ɪɴᴠᴏɪᴄᴇ**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 **ᴏʀᴅᴇʀ ɪᴅ:** `{order_id}`\n"
            f"💵 **ᴀᴍᴏᴜɴᴛ:** ₹{amount}\n"
            f"⏱ **ᴇxᴘɪʀᴇs ɪɴ:** 10 ᴍɪɴᴜᴛᴇs (ᴀᴛ {expires_at.strftime('%H:%M:%S')})\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 **ɢᴀᴛᴇᴡᴀʏ:** {settings['gateway_name']}\n"
            f"💼 **ᴜᴘɪ ɪᴅ:** `{settings['upi_id']}`\n"
            f"👤 **ɴᴀᴍᴇ:** `{settings['upi_name']}`\n\n"
            f"🔗 **ᴅɪʀᴇᴄᴛ ᴜᴘɪ ʟɪɴᴋ:** [ᴄʟɪᴄᴋ ᴛᴏ ᴘᴀʏ]({upi_url})\n\n"
            f"⚠️ ᴘᴀʏ ᴛʜᴇ ᴀʙᴏᴠᴇ ᴀᴍᴏᴜɴᴛ ᴀɴᴅ ᴄʟɪᴄᴋ **'I Have Paid'** ᴛᴏ ᴘʀᴏᴠɪᴅᴇ ʏᴏᴜʀ ᴜᴛʀ.\n\n"
            f"⚡ *ʙʏ: ᴋᴄxʀʏ*"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ ɪ ʜᴀᴠᴇ ᴘᴀɪᴅ (ᴠᴇʀɪғʏ ᴜᴛʀ)", callback_data="ask_utr")],
            [InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ ᴏʀᴅᴇʀ", callback_data="cancel_order")]
        ])
        
        await message.reply(details_text, disable_web_page_preview=True, reply_markup=keyboard)
        return

    elif current_step == "awaiting_utr":
        order_info = user_data[user_id]
        
        if datetime.now() > order_info["expires_at"]:
            await message.reply("⏳ **ᴛʜɪs ᴏʀᴅᴇʀ ʜᴀs ᴇxᴘɪʀᴇᴅ!** ᴘʟᴇᴀsᴇ ᴛʏᴘᴇ `/start` ᴛᴏ ᴄʀᴇᴀᴛᴇ ᴀ ɴᴇᴡ ᴏʀᴅᴇʀ.")
            user_data[user_id]["step"] = "idle"
            return
            
        utr = text
        if len(utr) < 8:
            await message.reply("❌ **ɪɴᴠᴀʟɪᴅ ᴜᴛʀ!** ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ 12-ᴅɪɢɪᴛ ᴜᴛʀ/ʀᴇғᴇʀᴇɴᴄᴇ ɴᴜᴍʙᴇʀ.")
            return
            
        processing_msg = await message.reply("⏳ **ᴠᴇʀɪғʏɪɴɢ ʏᴏᴜʀ ᴘᴀʏᴍᴇɴᴛ ᴠɪᴀ ɢᴍᴀɪʟ...**")
        
        loop = asyncio.get_running_loop()
        is_verified = await loop.run_in_executor(None, verify_utr_in_gmail, utr, order_info["amount"])
        
        await processing_msg.delete()
        
        if is_verified:
            await message.reply(
                f"🎉 **ᴘᴀʏᴍᴇɴᴛ ᴠᴇʀɪғɪᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!**\n"
                f"🆔 **ᴏʀᴅᴇʀ ɪᴅ:** `{order_info['order_id']}`\n"
                f"💵 **ᴀᴍᴏᴜɴᴛ ᴘᴀɪᴅ:** ₹{order_info['amount']}\n\n"
                f"ʏᴏᴜʀ ᴛʀᴀɴsᴀᴄᴛɪᴏɴ ʜᴀs ʙᴇᴇɴ ᴄᴏᴍᴘʟᴇᴛᴇᴅ.\n\n"
                f"⚡ *ʙʏ: ᴋᴄxʀʏ*"
            )
            user_data[user_id]["step"] = "idle"
        else:
            await message.reply(
                "❌ **ᴘᴀʏᴍᴇɴᴛ ɴᴏᴛ ғᴏᴜɴᴅ / ᴍᴀᴛᴄʜᴇᴅ!**\n"
                "ᴘᴏssɪʙʟᴇ ʀᴇᴀsᴏɴs:\n"
                "1. ɪɴᴄᴏʀʀᴇᴄᴛ ᴜᴛʀ ɴᴜᴍʙᴇʀ.\n"
                "2. ʙᴀɴᴋ/ɢᴀᴛᴇᴡᴀʏ ᴇᴍᴀɪʟ ɴᴏᴛ ʀᴇᴄᴇɪᴠᴇᴅ ʏᴇᴛ.\n\n"
                "ᴘʟᴇᴀsᴇ ᴠᴇʀɪғʏ ᴀɴᴅ sᴇɴᴅ ᴛʜᴇ ᴄᴏʀʀᴇᴄᴛ ᴜᴛʀ ᴀɢᴀɪɴ."
            )

@bot.on_callback_query(filters.regex("^ask_utr"))
async def ask_for_utr(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id in user_data and datetime.now() > user_data[user_id].get("expires_at", datetime.min):
        await callback_query.answer("⚠️ ᴛʜɪs ᴏʀᴅᴇʀ ʜᴀs ᴇxᴘɪʀᴇᴅ!", show_alert=True)
        return
        
    await callback_query.message.reply(
        "📝 **ᴘʟᴇᴀsᴇ sᴇɴᴅ ʏᴏᴜʀ 12-ᴅɪɢɪᴛ ᴜᴛʀ / ʀᴇғᴇʀᴇɴᴄᴇ ɴᴜᴍʙᴇʀ:**\n"
        "(ᴇxᴀᴍᴘʟᴇ: `4123xxxxxxxx`)"
    )
    await callback_query.answer()

@bot.on_callback_query(filters.regex("^cancel_order"))
async def cancel_order(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id in user_data:
        user_data[user_id]["step"] = "idle"
    
    await callback_query.message.edit_text("❌ **ᴏʀᴅᴇʀ ᴄᴀɴᴄᴇʟʟᴇᴅ.** ᴛʏᴘᴇ `/start` ᴛᴏ sᴛᴀʀᴛ ᴀɢᴀɪɴ.")
    await callback_query.answer()

# Gmail IMAP Verification Function
def verify_utr_in_gmail(utr_number, expected_amount):
    try:
        settings = get_settings()
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(settings["gmail_user"], settings["gmail_pass"])
        mail.select("inbox")
        
        date_since = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{date_since}")')
        
        if status != "OK":
            mail.logout()
            return False

        for num in messages[0].split():
            status, data = mail.fetch(num, "(RFC822)")
            if status != "OK":
                continue
            
            msg = email.message_from_bytes(data[0][1])
            body = ""
            
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except:
                            pass
            else:
                try:
                    body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                except:
                    pass
            
            if utr_number in body and str(expected_amount) in body:
                mail.logout()
                return True

        mail.logout()
        return False
    except Exception as e:
        print(f"IMAP Error: {e}")
        return False

async def main():
    await bot.start()
    try:
        await bot.send_message(
            ADMIN_ID,
            "🤖 **ʙᴏᴛ ʀᴇsᴛᴀʀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!**\n\n"
            "⚡ sᴇʀᴠᴇʀ ɪs ᴏɴʟɪɴᴇ ᴀɴᴅ ᴛʜᴇ ʙᴏᴛ ɪs ʀᴇᴀᴅʏ.\n"
            "👑 **ᴅᴇᴠᴇʟᴏᴘᴇᴅ ʙʏ:** ᴋᴄxʀʏ"
        )
    except Exception as e:
        print(f"Startup Notification Error: {e}")
    print("🤖 KCXRY Payment Bot & Port 8080 Server Started Successfully!")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    bot.run(main())
