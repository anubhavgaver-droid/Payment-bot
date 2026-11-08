"""
EXAMPLE - add this to each CLIENT bot (file store bot, auto post bot, ...).
Needs: integration.py (copy it next to this file) and a Flask app (most bots on Render already have one).

On the payment bot (admin only) register this bot once:
    /addbot filestore | https://<this-bot>.onrender.com/payment_done | SOME_LONG_RANDOM_SECRET | FileStoreBotUsername
Put the SAME secret in this bot's env var PAY_SECRET.
"""
import os
import json
from flask import Flask, request
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from integration import build_payload, body_sig, hmac  # hmac re-exported for compare_digest

PAY_BOT_USERNAME = "YourPaymentBotUsername"   # without @
CLIENT_KEY = "filestore"                      # same key used in /addbot (letters/digits, max 12)
PAY_SECRET = os.environ["PAY_SECRET"]

app = Flask(__name__)   # reuse your existing Flask app if you have one

# ---- 1) "Buy membership" button -> redirect to payment bot ----
def pay_button(user_id, amount, plan_ref):
    """plan_ref: letters/digits only, max 16 (e.g. 'gold30'). Amount is signed, user cannot edit it."""
    payload = build_payload(CLIENT_KEY, PAY_SECRET, user_id, amount, plan_ref)
    url = f"https://t.me/{PAY_BOT_USERNAME}?start={payload}"
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"💳 Pay ₹{amount}", url=url)]])

# usage inside your bot:
#   await message.reply("Gold membership - ₹99 / 30 days", reply_markup=pay_button(message.from_user.id, 99, "gold30"))

# ---- 2) Payment bot calls this after verified payment ----
processed_orders = set()   # in production keep this in your DB so restarts don't forget

def activate_membership(user_id, plan_ref):
    # TODO: your existing membership logic goes here
    # e.g. plans = {"gold30": 30}; add_membership(user_id, days=plans[plan_ref])
    pass

@app.route("/payment_done", methods=["POST"])
def payment_done():
    raw = request.get_data()
    sig = request.headers.get("X-Signature", "")
    if not hmac.compare_digest(sig, body_sig(PAY_SECRET, raw)):
        return "forbidden", 403
    data = json.loads(raw)
    if data["order_id"] in processed_orders:      # duplicate callback -> do nothing, still return 200
        return "ok", 200
    activate_membership(data["user_id"], data["ref"])
    processed_orders.add(data["order_id"])
    # optional: notify the user from your bot: app_client.send_message(data["user_id"], "✅ Membership active!")
    return "ok", 200
