import os
import asyncio
import re
import hmac
import random
import string
from io import BytesIO
from urllib.parse import quote
import qrcode
from PIL import Image
from datetime import datetime, timedelta
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request
from threading import Thread
from db import (get_settings, update_setting, save_payment, claim_payment,
                set_client, get_client, del_client, list_clients,
                save_order, mark_delivered, bump_attempt, pending_orders)
from integration import parse_payload, verify_payload, post_callback

# ================= CONFIGURATION =================
API_ID = int(os.environ.get("API_ID", 1234567))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 123456789))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
MAX_UTR_ATTEMPTS = 5
# =================================================

# 1. Flask App (Render Port 8080 Binding)
app = Flask(__name__)

@app.route('/')
def home():
    return "KCXRY Payment Bot is live and running on Render!"


# MacroDroid -> POST/GET /payment?key=SECRET  (text=<notification text>  OR  utr=..&amount=..)
@app.route('/payment', methods=['GET', 'POST'])
def payment_webhook():
    data = {}
    data.update(request.args.to_dict())
    data.update(request.form.to_dict())
    if request.is_json:
        data.update(request.get_json(silent=True) or {})

    key = str(data.get("key", ""))
    if not WEBHOOK_SECRET or not hmac.compare_digest(key, WEBHOOK_SECRET):
        return "forbidden", 403

    text = str(data.get("text", ""))
    utr = str(data.get("utr", "")).strip()
    amount = str(data.get("amount", "")).strip()

    if not utr:
        m = re.search(r"\b(\d{12})\b", text)
        utr = m.group(1) if m else ""
    if not amount:
        m = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)", text, re.I)
        amount = m.group(1).replace(",", "") if m else ""

    utr = re.sub(r"[^A-Za-z0-9]", "", utr).upper()
    try:
        amount_val = float(amount)
    except ValueError:
        return "bad amount", 400
    if len(utr) < 8 or amount_val <= 0:
        return "bad utr/amount", 400

    return ("saved", 200) if save_payment(utr, amount_val, text) else ("duplicate", 200)

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

def generate_order_id():
    letters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(letters) for i in range(8))

def make_qr_image(data, size=250):
    """Black & white QR, exactly size x size pixels, returned as in-memory PNG."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((size, size), Image.LANCZOS)
    bio = BytesIO()
    bio.name = "payment_qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    user_data[user_id] = {"step": "awaiting_amount"}

    # Redirect from another bot: /start pay-<key>-<amount>-<ref>-<sig>
    if len(message.command) > 1:
        parsed = parse_payload(message.command[1])
        client_cfg = get_client(parsed[0]) if parsed else None
        if not parsed or not client_cfg or not verify_payload(
                client_cfg["secret"], user_id, parsed[1], parsed[2], parsed[3]):
            await message.reply("❌ **ɪɴᴠᴀʟɪᴅ ᴏʀ ᴇxᴘɪʀᴇᴅ ᴘᴀʏᴍᴇɴᴛ ʟɪɴᴋ!**\nᴘʟᴇᴀsᴇ ɢᴏ ʙᴀᴄᴋ ᴛᴏ ᴛʜᴇ ʙᴏᴛ ᴀɴᴅ ᴛᴀᴘ ᴛʜᴇ ᴘᴀʏ ʙᴜᴛᴛᴏɴ ᴀɢᴀɪɴ.")
            user_data[user_id] = {"step": "idle"}
            return
        await create_order(message, user_id, parsed[1], parsed[0], parsed[2])
        return

    settings = get_settings()
    
    await message.reply(
        f"👋 **ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴀᴜᴛᴏᴍᴀᴛᴇᴅ ᴘᴀʏᴍᴇɴᴛ ʙᴏᴛ!**\n\n"
        f"💳 **ᴀᴄᴛɪᴠᴇ ɢᴀᴛᴇᴡᴀʏ:** {settings['gateway_name']}\n"
        f"💼 **ᴜᴘɪ ɪᴅ:** `{settings['upi_id']}`\n\n"
        "💰 **ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴛʜᴇ ᴀᴍᴏᴜɴᴛ (ɪɴ ɪɴʀ):**\n"
        "(ᴇxᴀᴍᴘʟᴇ: `49`, `99`, `500` ᴇᴛᴄ.)\n\n"
        "⚡ *ʙʏ: ᴋᴄxʀʏ*"
    )

# ================= ADMIN COMMANDS =================
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
        f"💼 **ᴜᴘɪ ɪᴅ:** `{s['upi_id']}`\n"
        f"👤 **ɴᴀᴍᴇ:** `{s['upi_name']}`\n\n"
        f"⚡ *ʙʏ: ᴋᴄxʀʏ*"
    )
# ==============================================================

async def create_order(message, user_id, amount, client_key=None, ref=None):
    # "invoice generating" message - deleted once the QR/details are ready
    wait_msg = await message.reply("⏳ **ʏᴏᴜʀ ɪɴᴠᴏɪᴄᴇ ɪs ɢᴇɴᴇʀᴀᴛɪɴɢ, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...**")

    order_id = f"ORD-{generate_order_id()}"
    expires_at = datetime.now() + timedelta(minutes=10)

    settings = get_settings()

    user_data.setdefault(user_id, {})
    user_data[user_id]["amount"] = amount
    user_data[user_id]["order_id"] = order_id
    user_data[user_id]["expires_at"] = expires_at
    user_data[user_id]["created_utc"] = datetime.utcnow()
    user_data[user_id]["attempts"] = 0
    user_data[user_id]["client"] = client_key
    user_data[user_id]["ref"] = ref
    user_data[user_id]["step"] = "awaiting_utr"

    upi_url = (
        f"upi://pay?pa={quote(settings['upi_id'], safe='@')}"
        f"&pn={quote(settings['upi_name'])}"
        f"&am={amount}&cu=INR&tn={quote('Order_' + order_id)}"
    )

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

    try:
        qr_img = make_qr_image(upi_url, 250)
        if len(details_text) <= 1024:
            await message.reply_photo(qr_img, caption=details_text, reply_markup=keyboard)
        else:
            await message.reply_photo(qr_img)
            await message.reply(details_text, disable_web_page_preview=True, reply_markup=keyboard)
    except Exception as e:
        print(f"QR Error: {e}")
        await message.reply(details_text, disable_web_page_preview=True, reply_markup=keyboard)

    try:
        await wait_msg.delete()
    except Exception:
        pass

@bot.on_message(filters.text & ~filters.command(["start", "setupi", "settings", "addbot", "delbot", "bots"]))
async def handle_text_inputs(client, message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id not in user_data:
        user_data[user_id] = {"step": "idle"}

    current_step = user_data[user_id].get("step")

    if current_step == "awaiting_amount":
        if not text.isdigit() or int(text) <= 0:
            await message.reply("❌ **ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ** (ᴇ.ɢ., `100`).")
            return

        await create_order(message, user_id, int(text))
        return

    elif current_step == "awaiting_utr":
        order_info = user_data[user_id]

        if datetime.now() > order_info["expires_at"]:
            await message.reply("⏳ **ᴛʜɪs ᴏʀᴅᴇʀ ʜᴀs ᴇxᴘɪʀᴇᴅ!** ᴘʟᴇᴀsᴇ ᴛʏᴘᴇ `/start` ᴛᴏ ᴄʀᴇᴀᴛᴇ ᴀ ɴᴇᴡ ᴏʀᴅᴇʀ.")
            user_data[user_id]["step"] = "idle"
            return

        utr = re.sub(r"[^A-Za-z0-9]", "", text).upper()
        if len(utr) < 8:
            await message.reply("❌ **ɪɴᴠᴀʟɪᴅ ᴜᴛʀ!** ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ 12-ᴅɪɢɪᴛ ᴜᴛʀ/ʀᴇғᴇʀᴇɴᴄᴇ ɴᴜᴍʙᴇʀ.")
            return

        processing_msg = await message.reply("⏳ **ᴠᴇʀɪғʏɪɴɢ ʏᴏᴜʀ ᴘᴀʏᴍᴇɴᴛ...**")

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, claim_payment, utr, order_info["amount"], user_id,
            order_info["order_id"], order_info["created_utc"]
        )

        try:
            await processing_msg.delete()
        except Exception:
            pass

        if result == "ok":
            await message.reply(
                f"🎉 **ᴘᴀʏᴍᴇɴᴛ ᴠᴇʀɪғɪᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!**\n"
                f"🆔 **ᴏʀᴅᴇʀ ɪᴅ:** `{order_info['order_id']}`\n"
                f"💵 **ᴀᴍᴏᴜɴᴛ ᴘᴀɪᴅ:** ₹{order_info['amount']}\n\n"
                f"ʏᴏᴜʀ ᴛʀᴀɴsᴀᴄᴛɪᴏɴ ʜᴀs ʙᴇᴇɴ ᴄᴏᴍᴘʟᴇᴛᴇᴅ.\n\n"
                f"⚡ *ʙʏ: ᴋᴄxʀʏ*"
            )
            user_data[user_id]["step"] = "idle"

            if order_info.get("client"):
                order = {
                    "_id": order_info["order_id"], "user_id": user_id,
                    "amount": order_info["amount"], "client": order_info["client"],
                    "ref": order_info["ref"], "paid_at": datetime.utcnow().isoformat(),
                    "delivered": False, "attempts": 0,
                }
                save_order(order)
                delivered = await deliver_order(order)
                cfg = get_client(order["client"]) or {}
                rows = []
                if cfg.get("bot_username"):
                    rows = [[InlineKeyboardButton("🔙 ʙᴀᴄᴋ ᴛᴏ ʙᴏᴛ", url=f"https://t.me/{cfg['bot_username']}")]]
                if delivered:
                    txt = "✅ **ᴍᴇᴍʙᴇʀsʜɪᴘ ᴀᴄᴛɪᴠᴀᴛᴇᴅ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ!**"
                else:
                    txt = "⏳ **ᴘᴀʏᴍᴇɴᴛ ᴅᴏɴᴇ.** ᴀᴄᴛɪᴠᴀᴛɪᴏɴ ɪs ᴅᴇʟᴀʏᴇᴅ, ɪᴛ ᴡɪʟʟ ʜᴀᴘᴘᴇɴ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ sʜᴏʀᴛʟʏ."
                await message.reply(txt, reply_markup=InlineKeyboardMarkup(rows) if rows else None)
            return

        # ---- failed attempt: tell the exact reason
        user_data[user_id]["attempts"] = order_info.get("attempts", 0) + 1

        if result == "used":
            reason = "🚫 **ᴛʜɪs ᴜᴛʀ ɪs ᴀʟʀᴇᴀᴅʏ ᴜsᴇᴅ!**\nᴇᴀᴄʜ ᴜᴛʀ ᴄᴀɴ ʙᴇ ᴜsᴇᴅ ᴏɴʟʏ ᴏɴᴄᴇ."
        elif result == "old":
            reason = ("⏳ **ᴛʜɪs ᴜᴛʀ ɪs ᴇxᴘɪʀᴇᴅ / ᴏʟᴅ!**\n"
                      "ᴛʜɪs ᴘᴀʏᴍᴇɴᴛ ᴡᴀs ᴍᴀᴅᴇ ʙᴇғᴏʀᴇ ᴛʜɪs ᴏʀᴅᴇʀ ᴡᴀs ᴄʀᴇᴀᴛᴇᴅ.")
        elif result == "amount_mismatch":
            reason = ("❌ **ᴀᴍᴏᴜɴᴛ ᴍɪsᴍᴀᴛᴄʜ!**\n"
                      "ᴛʜɪs ᴜᴛʀ's ᴀᴍᴏᴜɴᴛ ᴅᴏᴇs ɴᴏᴛ ᴍᴀᴛᴄʜ ʏᴏᴜʀ ᴏʀᴅᴇʀ.")
        else:  # not_found
            reason = ("❌ **ᴘᴀʏᴍᴇɴᴛ ɴᴏᴛ ғᴏᴜɴᴅ ʏᴇᴛ!**\n"
                      "ᴡᴀɪᴛ 1-2 ᴍɪɴᴜᴛᴇs ᴀɴᴅ sᴇɴᴅ ᴛʜᴇ ᴜᴛʀ ᴀɢᴀɪɴ, ᴏʀ ᴄʜᴇᴄᴋ ᴛʜᴇ ᴜᴛʀ ɴᴜᴍʙᴇʀ.")

        left = MAX_UTR_ATTEMPTS - user_data[user_id]["attempts"]
        if left <= 0:
            user_data[user_id]["step"] = "idle"
            await message.reply(reason + "\n\n🔒 **ᴛᴏᴏ ᴍᴀɴʏ ᴡʀᴏɴɢ ᴀᴛᴛᴇᴍᴘᴛs.** ᴏʀᴅᴇʀ ʟᴏᴄᴋᴇᴅ, ᴛʏᴘᴇ `/start` ᴀɢᴀɪɴ.")
        else:
            await message.reply(reason + f"\n\nᴀᴛᴛᴇᴍᴘᴛs ʟᴇғᴛ: {left}")

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

# ================= CALLBACK DELIVERY TO CLIENT BOTS =================
async def deliver_order(order):
    cfg = get_client(order["client"])
    if not cfg:
        return False
    data = {
        "order_id": order["_id"], "user_id": order["user_id"],
        "amount": order["amount"], "ref": order["ref"], "paid_at": order["paid_at"],
    }
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, post_callback, cfg["callback_url"], cfg["secret"], data)
    if ok:
        mark_delivered(order["_id"])
    else:
        n = bump_attempt(order["_id"])
        if n == 10:
            try:
                await bot.send_message(ADMIN_ID, f"⚠️ Callback to `{order['client']}` failing for order `{order['_id']}` (user {order['user_id']}, ₹{order['amount']}). Check that bot's /payment_done endpoint.")
            except Exception:
                pass
    return ok

async def retry_loop():
    while True:
        await asyncio.sleep(60)
        try:
            loop = asyncio.get_running_loop()
            orders = await loop.run_in_executor(None, pending_orders)
            for o in orders:
                await deliver_order(o)
        except Exception as e:
            print(f"Retry loop error: {e}")

@bot.on_message(filters.command("addbot") & filters.user(ADMIN_ID))
async def add_client_bot(client, message):
    try:
        args = message.text.split(" ", 1)[1]
        key, url, secret, uname = [x.strip() for x in args.split("|")]
        if not key.isalnum() or len(key) > 12:
            raise ValueError
        set_client(key, url, secret, uname.lstrip("@"))
        await message.reply(f"✅ Client bot `{key}` saved.")
        try:
            await message.delete()  # message contains the secret
        except Exception:
            pass
    except Exception:
        await message.reply("❌ Usage:\n`/addbot key | callback_url | secret | bot_username`\n(key: letters/digits only, max 12)")

@bot.on_message(filters.command("delbot") & filters.user(ADMIN_ID))
async def del_client_bot(client, message):
    try:
        key = message.text.split(" ", 1)[1].strip()
        await message.reply("✅ Removed." if del_client(key) else "❌ Not found.")
    except Exception:
        await message.reply("Usage: `/delbot key`")

@bot.on_message(filters.command("bots") & filters.user(ADMIN_ID))
async def list_client_bots(client, message):
    rows = list_clients()
    if not rows:
        await message.reply("No client bots yet. Use /addbot")
        return
    await message.reply("\n".join(f"• `{r['_id']}` → {r['callback_url']} (@{r['bot_username']})" for r in rows), disable_web_page_preview=True)

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
    if not WEBHOOK_SECRET:
        print("⚠️ WEBHOOK_SECRET not set - /payment webhook is disabled (all requests rejected)")
    print("🤖 KCXRY Payment Bot & Port 8080 Server Started Successfully!")
    asyncio.create_task(retry_loop())
    await idle()
    await bot.stop()

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    bot.run(main())
